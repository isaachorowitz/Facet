"""Hub services for gestures, narration, focus and wellness.

Chose a separate coordinator to keep model work and timing off camera and Clef threads.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections import deque

from .hands import HandsTracker
from .narrator import Narrator
from .wellness import FocusSessions, Wellness
from .store import day_bounds

logger = logging.getLogger(__name__)


class Features:
    def init_features(self, clock=None):
        self.clock = clock or time.time
        self.focus = FocusSessions(self.on_focus, self.clock)
        self.wellness = Wellness(self.store.add_event, self.notify, self.clock)
        self.caption = None
        self.captions = deque(maxlen=3)
        self.hands = HandsTracker(self.face.sensor_frame, self.on_hand_event)
        # Narrate whenever the person is in view, face or body: turned away is often the interesting part.
        self.narrator = Narrator(self.face.sensor_frame, self._person_in_view, self.on_caption)
        self.recap_lock = threading.Lock()
        self.notification_lock = threading.Lock()
        # User-visible day/session state survives a backend restart.
        previous = self.store.latest_focus()
        if previous and previous["state"] == "started":
            self.focus.session = previous["session"]
            self.focus.current()
        start, _ = day_bounds(time.strftime("%Y-%m-%d", time.localtime(self.clock())))
        sips = self.store.events_between("sip", start, self.clock() + 1)
        self.wellness.last_sip = sips[-1]["ts"] if sips else None
        self.wellness.touches.extend(e["ts"] for e in self.store.events_between("face_touch", self.clock() - 3600, self.clock() + 1))
        for event in self.store.events_between("notification", self.clock() - 1800, self.clock() + 1):
            self.last_notified[event["kind"]] = event["ts"]

    def start_features(self):
        self.hands.start()
        self.narrator.start()
        self.start_background(self._wellness_loop, "wellness")

    def _wellness_loop(self):
        while not self.stopped.wait(0.2):
            self.focus.current()  # expiry also runs while the camera is paused
            snap = self.face.get_snapshot()
            frame = self.face.sensor_frame()
            fresh = frame is not None and self.clock() - frame[2] <= 0.5
            self.wellness.update(snap.present and fresh, snap.looking_at_screen,
                                 snap.blink_rate, paused=self.paused)

    def on_hand_event(self, event):
        if self.paused or self.stopped.is_set():
            return
        data = event["data"]
        if event["type"] == "gesture":
            self.store.add_event("gesture", data)
            self.push(event)
            action = data["action"]
            if action in {"mark_good", "mark_rough", "mark_win"}:
                mark = {"ts": data["ts"], "kind": action.removeprefix("mark_"), "note": None}
                self.store.add_event("mark", mark)
                self.push({"type": "mark", "data": mark})
            elif action == "toggle_focus":
                self.focus.toggle()
        elif event["type"] == "face_touch":
            self.wellness.face_touch(data["ts"])
            data = {"ts": data["ts"], "count_last_hour": self.wellness.snapshot()["face_touches_last_hour"]}
            self.store.add_event("face_touch", data)
            self.push({"type": "face_touch", "data": data})

    def on_focus(self, data):
        self.store.add_event("focus", {"ts": self.clock(), **data})
        self.push({"type": "focus", "data": data})

    def _person_in_view(self) -> bool:
        snap = self.face.get_snapshot()
        return snap.present or snap.posture.visible

    def on_caption(self, data):
        if self.paused or self.stopped.is_set():
            return
        if self.caption and self.caption.get("text") == data.get("text"):
            self.caption = dict(data)  # same scene: refresh the timestamp, store and announce nothing new
            return
        self.caption = dict(data)
        self.captions.append(dict(data))
        self.store.add_event("caption", data)
        self.push({"type": "caption", "data": data})

    def generate_recap(self, date=None):
        if not self.recap_lock.acquire(blocking=False):
            raise RuntimeError("A recap is already being generated")
        try:
            evidence = self.store.recap_evidence(date)
            text = self.narrator.recap(evidence)
            result = {"date": evidence["summary"]["date"], "text": text, "generated_at": self.clock()}
            self.store.add_event("recap", result)
            return result
        finally:
            self.recap_lock.release()

    def notify(self, kind, text):
        """One cooldown path for all nudges, including gesture-started focus suppression."""
        if not self.settings["notifications"] or self.paused:
            return False
        now = self.clock()
        # Serialize the suppression decision and push with focus start/end events.
        with self.focus.lock:
            if kind != "posture" and self.focus.current():
                return False
            with self.notification_lock:
                if now - self.last_notified.get(kind, float("-inf")) < 1800:
                    return False
                self.last_notified[kind] = now
                self.store.add_event("notification", {"ts": now, "kind": kind, "text": text})
                self.push({"type": "notification", "data": {"kind": kind, "text": text}})
        with self.lock:
            has_app = self.app_clients > 0
        if not has_app:
            try:
                subprocess.run(["osascript", "-e", f'display notification {json.dumps(text)} with title "Facet"'],
                               check=False, timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                logger.exception("Could not display notification")
        return True

    def live_features(self):
        return {"hands": self.hands.snapshot(), "view": self.face.view(),
                "focus_session": self.focus.current(), "wellness": self.wellness.snapshot(),
                "caption": self.caption}
