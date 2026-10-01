"""CPU hand tracking and deterministic gesture/face-touch episodes off the face loop."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from . import config

logger = logging.getLogger(__name__)
ACTIONS = {"Thumb_Up": "mark_good", "Thumb_Down": "mark_rough", "Victory": "mark_win",
           "Pointing_Up": "toggle_focus", "Wave": "hello"}


class WaveDetector:
    """Count significant horizontal reversals in a rolling open-palm track."""

    def __init__(self):
        self.points = deque()

    def update(self, x: float, now: float, open_palm: bool) -> bool:
        if not open_palm:
            self.points.clear()
            return False
        if self.points and now - self.points[-1][0] > 0.25:
            self.points.clear()
        self.points.append((now, x))
        while self.points and now - self.points[0][0] > 1.5:
            self.points.popleft()
        direction, reversals = 0, 0
        anchor = extreme = self.points[0][1]
        for _, value in self.points:
            if direction == 0:
                if abs(value - anchor) >= 0.04:
                    direction = 1 if value > anchor else -1
                    extreme = value
            elif direction * (value - extreme) > 0:
                extreme = value
            elif direction * (extreme - value) >= 0.04:
                direction *= -1
                reversals += 1
                extreme = value
        return reversals >= 3


class GestureEpisodes:
    def __init__(self):
        self.holds = {}
        self.cooldowns = {}
        self.touch_since = None
        self.touch_counted = False
        self.touches = deque()
        self.last_update = None

    def update(self, hands: list[dict], now: float) -> list[dict]:
        if self.last_update is not None and now - self.last_update > 0.25:
            self.holds.clear()
            self.touch_since, self.touch_counted = None, False
        self.last_update = now
        events, current = [], set()
        for hand in hands:
            gesture = hand["gesture"]
            key = (hand["handedness"], gesture)
            if gesture == "None" or hand["score"] < 0.6:
                continue
            current.add(key)
            since, fired = self.holds.get(key, (now, False))
            threshold = 1.5 if gesture == "Pointing_Up" else 0.6
            if not fired and now - since >= threshold - 1e-6 and now - self.cooldowns.get(gesture, float("-inf")) >= 3 - 1e-6:
                self.cooldowns[gesture] = now
                fired = True
                events.append({"type": "gesture", "data": {"ts": now, "gesture": gesture,
                               "hand": hand["handedness"], "action": ACTIONS.get(gesture)}})
            self.holds[key] = (since, fired)
        self.holds = {k: v for k, v in self.holds.items() if k in current}
        while self.touches and now - self.touches[0] >= 3600:
            self.touches.popleft()
        if any(h["near_face"] for h in hands):
            if self.touch_since is None:
                self.touch_since = now
            if not self.touch_counted and now - self.touch_since >= 0.5 - 1e-6:
                self.touch_counted = True
                self.touches.append(now)
                events.append({"type": "face_touch", "data": {"ts": now, "count_last_hour": len(self.touches)}})
        else:
            self.touch_since, self.touch_counted = None, False
        return events


def near_face(landmarks: list[list[float]], box) -> bool:
    if box is None:
        return False
    x, y, w, h = box
    return any(x - w * 0.15 <= px <= x + w * 1.15 and y - h * 0.15 <= py <= y + h * 1.15
               for px, py in landmarks)


class HandsTracker(threading.Thread):
    def __init__(self, get_frame, on_event):
        super().__init__(daemon=True, name="hands")
        self.get_frame, self.on_event = get_frame, on_event
        self.stopped, self.paused = threading.Event(), threading.Event()
        self.latest = []
        self.error = None
        self.episodes = GestureEpisodes()
        self.waves = {"Left": WaveDetector(), "Right": WaveDetector()}
        self.last_frame = None
        self.last_seen = 0.0

    def convert(self, result, box, now):
        hands = []
        seen = set()
        for lms, labels, gestures in zip(result.hand_landmarks, result.handedness, result.gestures):
            # GestureRecognizer assumes a selfie image; Facet sends unmirrored RGB.
            label = "Right" if labels[0].category_name == "Left" else "Left"
            seen.add(label)
            category = gestures[0] if gestures else None
            gesture, score = (category.category_name, float(category.score)) if category else ("None", 0.0)
            points = [[float(p.x), float(p.y)] for p in lms]
            if self.waves[label].update(points[0][0], now, gesture == "Open_Palm" and score >= 0.6):
                gesture = "Wave"
            hands.append({"handedness": label, "gesture": gesture, "score": score,
                          "landmarks": points, "near_face": near_face(points, box)})
        for label in self.waves.keys() - seen:
            self.waves[label].update(0, now, False)
        return hands

    def snapshot(self, now=None):
        now = time.time() if now is None else now
        return self.latest if not self.paused.is_set() and now - self.last_seen <= 0.5 else []

    def stop(self):
        self.stopped.set()

    def run(self):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions

        recognizer = None
        try:
            recognizer = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_path=str(config.HAND_MODEL), delegate=BaseOptions.Delegate.CPU),
                running_mode=vision.RunningMode.VIDEO, num_hands=2))
            next_cycle = time.monotonic()
            while not self.stopped.wait(max(0, next_cycle - time.monotonic())):
                next_cycle = time.monotonic() + 1 / 15
                item = self.get_frame()
                now = time.time()
                if self.paused.is_set() or item is None or now - item[2] > 0.5:
                    self.latest = []
                    self.episodes.update([], now)
                    for wave in self.waves.values():
                        wave.update(0, now, False)
                    continue
                frame, ts, captured, box = item
                if self.last_frame is not None and ts <= self.last_frame:
                    continue  # MediaPipe VIDEO mode rejects repeated or older timestamps
                self.last_frame = ts
                result = recognizer.recognize_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=frame), ts)
                self.latest = self.convert(result, box, captured)
                self.last_seen = captured
                for event in self.episodes.update(self.latest, captured):
                    if not self.paused.is_set() and not self.stopped.is_set():
                        self.on_event(event)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            logger.exception("Hand tracker failed")
        finally:
            self.latest = []
            if recognizer is not None:
                recognizer.close()
