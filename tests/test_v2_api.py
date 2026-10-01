"""v2 REST, WebSocket actions, persistence and headless model isolation."""

import json
import time
from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from facet.app import app
from facet.hands import ACTIONS
from facet.store import Store, day_bounds
from test_wellness import Clock


@pytest.fixture
def client(monkeypatch):
    from facet import face, hands, judge, narrator, voice

    def forbidden(*args, **kwargs):
        pytest.fail("Headless must start no hardware, model or history worker")

    for worker in (face.FaceTracker, hands.HandsTracker, judge.Judge, narrator.Narrator, voice.VoiceListener):
        monkeypatch.setattr(worker, "start", forbidden)
    monkeypatch.setattr("facet.features.subprocess.run", forbidden)
    with TestClient(app) as client:
        yield client
    assert app.state.hub.background_threads == []


def test_new_empty_contract_fields_and_no_model_recap(client):
    state = client.get("/api/state").json()
    assert state["hands"] == [] and state["caption"] is None and state["focus_session"] is None
    assert state["view"] == {"x": 0, "y": 0, "w": 1, "h": 1}
    assert state["wellness"] == {"eyes_on_screen_minutes": 0, "low_blink": False,
                                 "minutes_since_sip": None, "face_touches_last_hour": 0}
    assert state["posture"]["stale"] is False
    assert client.get("/api/marks").json() == []
    assert client.get("/api/captions").json() == []
    date = datetime.now().strftime("%Y-%m-%d")
    assert client.get("/api/recap").json() == {"date": date, "text": None}
    assert client.post("/api/recap").status_code == 503
    assert app.state.hub.narrator.worker is None
    summary = client.get("/api/summary").json()
    assert {k: summary[k] for k in ("marks", "sips", "face_touches", "eyes_breaks_due", "eyes_breaks_taken", "focus_sessions")} == {
        "marks": [], "sips": 0, "face_touches": 0, "eyes_breaks_due": 0, "eyes_breaks_taken": 0, "focus_sessions": []}


@pytest.mark.parametrize("gesture,kind", [("Thumb_Up", "good"), ("Thumb_Down", "rough"), ("Victory", "win")])
def test_gesture_actions_write_mark_and_push_both_messages(client, gesture, kind):
    hub = app.state.hub
    ts = time.time()
    hub.on_hand_event({"type": "gesture", "data": {"ts": ts, "gesture": gesture, "hand": "Left", "action": ACTIONS[gesture]}})
    mark = {"ts": ts, "kind": kind, "note": None}
    assert client.get("/api/marks").json() == [mark]
    assert client.get("/api/summary").json()["marks"] == [mark]
    assert [event["type"] for _, event in hub.events] == ["gesture", "mark"]
    assert hub.events[-1][1] == {"type": "mark", "data": mark}
    assert hub.store._query("SELECT kind FROM events ORDER BY rowid") == [("gesture",), ("mark",)]
    assert client.get("/api/timeline").json()["points"][0]["marks"] == [kind]


def test_hello_and_other_gestures_push_only_gesture(client):
    hub = app.state.hub
    for gesture in ("Wave", "ILoveYou", "Closed_Fist"):
        hub.on_hand_event({"type": "gesture", "data": {"ts": time.time(), "gesture": gesture,
            "hand": "Right", "action": ACTIONS.get(gesture)}})
    assert [event["type"] for _, event in hub.events] == ["gesture"] * 3
    assert hub.store.marks() == [] and hub.focus.current() is None


def test_focus_rest_toggle_gesture_expiry_and_summary(client):
    hub = app.state.hub
    clock = Clock(day_bounds(None)[0] + 12 * 3600)
    hub.init_features(clock)
    session = client.post("/api/focus", json={"minutes": 10}).json()
    assert session == {"started": clock.now, "ends": clock.now + 600, "minutes": 10}
    assert client.get("/api/state").json()["focus_session"] == session
    assert hub.events[-1][1] == {"type": "focus", "data": {"state": "started", "session": session}}
    clock.now += 120
    hub.on_hand_event({"type": "gesture", "data": {"ts": clock.now, "gesture": "Pointing_Up",
                         "hand": "Left", "action": "toggle_focus"}})
    assert hub.focus.current() is None
    assert client.get("/api/summary").json()["focus_sessions"] == [{"started": session["started"], "minutes": 2}]
    clock.now += 1
    default = client.post("/api/focus", json={}).json()
    assert default["minutes"] == 25
    clock.now += 1500
    assert client.get("/api/state").json()["focus_session"] is None
    assert hub.events[-1][1]["data"] == {"state": "ended", "session": default}
    count = len(hub.events)
    client.get("/api/state")
    assert len(hub.events) == count


@pytest.mark.parametrize("body", [{"minutes": 0}, {"minutes": -1}, {"minutes": "25"}, {"minutes": True}, {"foo": 2}])
def test_focus_validation(client, body):
    assert client.post("/api/focus", json=body).status_code == 422
    assert app.state.hub.focus.current() is None


def test_focus_suppresses_every_non_posture_nudge_and_preserves_cooldown(client, monkeypatch):
    hub, notifier = app.state.hub, Mock()
    monkeypatch.setattr("facet.features.subprocess.run", notifier)
    clock = Clock(day_bounds(None)[0] + 12 * 3600)
    hub.init_features(clock)
    hub.focus.toggle()
    for kind in ("eyes", "blink", "hydrate", "stand", "stress", "fatigue", "break"):
        assert not hub.notify(kind, "Synthetic nudge")
    assert hub.notify("posture", "Synthetic posture nudge")
    assert notifier.call_count == 1
    assert not hub.notify("posture", "Synthetic posture nudge")
    hub.focus.toggle()
    assert hub.notify("eyes", "Synthetic eye nudge")
    assert not hub.notify("eyes", "Synthetic eye nudge")
    clock.now += 1800
    assert hub.notify("eyes", "Synthetic eye nudge")
    assert [v["kind"] for v in hub.store.summary(None)["notifications"]] == ["posture", "eyes", "eyes"]


def test_focus_does_not_lose_pending_wellness_nudges(client, monkeypatch):
    hub = app.state.hub
    monkeypatch.setattr("facet.features.subprocess.run", Mock())
    clock = Clock(day_bounds(None)[0] + 12 * 3600)
    hub.init_features(clock)
    hub.focus.toggle(60)
    hub.wellness.update(True, True, 12)
    clock.now += 1200
    hub.wellness.update(True, True, 12)
    summary = hub.store.summary(None)
    assert summary["eyes_breaks_due"] == 1 and summary["notifications"] == []
    hub.focus.toggle()
    hub.wellness.update(True, True, 12)
    assert hub.store.summary(None)["notifications"][0]["kind"] == "eyes"


def test_caption_persistence_order_and_overall_state_last_three(client):
    from test_store import face_verdict
    from facet.face import FaceSnapshot

    hub = app.state.hub
    now = time.time()
    for i in range(4):
        hub.on_caption({"ts": now - 4 + i, "text": f"You hold a pen while working at your desk, observation {i}."})
    captions = client.get("/api/captions").json()
    assert [c["ts"] for c in captions] == sorted(c["ts"] for c in captions)
    assert client.get("/api/state").json()["caption"] == captions[-1]
    assert hub.events[-1][1] == {"type": "caption", "data": captions[-1]}
    for _ in range(3):
        hub.store.add_verdict("face", {**face_verdict(), "distracted": 0, "eyes_heavy": 0})
    hub.face.snapshot = FaceSnapshot(present=True)
    assert hub.overall_state()["recent_captions"] == captions[-3:]


def test_face_touches_and_sips_summary_without_face_verdicts(client):
    hub = app.state.hub
    now = time.time()
    hub.on_hand_event({"type": "face_touch", "data": {"ts": now, "count_last_hour": 1}})
    hub.wellness.activity({"activity": {"choice": "eating_or_drinking", "confidence": 0.8}})
    hub.store.add_event("eyes_break_due", {"ts": now})
    hub.store.add_event("eyes_break_taken", {"ts": now + 20})
    summary = client.get("/api/summary").json()
    assert summary["face_touches"] == summary["sips"] == summary["eyes_breaks_due"] == summary["eyes_breaks_taken"] == 1
    assert client.get("/api/state").json()["wellness"]["face_touches_last_hour"] == 1
    assert hub.events[0][1] == {"type": "face_touch", "data": {"ts": now, "count_last_hour": 1}}


def test_recap_get_cache_post_generation_and_regeneration(client, monkeypatch):
    hub = app.state.hub
    text = " ".join(["You worked at your desk and paused to take care of yourself."] * 12)
    model = Mock(return_value=text)
    monkeypatch.setattr(hub.narrator, "recap", model)
    date = "2026-09-29"
    assert client.get(f"/api/recap?date={date}").json() == {"date": date, "text": None}
    model.assert_not_called()
    result = client.post(f"/api/recap?date={date}").json()
    assert result == {"date": date, "text": text, "generated_at": pytest.approx(time.time(), abs=1)}
    assert model.call_count == 1
    assert model.call_args.args[0]["summary"]["date"] == date
    assert set(model.call_args.args[0]) == {"summary", "marks", "notable_captions", "nudges"}
    assert client.get(f"/api/recap?date={date}").json() == result
    assert model.call_count == 1  # GET is read-only
    reopened = Store()
    try:
        assert reopened.cached_recap(date) == result  # cache survives reopening
    finally:
        reopened.close()
    model.return_value = text.replace("worked", "read")
    assert client.post(f"/api/recap?date={date}").json()["text"] == model.return_value
    assert client.get(f"/api/recap?date={date}").json()["text"] == model.return_value
    assert hub.store._query("SELECT count(*) FROM events WHERE kind='recap'")[0][0] == 2
    assert client.get("/api/recap?date=2026-09-28").json()["text"] is None


def test_recap_failure_and_concurrent_generation_leave_cache_intact(client, monkeypatch):
    hub = app.state.hub
    monkeypatch.setattr(hub.narrator, "recap", Mock(side_effect=RuntimeError("Narrator busy")))
    assert client.post("/api/recap").status_code == 503
    assert client.get("/api/recap").json()["text"] is None
    hub.recap_lock.acquire()
    try:
        assert client.post("/api/recap").status_code == 503
    finally:
        hub.recap_lock.release()


@pytest.mark.parametrize("path", ["/api/marks", "/api/recap"])
@pytest.mark.parametrize("date", ["2026-02-30", "2026-2-3", "nonsense"])
def test_new_date_validation(client, path, date):
    assert client.get(f"{path}?date={date}").status_code == 422
    if path == "/api/recap":
        assert client.post(f"{path}?date={date}").status_code == 422


def test_paused_features_do_not_emit_or_act(client):
    hub = app.state.hub
    assert client.post("/api/pause").json()["paused"]
    assert hub.hands.paused.is_set() and hub.narrator.paused.is_set()
    hub.on_caption({"ts": time.time(), "text": "You work."})
    hub.on_hand_event({"type": "gesture", "data": {"ts": time.time(), "gesture": "Thumb_Up", "hand": "Left", "action": "mark_good"}})
    assert hub.events == hub.events.__class__(maxlen=200)
    assert client.post("/api/resume").json()["paused"] is False
    assert not hub.hands.paused.is_set() and not hub.narrator.paused.is_set()


def test_marks_and_day_events_half_open_boundaries(store):
    start, end = day_bounds("2026-09-30")
    for ts, kind in [(start - 1, "rough"), (start, "good"), (end - 1, "win"), (end, "rough")]:
        store.add_event("mark", {"ts": ts, "kind": kind, "note": None})
    assert [m["kind"] for m in store.marks("2026-09-30")] == ["good", "win"]
    points = store.timeline("2026-09-30", 1)["points"]
    assert len(points) == 2
    assert points[0]["marks"] == ["good"] and points[-1]["marks"] == ["win"]


def test_focus_spanning_midnight_is_reported_on_its_start_day(store):
    start, end = day_bounds("2026-09-30")
    session = {"started": end - 600, "ends": end + 900, "minutes": 25}
    store.add_event("focus", {"ts": session["started"], "state": "started", "session": session})
    store.add_event("focus", {"ts": session["ends"], "state": "ended", "session": session})
    assert store.summary("2026-09-30")["focus_sessions"] == [{"started": end - 600, "minutes": 25}]
    assert store.summary("2026-10-01")["focus_sessions"] == []


def test_restart_recovers_focus_sip_touches_and_notification_cooldown(client):
    hub = app.state.hub
    clock = Clock(day_bounds(None)[0] + 12 * 3600)
    hub.init_features(clock)
    session = hub.focus.toggle()
    hub.store.add_event("sip", {"ts": clock.now})
    hub.store.add_event("face_touch", {"ts": clock.now})
    hub.store.add_event("notification", {"ts": clock.now, "kind": "eyes", "text": "Synthetic eye nudge"})
    clock.now += 30
    hub.init_features(clock)
    assert hub.focus.current() == session
    assert hub.wellness.snapshot()["minutes_since_sip"] == 0.5
    assert hub.wellness.snapshot()["face_touches_last_hour"] == 1
    assert not hub.notify("eyes", "Still within cooldown")
    clock.now += 1500
    hub.init_features(clock)
    assert hub.focus.current() is None
    assert hub.store.latest_focus()["state"] == "ended"
    assert hub.store.latest_focus()["session"]["ends"] == session["ends"]
