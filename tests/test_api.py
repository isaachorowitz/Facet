import sqlite3
import time
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from facet import api
from facet.app import app


STATUS_KEYS = {"paused", "camera", "camera_error", "judge", "judge_error", "latency_ms",
               "voice", "voice_error", "mic", "calibrating_seconds_left", "baseline_samples",
               "baseline", "settings"}
POSTURE_KEYS = {"visible", "score", "state", "issues", "neck", "shoulder_tilt", "lean",
                "sink", "reference", "ref_neck", "skeleton", "stale"}


def assert_status(status):
    assert set(status) == STATUS_KEYS
    assert isinstance(status["paused"], bool)
    assert status["camera"] in {"on", "off", "paused"}
    assert status["judge"] in {"loading", "warming up", "ready", "failed"}
    for key in ("camera_error", "judge_error", "voice_error"):
        assert status[key] is None or isinstance(status[key], str)
    for key in ("voice", "mic"):
        assert isinstance(status[key], str)
    for key in ("calibrating_seconds_left", "baseline_samples"):
        assert isinstance(status[key], (float, int))
    assert set(status["latency_ms"]) <= {"face", "face_detail", "voice", "overall"}
    assert all(isinstance(n, (float, int)) for n in status["latency_ms"].values())
    for baseline in status["baseline"].values():
        assert set(baseline) == {"mean", "std"}
        assert all(isinstance(n, (float, int)) for n in baseline.values())
    assert set(status["settings"]) == {"notifications", "mic", "store_transcripts"}
    assert all(isinstance(v, bool) for v in status["settings"].values())


def assert_live(live):
    assert set(live) == {"type", "face", "voice", "status", "minutes_since_break", "posture", "hands", "view", "focus_session", "wellness", "caption"}
    assert live["type"] == "live"
    assert_status(live["status"])
    face = live["face"]
    assert set(face) == {"present", "metrics", "vs_usual", "blink_rate", "looking_at_screen", "yawning", "fps"}
    for key in ("present", "looking_at_screen", "yawning"):
        assert isinstance(face[key], bool)
    for key in ("metrics", "vs_usual"):
        assert isinstance(face[key], dict)
        assert all(isinstance(n, (float, int)) for n in face[key].values())
    for key in ("blink_rate", "fps"):
        assert isinstance(face[key], (float, int))
    assert isinstance(live["minutes_since_break"], (float, int))
    assert set(live["voice"]) == {"level_db", "speaking"}
    assert isinstance(live["voice"]["speaking"], bool)
    assert isinstance(live["voice"]["level_db"], (float, int))
    posture = live["posture"]
    assert set(posture) == POSTURE_KEYS
    assert isinstance(posture["visible"], bool)
    assert 0 <= posture["score"] <= 100
    assert posture["state"] in {"good", "fair", "poor", "unknown"}
    assert posture["reference"] in {"calibrated", "learned", "learning"}
    assert isinstance(posture["issues"], list)
    assert all(isinstance(issue, str) for issue in posture["issues"])
    for key in ("neck", "shoulder_tilt", "lean", "sink", "ref_neck"):
        assert isinstance(posture[key], (float, int))
    assert isinstance(posture["skeleton"], dict)
    for point in posture["skeleton"].values():
        assert len(point) == 3 and all(isinstance(n, (float, int)) for n in point)


@pytest.fixture
def client(monkeypatch):
    from facet.app import FaceTracker, Judge, VoiceListener

    def forbidden(*args, **kwargs):
        pytest.fail("Headless Hub must not start any worker")

    for worker in (FaceTracker, Judge, VoiceListener):
        monkeypatch.setattr(worker, "start", forbidden)
    with TestClient(app) as instance:
        yield instance
    assert app.state.hub.stopped.is_set()
    with pytest.raises(sqlite3.ProgrammingError):
        app.state.hub.store._query("SELECT 1")


def test_health_state_and_empty_history(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "judge": "loading", "version": api.package_version()}
    state = client.get("/api/state").json()
    assert state.pop("latest") == {}
    assert_live(state)
    assert state["status"]["camera"] == "off"
    assert app.state.hub.background_threads == []
    timeline = client.get("/api/timeline?bucket=1").json()
    assert set(timeline) == {"start", "bucket_minutes", "points"}
    assert timeline["bucket_minutes"] == 1 and timeline["points"] == []
    summary = client.get("/api/summary").json()
    assert set(summary) == {"date", "minutes_present", "first_seen", "last_seen", "verdicts", "minutes_talking", "notifications", "marks", "sips", "face_touches", "eyes_breaks_taken", "eyes_breaks_due", "focus_sessions"}
    assert summary["verdicts"] == 0 and summary["notifications"] == []
    assert client.get("/api/speech?minutes=60").json() == []


def test_speech_settings_and_persistence(client):
    hub = app.state.hub
    seg = {"ts": time.time(), "text": "A synthetic sentence.",
           "prosody": {"duration_s": 4, "words_per_minute": 45, "pitch_hz": 150,
                       "pitch_variation_semitones": 2, "loudness_db": -20, "pause_ratio": 0.1},
           "emotion": {"neutral": 1}}
    hub.on_speech(seg)
    response = client.get("/api/speech").json()
    assert response == [{**seg, "verdict": None}]
    hub.on_speech({**seg, "ts": seg["ts"] + 1, "text": "Second sentence."})
    assert [s["ts"] for s in client.get("/api/speech").json()] == [seg["ts"], seg["ts"] + 1]
    status = client.post("/api/settings", json={"mic": False, "notifications": False}).json()
    assert_status(status)
    assert status["settings"] == {"mic": False, "notifications": False, "store_transcripts": True}
    assert status["voice"] == "paused" and hub.voice.paused.is_set()
    assert hub.store.get_setting("mic", True) is False
    status = client.post("/api/settings", json={"store_transcripts": False}).json()
    assert status["settings"]["mic"] is False
    hub.on_speech({**seg, "ts": seg["ts"] + 2})
    assert client.get("/api/speech").json()[-1]["text"] == ""
    assert_status(client.post("/api/pause").json())
    assert client.post("/api/resume").json()["voice"] == "paused"
    assert client.post("/api/settings", json={"mic": True}).json()["settings"]["mic"] is True
    assert not hub.voice.paused.is_set()


def test_websocket_hello_live_and_events(client):
    hub = app.state.hub
    # Seed a full face verdict without invoking a model.
    from facet.judge import FACE_QUESTIONS
    choice = {"choice": "focused", "confidence": 0.8, "probabilities": {"focused": 0.8, "neutral": 0.2}}
    verdict = {k: (dict(choice) if q["type"] == "choice" else 0.5 if q["type"] == "noul" else 2.0)
               for k, q in FACE_QUESTIONS.items()}
    verdict["posture"]["choice"] = "upright"
    verdict["activity"]["choice"] = "working"
    hub.on_verdict("face", verdict, {})
    with client.websocket_connect("/ws") as socket:
        hello = socket.receive_json()
        assert set(hello) == {"type", "latest", "status"}
        assert hello["type"] == "hello"
        assert hello["latest"]["face"] == hub.latest["face"]
        assert_status(hello["status"])
        assert_live(socket.receive_json())
        assert_live(socket.receive_json())
        hub.on_verdict("face", verdict, {})
        hub.push({"type": "notification", "data": {"kind": "posture", "text": "Synthetic nudge"}})
        events = []
        while len(events) < 2:
            message = socket.receive_json()
            if message["type"] == "live":
                assert_live(message)
            else:
                events.append(message)
        assert events[0]["type"] == "verdict" and events[0]["kind"] == "face"
        assert events[0]["data"] == hub.latest["face"]
        assert set(events[0]) == {"type", "kind", "data", "latency_ms"}
        assert events[1] == {"type": "notification", "data": {"kind": "posture", "text": "Synthetic nudge"}}


def test_app_clients_suppress_only_backend_notifications(client, monkeypatch):
    hub = app.state.hub
    notifier = Mock()
    monkeypatch.setattr("facet.app.subprocess.run", notifier)
    monkeypatch.setattr(hub, "_minutes_since_break_cached", lambda: 100)

    def notify():
        hub.last_notified.clear()
        hub._maybe_notify({"needs_break": 1})
        assert hub.store.summary(None)["notifications"][-1]["kind"] == "stand"

    with client.websocket_connect("/ws") as dashboard:
        dashboard.receive_json()
        assert hub.app_clients == 0
        notify()
        assert notifier.call_count == 1
        with client.websocket_connect("/ws?client=app") as first:
            first.receive_json()
            assert hub.app_clients == 1
            with client.websocket_connect("/ws?client=app") as second:
                second.receive_json()
                assert hub.app_clients == 2
                notify()
                assert notifier.call_count == 1
                while (event := first.receive_json())["type"] != "notification":
                    assert_live(event)
                assert event["data"]["kind"] == "stand"
            assert hub.app_clients == 1
            notify()
            assert notifier.call_count == 1
        assert hub.app_clients == 0
        notify()
        assert notifier.call_count == 2
        hub._maybe_notify({"needs_break": 1})
        assert notifier.call_count == 2  # original cooldown still holds


def test_static_build_and_fallback(tmp_path):
    dist = tmp_path / "dist"
    bare = FastAPI()
    api.register_routes(bare, dist)
    with TestClient(bare) as client:
        assert client.get("/").text == (api.STATIC / "index.html").read_text()
        assert client.get("/assets/missing.js").status_code == 404
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<h1>Synthetic React build</h1>")
    (dist / "assets" / "app.js").write_text("console.log('synthetic')")
    built = FastAPI()
    api.register_routes(built, dist)
    with TestClient(built) as client:
        assert client.get("/").text == "<h1>Synthetic React build</h1>"
        assert client.get("/assets/app.js").text == "console.log('synthetic')"
        assert client.get("/assets/missing.js").status_code == 404


def test_version_metadata_and_fallback(monkeypatch):
    monkeypatch.setattr(api.metadata, "version", lambda name: "1.2.3" if name == "facet" else pytest.fail(name))
    assert api.package_version() == "1.2.3"

    def missing(name):
        raise api.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(api.metadata, "version", missing)
    assert api.package_version() == "0.1.0"


def test_calibration_is_cancelled_on_shutdown(client):
    assert_status(client.post("/api/calibrate?seconds=30").json())
    assert len(app.state.hub.background_threads) == 1
