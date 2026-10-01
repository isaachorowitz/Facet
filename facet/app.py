"""Facet server: wires camera, voice, and the Clef judge to a local dashboard."""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from . import config
from .face import FaceTracker
from .judge import Judge
from .store import Store
from .voice import VoiceListener

STATIC = Path(__file__).parent / "static"


class Hub:
    """Shared state between the worker threads and the web clients."""

    def __init__(self) -> None:
        config.ensure_models()
        self.store = Store()
        self.settings = {
            "notifications": self.store.get_setting("notifications", True),
            "mic": self.store.get_setting("mic", True),
            "store_transcripts": self.store.get_setting("store_transcripts", True),
        }
        self.events: deque[tuple[int, dict]] = deque(maxlen=200)
        self.seq = 0
        self.lock = threading.Lock()
        self.latest: dict[str, dict] = {}
        self.calibrating_until = 0.0
        self.started = time.time()
        self.last_notified: dict[str, float] = {}
        self.paused = False

        self.face = FaceTracker()
        self.judge = Judge(self.face.latest_crop, self.on_verdict)
        self.judge.overall_state = self.overall_state
        self.voice = VoiceListener(self.on_speech)
        if not self.settings["mic"]:
            self.voice.paused.set()

    def apply_baseline(self) -> None:
        self.face.posture_ref = self.store.posture_ref
        self.face.posture_learned = self.store.posture_learned
        fs = self.store.baseline.get("face_size")
        self.face.ref_face_size = fs["mean"] if fs else None

    def start(self) -> None:
        # transformers resolves names lazily and that is not thread safe; resolve
        # everything the workers need here, before any of them start.
        from transformers import (  # noqa: F401
            AutoFeatureExtractor,
            AutoModelForAudioClassification,
            AutoProcessor,
            Qwen3_5ForConditionalGeneration,
        )

        self.apply_baseline()
        self.face.start()
        self.judge.start()
        self.voice.start()
        threading.Thread(target=self._window_loop, daemon=True, name="windows").start()

    def stop(self) -> None:
        for worker in (self.face, self.judge, self.voice):
            worker.stopped.set()

    def push(self, event: dict) -> None:
        with self.lock:
            self.seq += 1
            self.events.append((self.seq, event))

    # -- callbacks from workers -------------------------------------------
    def on_verdict(self, kind: str, verdict: dict, state: dict) -> None:
        verdict = {"ts": time.time(), **verdict}
        self.latest[kind] = verdict
        self.store.add_verdict(kind, verdict)
        self.push({"type": "verdict", "kind": kind, "data": verdict, "latency_ms": self.judge.latency.get(kind)})
        if kind == "overall":
            self._maybe_notify(verdict)

    def on_speech(self, seg: dict) -> None:
        recent = self.latest.get("face")
        state = {
            "transcript": seg["text"],
            "prosody": seg["prosody"],
            "voice_emotion_model_scores": seg["emotion"],
            "speaker_usual_pitch_hz": self._usual_pitch(),
        }
        if recent and time.time() - recent["ts"] < 10:
            state["face_expression_at_the_time"] = recent["expression"]["choice"]

        def done(verdict: dict) -> None:
            verdict = {"ts": time.time(), **verdict}
            self.latest["voice"] = verdict
            self.store.add_speech(seg, verdict, self.settings["store_transcripts"])
            self.push({"type": "speech", "data": {**seg, "verdict": verdict}, "latency_ms": self.judge.latency.get("voice")})

        if self.judge.status == "ready":
            self.judge.submit_voice(state, done)
        else:
            self.store.add_speech(seg, None, self.settings["store_transcripts"])
            self.push({"type": "speech", "data": {**seg, "verdict": None}})

    def _usual_pitch(self) -> float | None:
        pitches = [s["prosody"]["pitch_hz"] for s in self.store.recent_speech(7 * 86400) if s["prosody"].get("pitch_hz")]
        return round(float(np.median(pitches)), 1) if len(pitches) >= 5 else None

    def _window_loop(self) -> None:
        last_baseline = time.time()
        while not self.face.stopped.is_set():
            time.sleep(config.FACE_WINDOW_SECONDS)
            if self.paused:
                continue
            window = self.face.take_window()
            if window is None:
                continue
            calibrating = time.time() < self.calibrating_until
            self.store.add_face_window(window, neutral=calibrating)
            if time.time() - last_baseline > 600:
                self.store.refresh_baseline()
                self.apply_baseline()
                last_baseline = time.time()

    def overall_state(self) -> dict | None:
        faces = self.store.recent_verdicts("face", 90)
        if len(faces) < 3:
            return None
        vals = [v for _, v in faces]
        expressions: dict[str, int] = {}
        for v in vals:
            expressions[v["expression"]["choice"]] = expressions.get(v["expression"]["choice"], 0) + 1
        snap = self.face.get_snapshot()
        z = self.store.zscores({**snap.metrics, "blink_rate": snap.blink_rate}) if snap.present else {}
        state: dict = {
            "camera_judgments_last_90s": {
                "expressions_seen": expressions,
                **{f"avg_{k}_0_to_4": round(float(np.mean([v[k] for v in vals])), 2) for k in ("stress", "fatigue", "focus", "energy", "tension")},
                "avg_positivity_0_very_negative_to_4_very_positive": round(float(np.mean([v["positivity"] for v in vals])), 2),
                "share_smiling": round(float(np.mean([v["smiling"] > 0.5 for v in vals])), 2),
                "share_distracted": round(float(np.mean([v["distracted"] > 0.5 for v in vals])), 2),
                "share_eyes_heavy": round(float(np.mean([v["eyes_heavy"] > 0.5 for v in vals])), 2),
            },
            "measured_face": {
                "blinks_per_minute": snap.blink_rate,
                "yawning_now": snap.yawning,
                "difference_from_their_usual_face_in_standard_deviations": z or "not enough history yet",
            },
            "posture": self._posture_state(snap),
            "session": {
                "minutes_at_desk_since_last_break": round(self._minutes_since_break_cached(), 1),
                "local_time": datetime.now().strftime("%H:%M"),
            },
        }
        speech = self.store.recent_speech(300)
        if speech:
            state["voice_last_5_minutes"] = [
                {"said": s["text"][:200], "tone": (s["verdict"] or {}).get("tone", {}).get("choice"), "words_per_minute": s["prosody"]["words_per_minute"]}
                for s in speech[-4:]
            ]
        return state

    @staticmethod
    def _posture_state(snap) -> dict | str:
        p = snap.posture
        if not p.visible or p.state == "unknown":
            return "not measured yet"
        return {"score_0_to_100": p.score, "state": p.state, "issues": p.issues or "none"}

    def _recent_posture(self, seconds: float) -> list[float]:
        rows = self.store._query("SELECT data FROM face_windows WHERE ts > ? AND neutral=0", (time.time() - seconds,))
        return [json.loads(d)["posture_score"] for (d,) in rows if "posture_score" in json.loads(d)]

    def _minutes_since_break(self) -> float:
        rows = self.store._query("SELECT ts, data FROM face_windows WHERE ts > ? ORDER BY ts", (time.time() - 6 * 3600,))
        present = [ts for ts, d in rows if json.loads(d).get("present", 0) > 0.5]
        if not present:
            return 0.0
        start = present[0]
        for a, b in zip(present, present[1:]):
            if b - a > config.BREAK_GAP_SECONDS:
                start = b
        return (present[-1] - start) / 60

    def _maybe_notify(self, verdict: dict) -> None:
        if not self.settings["notifications"]:
            return
        now = time.time()
        recent = self.store.recent_verdicts("overall", 600)
        messages = []
        if len(recent) >= 20 and np.mean([v["stress"] for _, v in recent]) >= 2.5:
            messages.append(("stress", "You've looked stressed for ten minutes. Unclench your jaw and drop your shoulders."))
        if verdict["needs_break"] > 0.75 and self._minutes_since_break_cached() > 90:
            messages.append(("break", f"{int(self._minutes_since_break_cached())} minutes at the desk without a break. Stand up for a few."))
        if len(recent) >= 20 and np.mean([v["fatigue"] for _, v in recent]) >= 2.8:
            messages.append(("fatigue", "You've looked tired for a while. Water, light, or a short walk might help."))
        posture = self._recent_posture(600)
        if len(posture) >= 90 and sum(1 for x in posture if x < 55) / len(posture) >= 0.7:
            messages.append(("posture", "You've been slouching for ten minutes. Sit back, chin in, shoulders down, or stand up for a minute."))
        for key, text in messages:
            if now - self.last_notified.get(key, 0) < 1800:
                continue
            self.last_notified[key] = now
            self.store.add_event("notification", {"kind": key, "text": text})
            self.push({"type": "notification", "data": {"kind": key, "text": text}})
            subprocess.run(["osascript", "-e", f'display notification {json.dumps(text)} with title "Facet"'], check=False)

    def status(self) -> dict:
        return {
            "paused": self.paused,
            "camera": "on" if self.face.camera_on else ("paused" if self.paused else "off"),
            "camera_error": self.face.error,
            "judge": self.judge.status,
            "judge_error": self.judge.error,
            "latency_ms": self.judge.latency,
            "voice": "paused" if self.voice.paused.is_set() else self.voice.status,
            "voice_error": self.voice.error,
            "mic": self.voice.device_name,
            "calibrating_seconds_left": max(0, round(self.calibrating_until - time.time())),
            "baseline_samples": int(self.store.baseline.get("_samples", {}).get("mean", 0)),
            "baseline": {k: v for k, v in self.store.baseline.items() if not k.startswith("_")},
            "settings": self.settings,
        }

    def live(self) -> dict:
        snap = self.face.get_snapshot()
        metrics = {k: round(v, 3) for k, v in snap.metrics.items()}
        return {
            "type": "live",
            "face": {
                "present": snap.present,
                "metrics": metrics,
                "vs_usual": self.store.zscores({**snap.metrics, "blink_rate": snap.blink_rate}) if snap.present else {},
                "blink_rate": snap.blink_rate,
                "looking_at_screen": snap.looking_at_screen,
                "yawning": snap.yawning,
                "fps": round(snap.fps, 1),
            },
            "voice": {"level_db": round(self.voice.level_db, 1), "speaking": self.voice.speaking},
            "status": self.status(),
            "minutes_since_break": round(self._minutes_since_break_cached(), 1),
            "posture": {
                "visible": snap.posture.visible,
                "score": snap.posture.score,
                "state": snap.posture.state,
                "issues": snap.posture.issues,
                "neck": snap.posture.neck,
                "shoulder_tilt": snap.posture.shoulder_tilt,
                "lean": snap.posture.lean,
                "sink": snap.posture.sink,
                "reference": snap.posture.reference,
                "ref_neck": snap.posture.ref_neck,
                "skeleton": snap.posture.skeleton,
            },
        }

    _break_cache = (0.0, 0.0)

    def _minutes_since_break_cached(self) -> float:
        t, v = self._break_cache
        if time.time() - t > 30:
            v = self._minutes_since_break()
            self._break_cache = (time.time(), v)
        return v


hub: Hub


app = FastAPI(title="Facet")


@app.on_event("startup")
def _startup() -> None:
    global hub
    hub = Hub()
    hub.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    hub.stop()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state() -> JSONResponse:
    return JSONResponse({**hub.live(), "latest": hub.latest})


@app.get("/api/timeline")
def timeline(date: str | None = None, bucket: int = 5) -> JSONResponse:
    return JSONResponse(hub.store.timeline(date, bucket))


@app.get("/api/summary")
def summary(date: str | None = None) -> JSONResponse:
    return JSONResponse(hub.store.summary(date))


@app.get("/api/speech")
def speech(minutes: int = 60) -> JSONResponse:
    return JSONResponse(hub.store.recent_speech(minutes * 60))


@app.post("/api/calibrate")
def calibrate(seconds: int = 30) -> JSONResponse:
    hub.calibrating_until = time.time() + seconds

    def finish() -> None:
        time.sleep(seconds + config.FACE_WINDOW_SECONDS + 1)
        hub.store.refresh_baseline()
        hub.apply_baseline()
        hub.store.add_event("calibration", {"seconds": seconds})
        hub.push({"type": "calibrated", "data": hub.status()})

    threading.Thread(target=finish, daemon=True).start()
    return JSONResponse(hub.status())


@app.post("/api/pause")
def pause() -> JSONResponse:
    hub.paused = True
    hub.face.paused.set()
    hub.judge.paused.set()
    hub.voice.paused.set()
    return JSONResponse(hub.status())


@app.post("/api/resume")
def resume() -> JSONResponse:
    hub.paused = False
    hub.face.paused.clear()
    hub.judge.paused.clear()
    if hub.settings["mic"]:
        hub.voice.paused.clear()
    return JSONResponse(hub.status())


@app.post("/api/settings")
async def settings(body: dict) -> JSONResponse:
    for key in ("notifications", "mic", "store_transcripts"):
        if key in body:
            hub.settings[key] = bool(body[key])
            hub.store.set_setting(key, bool(body[key]))
    if hub.settings["mic"] and not hub.paused:
        hub.voice.paused.clear()
    else:
        hub.voice.paused.set()
    return JSONResponse(hub.status())


@app.get("/video.mjpg")
async def video() -> StreamingResponse:
    async def frames():
        hub.face.preview_clients += 1
        last = None
        try:
            while True:
                jpeg = hub.face.preview_jpeg
                if jpeg and jpeg is not last:
                    last = jpeg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                await asyncio.sleep(1 / 15)
        finally:
            hub.face.preview_clients -= 1

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    with hub.lock:
        last = hub.seq
    await socket.send_json({"type": "hello", "latest": hub.latest, "status": hub.status()})
    try:
        while True:
            await socket.send_json(hub.live())
            with hub.lock:
                fresh = [e for s, e in hub.events if s > last]
                last = hub.seq
            for event in fresh:
                await socket.send_json(event)
            await asyncio.sleep(0.2)
    except (WebSocketDisconnect, RuntimeError):
        pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Facet: a local mirror for your face and voice")
    parser.add_argument("--no-browser", action="store_true", help="do not open the dashboard")
    args = parser.parse_args()
    url = f"http://{config.HOST}:{config.PORT}/"
    if not args.no_browser:
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()
    print(f"Facet dashboard: {url}", flush=True)
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning")


if __name__ == "__main__":
    main()
