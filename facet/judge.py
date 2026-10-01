"""Clef-flash judge. One thread owns the model; every call goes through it.

Three kinds of verdict:
  face     the head-and-shoulders crop alone, every few seconds
  voice    a finished speech segment (transcript, prosody, voice-emotion scores)
  overall  a text read that fuses the recent face verdicts, measured face
           metrics against your baseline, and recent voice
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import traceback
from typing import Any, Callable

import numpy as np
from PIL import Image

from . import config

EXPRESSIONS = {
    "happy": "Clearly happy or pleased",
    "content": "Calm and mildly positive",
    "neutral": "Relaxed resting face with no particular emotion",
    "focused": "Concentrating on a task",
    "serious": "Serious, stern, or businesslike",
    "tired": "Tired, drowsy, or worn out",
    "bored": "Bored or disengaged",
    "sad": "Sad, down, or disappointed",
    "frustrated": "Frustrated or annoyed",
    "angry": "Angry",
    "anxious": "Worried, nervous, or anxious",
    "confused": "Confused or puzzled",
    "surprised": "Surprised or startled",
    "amused": "Amused, laughing, or grinning",
}
FIVE = lambda low, high: [f"Not {low} at all", f"Slightly {high}", f"Moderately {high}", f"Very {high}", f"Extremely {high}"]  # noqa: E731

FACE_QUESTIONS: dict[str, Any] = {
    "expression": {
        "type": "choice",
        "instructions": "Which word best describes the facial expression of the person in the image?",
        "criteria": EXPRESSIONS,
    },
    "stress": {"type": "score", "instructions": "How stressed does the person in the image look?", "criteria": FIVE("stressed", "stressed")},
    "fatigue": {"type": "score", "instructions": "How tired does the person in the image look?", "criteria": FIVE("tired", "tired")},
    "focus": {"type": "score", "instructions": "How focused on their work does the person in the image look?", "criteria": FIVE("focused", "focused")},
    "energy": {"type": "score", "instructions": "How energetic or alert does the person in the image look?", "criteria": FIVE("energetic", "energetic")},
    "positivity": {
        "type": "score",
        "instructions": "How positive or negative is the mood the person in the image shows?",
        "criteria": ["Very negative", "Somewhat negative", "Neutral", "Somewhat positive", "Very positive"],
    },
    "tension": {"type": "score", "instructions": "How much physical tension shows in the face and shoulders of the person in the image?", "criteria": FIVE("tense", "tense")},
    "smiling": {"type": "noul", "instructions": "Is the person in the image smiling?"},
    "frowning": {"type": "noul", "instructions": "Is the person in the image frowning or furrowing their brow?"},
    "jaw_clenched": {"type": "noul", "instructions": "Does the person in the image have a clenched jaw or pressed lips?"},
    "eyes_heavy": {"type": "noul", "instructions": "Do the eyes of the person in the image look heavy or droopy?"},
    "eyes_on_screen": {"type": "noul", "instructions": "Is the person in the image looking toward the camera or screen in front of them?"},
    "hand_on_face": {"type": "noul", "instructions": "Is the person in the image touching their face or resting their head on a hand?"},
    "talking": {"type": "noul", "instructions": "Is the person in the image talking?"},
    "yawning": {"type": "noul", "instructions": "Is the person in the image yawning?"},
    "distracted": {"type": "noul", "instructions": "Does the person in the image look distracted?"},
    "posture": {
        "type": "choice",
        "instructions": "What is the posture of the person in the image?",
        "criteria": {
            "upright": "Sitting upright",
            "leaning_forward": "Leaning toward the screen",
            "slumped": "Slumped or hunched",
            "reclined": "Leaning back in the chair",
            "head_on_hand": "Head resting on a hand",
        },
    },
    "activity": {
        "type": "choice",
        "instructions": "What is the person in the image most likely doing?",
        "criteria": {
            "working": "Working at the computer",
            "reading": "Reading the screen",
            "talking": "Talking with someone",
            "listening": "Listening to someone",
            "on_phone": "Looking at a phone",
            "eating_or_drinking": "Eating or drinking",
            "thinking": "Thinking or looking away",
            "idle": "Resting or doing nothing",
        },
    },
}

VOICE_QUESTIONS: dict[str, Any] = {
    "tone": {
        "type": "choice",
        "instructions": "Which word best describes how the speaker sounds, using the words, the pace, the pitch, and the voice-emotion scores?",
        "criteria": {
            "calm": "Calm and even",
            "cheerful": "Cheerful or warm",
            "energetic": "Energetic or excited",
            "rushed": "Rushed or hurried",
            "tense": "Tense or stressed",
            "irritated": "Irritated or annoyed",
            "flat": "Flat, low energy, or monotone",
            "sad": "Sad or down",
            "uncertain": "Hesitant or unsure",
        },
    },
    "stress": {"type": "score", "instructions": "How stressed does the speaker sound?", "criteria": FIVE("stressed", "stressed")},
    "energy": {"type": "score", "instructions": "How much energy is in the speaker's voice?", "criteria": FIVE("energetic", "energetic")},
    "positivity": {
        "type": "score",
        "instructions": "How positive or negative does the speaker sound?",
        "criteria": ["Very negative", "Somewhat negative", "Neutral", "Somewhat positive", "Very positive"],
    },
    "confident": {"type": "noul", "instructions": "Does the speaker sound confident?"},
    "tired": {"type": "noul", "instructions": "Does the speaker sound tired?"},
    "frustrated": {"type": "noul", "instructions": "Does the speaker sound frustrated?"},
}

# The face schema is split so the readings that move fastest refresh every cycle.
# Prefill cost scales with schema length: the core half runs in about 0.8 s on an
# M5 Max, the full schema in about 1.9 s, with the same answers to within ~0.05.
FACE_CORE_KEYS = ("expression", "stress", "fatigue", "focus", "energy", "positivity", "tension")
FACE_CORE = {k: FACE_QUESTIONS[k] for k in FACE_CORE_KEYS}
FACE_DETAIL = {k: v for k, v in FACE_QUESTIONS.items() if k not in FACE_CORE_KEYS}
DETAIL_EVERY = 3  # detail questions run on every third face cycle

OVERALL_QUESTIONS: dict[str, Any] = {
    "mood": {
        "type": "choice",
        "instructions": "Taking all the evidence together, which word best describes how this person is doing right now?",
        "criteria": EXPRESSIONS,
    },
    "stress": {"type": "score", "instructions": "Overall, how stressed is this person right now?", "criteria": FIVE("stressed", "stressed")},
    "fatigue": {"type": "score", "instructions": "Overall, how tired is this person right now?", "criteria": FIVE("tired", "tired")},
    "focus": {"type": "score", "instructions": "Overall, how focused is this person right now?", "criteria": FIVE("focused", "focused")},
    "positivity": {
        "type": "score",
        "instructions": "Overall, how positive is this person's mood right now?",
        "criteria": ["Very negative", "Somewhat negative", "Neutral", "Somewhat positive", "Very positive"],
    },
    "needs_break": {"type": "noul", "instructions": "Would this person benefit from taking a break now?"},
    "in_flow": {"type": "noul", "instructions": "Is this person in a state of deep, steady focus (flow)?"},
    "overwhelmed": {"type": "noul", "instructions": "Does this person seem overwhelmed?"},
}


def _worker_main(requests, responses, repo: str, backend: str, device: str) -> None:
    """Runs in its own process: owns the model, answers SystemOne requests forever."""
    import warnings

    warnings.filterwarnings("ignore")
    from huggingface_hub import snapshot_download

    try:
        path = snapshot_download(repo)
        if backend == "torch":
            sys.path.insert(0, path)
            from joint_schema_model import load_release_model, systemone

            model, processor = load_release_model(path, device=device)
            answer = lambda request: systemone(model, processor, request)  # noqa: E731
        else:
            import mlx.core as mx

            from .clef_mlx import ClefMLX

            mx.set_cache_limit(2 << 30)  # keep at most 2 GB of freed GPU buffers around
            answer = ClefMLX(path, device=device).systemone
        responses.put(("ready", None))
    except Exception as exc:  # reported to the parent, which surfaces it
        responses.put(("error", f"{type(exc).__name__}: {exc}"))
        return
    while True:
        job = requests.get()
        if job is None:
            return
        try:
            responses.put(("ok", answer(job)))
        except Exception as exc:
            responses.put(("error", f"{type(exc).__name__}: {exc}"))


class ClefWorker:
    """Clef in a separate process so inference never competes with the camera loop for the GIL."""

    def __init__(self) -> None:
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        self.requests, self.responses = ctx.Queue(), ctx.Queue()
        self.process = ctx.Process(
            target=_worker_main,
            args=(self.requests, self.responses, config.CLEF_REPO, config.CLEF_BACKEND, config.CLEF_DEVICE),
            daemon=True,
            name="facet-clef",
        )
        self.process.start()
        kind, payload = self.responses.get()
        if kind != "ready":
            raise RuntimeError(payload)

    def __call__(self, request: dict) -> dict:
        self.requests.put(request)
        while True:
            try:
                kind, payload = self.responses.get(timeout=1.0)
                break
            except queue.Empty:
                if not self.process.is_alive():
                    raise RuntimeError("Clef worker process exited")
        if kind != "ok":
            raise RuntimeError(payload)
        return payload

    def close(self) -> None:
        self.requests.put(None)
        self.process.join(timeout=5)


def _load_clef():
    return ClefWorker()


def simplify(answers: dict[str, Any]) -> dict[str, Any]:
    """Flatten a SystemOne response into compact values for the dashboard and storage."""
    out: dict[str, Any] = {}
    for key, a in answers.items():
        if a["type"] == "noul":
            out[key] = a["noul"]
        elif a["type"] == "choice":
            out[key] = {"choice": a["choice"], "confidence": a["confidence"], "probabilities": a["probabilities"]}
        else:
            out[key] = round(a["score"], 3)
    return out


class Judge(threading.Thread):
    def __init__(self, get_crop: Callable[[], tuple[np.ndarray | None, float]], on_verdict: Callable[[str, dict, dict], None]):
        super().__init__(daemon=True, name="judge")
        self.get_crop = get_crop
        self.on_verdict = on_verdict
        self.jobs: queue.Queue[tuple[dict, Callable[[dict], None]]] = queue.Queue()
        self.status = "loading"
        self.error: str | None = None
        self.latency: dict[str, float] = {}
        self.overall_state: Callable[[], dict | None] | None = None
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self._last_face_crop_time = 0.0

    def submit_voice(self, state: dict, callback: Callable[[dict], None]) -> None:
        """Queue a voice judgment; voice jobs run before the next face judgment."""
        self.jobs.put((state, callback))

    def _run(self, kind: str, state: Any, questions: dict, image: np.ndarray | None = None) -> dict:
        request: dict[str, Any] = {"model": "clef-flash", "state": state, "questions": questions}
        if image is not None:
            request["images"] = [Image.fromarray(image)]
        t = time.time()
        response = self.systemone(request)
        self.latency[kind] = round((time.time() - t) * 1000)
        return simplify(response["answers"])

    def run(self) -> None:
        try:
            self.systemone = _load_clef()
            self.status = "warming up"
            warm = np.full((config.CROP_SIZE, config.CROP_SIZE, 3), 128, dtype=np.uint8)
            self._run("face", {"context": "warmup"}, FACE_CORE, warm)
            self._run("face_detail", {"context": "warmup"}, FACE_DETAIL, warm)
            self._run("voice", {"warmup": True}, VOICE_QUESTIONS)
            self._run("overall", {"warmup": True}, OVERALL_QUESTIONS)
            self.status = "ready"
        except Exception as exc:  # surfaced on the dashboard
            self.status, self.error = "failed", f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
            return

        next_face = time.time()
        cycle = 0
        detail: dict = {}
        next_overall = time.time() + config.OVERALL_INTERVAL
        while not self.stopped.is_set():
            try:
                state, callback = self.jobs.get(timeout=0.1)
                callback(self._run("voice", state, VOICE_QUESTIONS))
                continue
            except queue.Empty:
                pass
            except Exception as exc:
                self.error = f"voice: {exc}"
                traceback.print_exc()
            now = time.time()
            if self.paused.is_set():
                time.sleep(0.2)
                continue
            try:
                if now >= next_face:
                    next_face = now + config.FACE_JUDGE_INTERVAL
                    crop, crop_time = self.get_crop()
                    if crop is not None and now - crop_time < 2.0 and crop_time != self._last_face_crop_time:
                        self._last_face_crop_time = crop_time
                        state = {"context": "Webcam image of a person at their desk during the workday."}
                        verdict = self._run("face", state, FACE_CORE, crop)
                        if cycle % DETAIL_EVERY == 0 or not detail:
                            detail = self._run("face_detail", state, FACE_DETAIL, crop)
                        cycle += 1
                        self.on_verdict("face", {**detail, **verdict}, {})
                if now >= next_overall and self.overall_state is not None:
                    next_overall = now + config.OVERALL_INTERVAL
                    state = self.overall_state()
                    if state is not None:
                        self.on_verdict("overall", self._run("overall", state, OVERALL_QUESTIONS), state)
                self.error = None
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
                time.sleep(1)
