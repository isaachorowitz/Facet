"""Timer thresholds use an injected clock, with no waiting or hardware."""

from datetime import datetime

import pytest

from facet.wellness import FocusSessions, Wellness


class Clock:
    def __init__(self, now=0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def wellness():
    clock, events, nudges = Clock(), [], []
    instance = Wellness(lambda kind, data: events.append((kind, data)),
                        lambda kind, text: nudges.append(kind), clock)
    return instance, clock, events, nudges


def test_twenty_twenty_twenty_due_and_taken_once(wellness):
    instance, clock, events, nudges = wellness
    instance.update(True, True, 12)
    clock.now = 1199
    instance.update(True, True, 12)
    assert "eyes" not in nudges
    clock.now = 1200
    instance.update(True, True, 12)
    assert nudges == ["eyes"]
    assert [e[0] for e in events] == ["eyes_break_due"]
    clock.now = 1201
    instance.update(True, True, 12)
    assert [e[0] for e in events] == ["eyes_break_due"]  # no second due in one stretch
    clock.now = 1202
    instance.update(True, False, 12)
    clock.now = 1221.9
    instance.update(True, False, 12)
    assert instance.snapshot()["eyes_on_screen_minutes"] > 20
    assert len(events) == 1
    clock.now = 1222
    instance.update(True, False, 12)
    assert instance.snapshot()["eyes_on_screen_minutes"] == 0
    assert [e[0] for e in events] == ["eyes_break_due", "eyes_break_taken"]
    clock.now = 1230
    instance.update(False, False, 12)
    assert len(events) == 2
    clock.now = 1240
    instance.update(True, True, 12)
    clock.now = 2440
    instance.update(True, True, 12)
    assert [e[0] for e in events].count("eyes_break_due") == 2


def test_short_look_away_does_not_reset_screen_stretch(wellness):
    instance, clock, events, _ = wellness
    instance.update(True, True, 12)
    clock.now = 100
    instance.update(True, False, 12)
    clock.now = 119
    instance.update(True, True, 12)
    assert instance.snapshot()["eyes_on_screen_minutes"] == pytest.approx(119 / 60, abs=0.01)
    clock.now = 1200
    instance.update(True, True, 12)
    assert events[0][0] == "eyes_break_due"


def test_low_blink_requires_five_continuous_minutes_and_resets(wellness):
    instance, clock, _, nudges = wellness
    instance.update(True, True, 7.9)
    clock.now = 299.9
    instance.update(True, True, 7.9)
    assert not instance.snapshot()["low_blink"]
    clock.now = 300
    instance.update(True, True, 7.9)
    assert instance.snapshot()["low_blink"] and nudges == ["blink"]
    clock.now = 301
    instance.update(True, True, 8)
    assert not instance.snapshot()["low_blink"]
    clock.now = 302
    instance.update(True, True, 1)
    clock.now = 500
    instance.update(False, False, 1)
    clock.now = 600
    instance.update(True, True, 1)
    assert not instance.snapshot()["low_blink"]


def test_stand_at_fifty_minutes_and_absence_break_resets_desk(wellness):
    instance, clock, _, nudges = wellness
    instance.update(True, True, 12)
    clock.now = 2999
    instance.update(True, True, 12)
    assert "stand" not in nudges
    clock.now = 3000
    instance.update(True, True, 12)
    assert "stand" in nudges
    clock.now = 3001
    instance.update(False, False, 0)
    clock.now = 3181
    instance.update(True, True, 12)
    assert instance.desk_since == 3181
    nudges.clear()
    clock.now = 3200
    instance.update(True, True, 12)
    assert "stand" not in nudges


def test_short_absence_does_not_reset_desk(wellness):
    instance, clock, _, _ = wellness
    instance.update(True, True, 12)
    clock.now = 100
    instance.update(False, False, 0)
    clock.now = 279
    instance.update(True, True, 12)
    assert instance.desk_since == 0


def test_hydration_counts_only_present_time_and_sip_transitions(wellness):
    instance, clock, events, nudges = wellness
    assert instance.snapshot()["minutes_since_sip"] is None
    instance.update(True, True, 12)
    clock.now = 3000
    instance.update(True, True, 12)
    clock.now = 3001
    instance.update(False, False, 12)
    clock.now = 13000
    instance.update(True, True, 12)
    assert "hydrate" not in nudges
    clock.now = 15400
    instance.update(True, True, 12)
    assert "hydrate" in nudges  # 5400 seconds PRESENT, not elapsed time
    activity = lambda choice, confidence=0.8: {"activity": {"choice": choice, "confidence": confidence}}
    instance.activity(activity("eating_or_drinking", 0.49))
    assert instance.last_sip is None
    instance.activity(activity("eating_or_drinking", 0.5))
    assert [e[0] for e in events].count("sip") == 1
    assert instance.snapshot()["minutes_since_sip"] == 0
    clock.now += 70
    instance.activity(activity("eating_or_drinking"))
    assert [e[0] for e in events].count("sip") == 1  # still the SAME activity
    instance.activity(activity("working"))
    instance.activity(activity("eating_or_drinking"))
    assert [e[0] for e in events].count("sip") == 2
    instance.activity(activity("working"))
    clock.now += 59.9
    instance.activity(activity("eating_or_drinking"))
    assert [e[0] for e in events].count("sip") == 2
    nudges.clear()
    instance.update(True, True, 12)
    assert "hydrate" not in nudges


def test_sip_day_rollover_and_face_touch_last_hour():
    clock = Clock(datetime(2026, 9, 30, 23, 59).timestamp())
    instance = Wellness(lambda *args: None, lambda *args: None, clock)
    instance.activity({"activity": {"choice": "eating_or_drinking", "confidence": 0.8}})
    instance.face_touch(clock.now)
    assert instance.snapshot()["minutes_since_sip"] == 0
    assert instance.snapshot()["face_touches_last_hour"] == 1
    clock.now += 120
    assert instance.snapshot()["minutes_since_sip"] is None
    assert instance.snapshot()["face_touches_last_hour"] == 1
    clock.now += 3600
    assert instance.snapshot()["face_touches_last_hour"] == 0


def test_pause_does_not_invent_breaks_or_accrue_present_time(wellness):
    instance, clock, events, _ = wellness
    instance.update(True, True, 1)
    clock.now = 1200
    instance.update(True, True, 1)
    assert instance.eyes_due
    before = instance.present_without_sip
    clock.now = 1201
    instance.update(False, False, 0, paused=True)
    clock.now = 1300
    instance.update(False, False, 0, paused=True)
    clock.now = 1301
    instance.update(True, True, 1)
    assert instance.present_without_sip == before
    assert instance.snapshot()["eyes_on_screen_minutes"] == 0
    assert instance.desk_since == 1301
    assert not any(k == "eyes_break_taken" for k, _ in events)


def test_focus_start_manual_end_and_automatic_end_once():
    clock, events = Clock(), []
    focus = FocusSessions(events.append, clock)
    assert focus.toggle() == {"started": 0, "ends": 1500, "minutes": 25}
    clock.now = 123
    assert focus.toggle() is None
    assert events[-1] == {"state": "ended", "session": {"started": 0, "ends": 123, "minutes": 2.05}}
    clock.now = 200
    assert focus.toggle(10) == {"started": 200, "ends": 800, "minutes": 10}
    clock.now = 799.9
    assert focus.current() is not None
    clock.now = 900
    assert focus.current() is None
    assert events[-1] == {"state": "ended", "session": {"started": 200, "ends": 800, "minutes": 10}}
    assert len(events) == 4
    focus.current()
    assert len(events) == 4
