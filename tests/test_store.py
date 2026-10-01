import json
from datetime import datetime

import numpy as np
import pytest

from facet import config
from facet.store import Store, day_bounds


def face_verdict(expression="focused", stress=2):
    return {
        "expression": {"choice": expression},
        "stress": stress, "fatigue": 1, "focus": 3, "energy": 2,
        "positivity": 3, "tension": 1, "smiling": 0.8,
        "posture": {"choice": "upright"}, "activity": {"choice": "working"},
    }


def window(neck=0.5, smile=0.2):
    return {"present": 1, "smile": smile, "tension": 0.3, "blink_rate": 12,
            "posture_score": 80, "neck": neck, "shoulder_y": 0.5, "shoulder_width": 0.4}


def test_timeline_and_summary(store, monkeypatch):
    start, _ = day_bounds(None)
    stamp = start + 12 * 3600
    # Freeze the writer's clock to put synthetic records at known bucket offsets.
    monkeypatch.setattr("facet.store.time.time", lambda: stamp)
    for offset, expression, stress in [(0, "focused", 2), (10, "happy", 4), (20, "focused", 3)]:
        stamp = start + 12 * 3600 + offset
        store.add_verdict("face", face_verdict(expression, stress))
    stamp = start + 12 * 3600
    store.add_face_window(window())
    stamp += 5
    store.add_face_window({**window(), "posture_score": 40, "present": 0})
    store.add_face_window({**window(), "posture_score": 0}, neutral=True)
    stamp += 600
    store.add_face_window(window())
    store.add_event("notification", {"kind": "stress", "text": "Synthetic nudge"})
    store.add_event("calibration", {})
    seg = {"ts": start + 12 * 3600, "text": "Synthetic speech", "prosody": {"duration_s": 30}, "emotion": {"neutral": 1}}
    store.add_speech(seg, {"tone": {"choice": "calm"}}, True)
    store.add_speech({**seg, "ts": seg["ts"] + 30}, None, False)
    date = datetime.fromtimestamp(start).strftime("%Y-%m-%d")
    timeline = store.timeline(date)
    assert timeline["start"] == start
    assert timeline["bucket_minutes"] == 5
    assert timeline["points"] == [
        {"t": start + 12 * 3600, "stress": 3, "fatigue": 1, "focus": 3,
         "energy": 2, "positivity": 3, "tension": 1, "expression": "focused",
         "present": 0.5, "posture": 2.4, "measured_tension": 0.3, "smile": 0.2,
         "blink_rate": 12, "speech_s": 60},
        {"t": start + 12 * 3600 + 600, "present": 1, "posture": 3.2,
         "measured_tension": 0.3, "smile": 0.2, "blink_rate": 12},
    ]
    summary = store.summary(date)
    assert summary["minutes_present"] == 0.2
    assert summary["first_seen"] == seg["ts"]
    assert summary["last_seen"] == stamp
    assert summary["verdicts"] == 3
    assert summary["minutes_talking"] == 1
    assert summary["avg_stress"] == 3
    assert summary["expressions"] == {"focused": 0.667, "happy": 0.333}
    assert summary["avg_posture"] == 66.7
    assert summary["minutes_poor_posture"] == 0.1
    assert summary["minutes_good_posture"] == 0.2
    assert summary["posture"] == {"upright": 3}
    assert summary["activity"] == {"working": 3}
    assert summary["smiling_share"] == 1
    assert summary["stress_peaks"] == [{"ts": seg["ts"], "stress": 3}]
    assert summary["breaks"] == [{"start": seg["ts"], "minutes": 10.1}]
    assert summary["focus_streaks"] == []
    assert summary["voice_tones"] == {"calm": 1}
    assert summary["by_hour"] == [{"hour": 12, "stress": 3, "focus": 3, "fatigue": 1,
                                    "positivity": 3, "top_expression": "focused"}]
    assert summary["notifications"] == [{"ts": stamp, "kind": "stress", "text": "Synthetic nudge"}]
    speech = store.recent_speech(86400)
    assert [s["text"] for s in speech] == ["Synthetic speech", ""]
    assert [s["ts"] for s in speech] == sorted(s["ts"] for s in speech)
    assert speech[1]["verdict"] is None
    assert store.recent_verdicts("overall", 86400) == []


def test_baseline_calibration_and_learned_posture(store):
    assert store.baseline == {}
    assert store.posture_ref is None and store.posture_learned is None
    for i in range(60):
        store.add_face_window(window(neck=0.3 + i * 0.01, smile=i / 100))
    for _ in range(3):
        store.add_face_window(window(neck=0.75, smile=0.15), neutral=True)
    store.add_face_window({**window(neck=10, smile=10), "present": 0})
    store.refresh_baseline()
    assert store.baseline["smile"]["mean"] == 0.15
    assert store.baseline["smile"]["std"] == pytest.approx(np.std([i / 100 for i in range(60)] + [0.15] * 3))
    assert store.baseline["blink_rate"]["std"] == 1
    assert store.baseline["_samples"] == {"mean": 63, "std": 3}
    assert store.posture_ref == {"neck": 0.75, "shoulder_y": 0.5, "shoulder_width": 0.4}
    necks = [0.3 + i * 0.01 for i in range(60)] + [0.75] * 3
    best = [v for v in necks if v >= np.percentile(necks, 70)]
    assert store.posture_learned == {"neck": pytest.approx(float(np.median(best))), "shoulder_y": 0.5, "shoulder_width": 0.4}
    assert store.zscores({"smile": 0.15, "unknown": 5}) == {"smile": 0}
    store.set_setting("mic", False)
    reopened = Store()
    try:
        assert reopened.get_setting("mic", True) is False
        assert reopened.get_setting("missing", True) is True
        assert reopened.baseline == store.baseline
        assert reopened.posture_ref == store.posture_ref
        assert reopened.posture_learned == store.posture_learned
        assert config.DB_PATH.parent == config.DATA_DIR
    finally:
        reopened.close()


def test_empty_history_and_insufficient_baseline(store):
    assert store.timeline(None)["points"] == []
    summary = store.summary(None)
    assert summary["first_seen"] is None and summary["last_seen"] is None
    assert summary["verdicts"] == 0 and summary["minutes_talking"] == 0
    store.add_face_window(window())
    store.refresh_baseline()
    assert store.baseline == {} and store.posture_learned is None


def test_focus_streak(store):
    start, _ = day_bounds(None)
    for offset in range(0, 341, 20):
        store._exec("INSERT INTO verdicts VALUES (?,?,?)", (start + 36000 + offset, "face", json.dumps(face_verdict())))
    assert store.summary(None)["focus_streaks"] == [{"start": start + 36000, "minutes": 5.7}]
