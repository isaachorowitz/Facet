"""Synthetic tracks exercise wave recognition, debounce, cooldown and touches."""

from types import SimpleNamespace

import pytest

from facet.hands import GestureEpisodes, HandsTracker, WaveDetector, near_face


def hand(gesture="Thumb_Up", score=0.8, label="Left", touching=False):
    return {"handedness": label, "gesture": gesture, "score": score,
            "landmarks": [[0.5, 0.5]] * 21, "near_face": touching}


def hold(episodes, hands, start, duration, step=0.1):
    events = []
    for index in range(round(duration / step) + 1):
        events += episodes.update(hands, start + index * step)
    return events


def track(xs, duration=1.4):
    detector = WaveDetector()
    values = []
    # Interpolate each leg at 15 Hz, so dropped samples cannot create a wave.
    for i in range(len(xs) - 1):
        for j in range(4):
            t = duration * (i + j / 4) / (len(xs) - 1)
            values.append(detector.update(xs[i] + (xs[i + 1] - xs[i]) * j / 4, t, True))
    values.append(detector.update(xs[-1], duration, True))
    return values


def test_wave_requires_three_significant_reversals():
    assert any(track([0.4, 0.52, 0.4, 0.52, 0.4]))
    assert not any(track([0.4, 0.52, 0.4, 0.52]))  # two reversals
    assert not any(track([0.4, 0.42, 0.4, 0.42, 0.4]))  # tiny jitter
    assert not any(track([0.4, 0.52, 0.4, 0.52, 0.4], duration=4))
    assert not any(track([0.4, 0.43, 0.45, 0.48, 0.52]))  # one-way sweep


def test_wave_clears_on_non_open_palm_and_gaps():
    detector = WaveDetector()
    detector.update(0.4, 0, True)
    detector.update(0.5, 0.1, True)
    detector.update(0.4, 0.2, False)
    assert not detector.points
    detector.update(0.5, 1, True)
    detector.update(0.4, 2, True)
    assert list(detector.points) == [(2, 0.4)]


@pytest.mark.parametrize("gesture,action", [("Thumb_Up", "mark_good"), ("Thumb_Down", "mark_rough"),
    ("Victory", "mark_win"), ("Wave", "hello"), ("Closed_Fist", None), ("Open_Palm", None), ("ILoveYou", None)])
def test_gesture_held_and_fires_once_per_episode(gesture, action):
    episodes = GestureEpisodes()
    events = hold(episodes, [hand(gesture)], 10, 5)
    assert len(events) == 1
    assert events[0]["type"] == "gesture"
    assert events[0]["data"] == {"ts": pytest.approx(10.6), "gesture": gesture, "hand": "Left", "action": action}


def test_pointing_up_needs_one_and_a_half_seconds():
    episodes = GestureEpisodes()
    assert hold(episodes, [hand("Pointing_Up")], 0, 1.4) == []
    assert episodes.update([hand("Pointing_Up")], 1.5)[0]["data"]["action"] == "toggle_focus"


def test_debounce_confidence_release_and_cooldown_shared_between_hands():
    episodes = GestureEpisodes()
    assert hold(episodes, [hand(score=0.59)], 0, 0.8) == []
    assert hold(episodes, [hand()], 1, 0.5) == []
    assert episodes.update([], 1.6) == []
    assert len(hold(episodes, [hand(score=0.6)], 1.7, 0.7)) == 1
    assert len(hold(episodes, [hand(label="Right")], 2.5, 0.7)) == 0
    # A different gesture has its own cooldown.
    assert len(hold(episodes, [hand("Victory")], 3.3, 0.7)) == 1
    events = hold(episodes, [hand(label="Right")], 4.1, 1.3)
    assert len(events) == 1 and events[0]["data"]["ts"] >= 5.3
    assert hold(episodes, [hand("None")], 6, 1) == []


def test_two_hands_do_not_double_fire_same_gesture():
    events = hold(GestureEpisodes(), [hand(), hand(label="Right")], 0, 0.8)
    assert len(events) == 1


def test_gap_or_changed_gesture_breaks_hold():
    episodes = GestureEpisodes()
    assert hold(episodes, [hand()], 0, 0.4) == []
    assert episodes.update([hand()], 1) == []
    assert hold(episodes, [hand("Victory")], 1.1, 0.5) == []
    assert episodes.update([hand()], 1.7) == []


def test_face_touch_once_per_episode_and_hourly_expiry():
    episodes = GestureEpisodes()
    hands = [hand("None", touching=True), hand("None", label="Right", touching=True)]
    assert hold(episodes, hands, 0, 0.4) == []
    assert episodes.update(hands, 0.5) == [{"type": "face_touch", "data": {"ts": 0.5, "count_last_hour": 1}}]
    assert hold(episodes, hands, 0.6, 5) == []
    episodes.update([], 5.7)
    assert hold(episodes, hands, 5.8, 0.4) == []
    assert episodes.update(hands, 6.3)[0]["data"]["count_last_hour"] == 2
    episodes.update([], 3600.6)
    assert list(episodes.touches) == [6.3]


def test_near_face_uses_any_landmark_and_fifteen_percent_expansion():
    assert near_face([[0.37, 0.4]], (0.4, 0.3, 0.2, 0.2))
    assert not near_face([[0.369, 0.4]], (0.4, 0.3, 0.2, 0.2))
    assert near_face([[0.1, 0.1], [0.63, 0.53]], (0.4, 0.3, 0.2, 0.2))
    assert not near_face([[0.5, 0.4]], None)


def test_unmirrored_input_swaps_handedness_without_mirroring_landmarks():
    tracker = HandsTracker(lambda: None, lambda e: None)
    category = lambda name: SimpleNamespace(category_name=name, score=0.8)
    result = SimpleNamespace(hand_landmarks=[[SimpleNamespace(x=0.45, y=0.4)] * 21],
                             handedness=[[category("Left")]], gestures=[[category("Victory")]])
    value = tracker.convert(result, (0.4, 0.3, 0.2, 0.2), 10)[0]
    assert value["handedness"] == "Right"
    assert value["landmarks"] == [[0.45, 0.4]] * 21
    assert value["near_face"] and value["gesture"] == "Victory"
    tracker.latest, tracker.last_seen = [value], 10
    assert tracker.snapshot(10.4) == [value]
    assert tracker.snapshot(10.6) == []
    tracker.paused.set()
    assert tracker.snapshot(10.1) == []


def test_hand_worker_uses_cpu_video_two_hands_and_closes_recognizer(monkeypatch):
    import threading
    import time
    from unittest.mock import Mock
    from facet import face
    import numpy as np

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    tracker = HandsTracker(lambda: (frame, 123, time.time(), None), lambda e: None)
    recognizer = Mock()
    threads = []

    def recognize(image, ts):
        threads.append(threading.current_thread().name)
        assert image.width == 640 and image.height == 360 and ts == 123
        tracker.stop()
        return SimpleNamespace(hand_landmarks=[], handedness=[], gestures=[])

    recognizer.recognize_for_video.side_effect = recognize
    factory = Mock(return_value=recognizer)
    monkeypatch.setattr(face.vision.GestureRecognizer, "create_from_options", factory)
    tracker.start()
    tracker.join(2)
    assert not tracker.is_alive() and tracker.error is None
    assert threads == ["hands"]
    options = factory.call_args.args[0]
    assert options.running_mode == face.vision.RunningMode.VIDEO and options.num_hands == 2
    assert options.base_options.delegate == face.BaseOptions.Delegate.CPU
    recognizer.close.assert_called_once()
