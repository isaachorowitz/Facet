"""Clock-injected wellness timers and focus sessions, independent of model inference."""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime

from . import config


class FocusSessions:
    def __init__(self, emit, clock=time.time):
        self.emit, self.clock = emit, clock
        self.lock = threading.RLock()
        self.session = None

    def _end(self, now):
        session = {**self.session, "ends": now, "minutes": round((now - self.session["started"]) / 60, 3)}
        self.session = None
        self.emit({"state": "ended", "session": session})

    def current(self):
        with self.lock:
            if self.session is not None and self.clock() >= self.session["ends"]:
                self._end(self.session["ends"])
            return dict(self.session) if self.session else None

    def toggle(self, minutes=25):
        with self.lock:
            now = self.clock()
            if self.current() is not None:
                self._end(now)
            else:
                self.session = {"started": now, "ends": now + minutes * 60, "minutes": minutes}
                self.emit({"state": "started", "session": dict(self.session)})
            return dict(self.session) if self.session else None


class Wellness:
    def __init__(self, emit, notify, clock=time.time):
        self.emit, self.notify, self.clock = emit, notify, clock
        self.lock = threading.RLock()
        self.last = None
        self.previous_present = False
        self.screen_since = self.away_since = self.low_since = None
        self.desk_since = self.absent_since = None
        self.present_without_sip = 0.0
        self.last_sip = None
        self.drinking = False
        self.eyes_due = False
        self.low_blink = False
        self.touches = deque()
        self.day = datetime.fromtimestamp(clock()).date()

    def _roll_day(self, now):
        day = datetime.fromtimestamp(now).date()
        if day != self.day:
            self.day, self.last_sip = day, None
            self.present_without_sip = 0.0

    def face_touch(self, ts):
        with self.lock:
            self.touches.append(ts)

    def activity(self, verdict):
        with self.lock:
            now = self.clock()
            self._roll_day(now)
            activity = verdict.get("activity", {})
            drinking = activity.get("choice") == "eating_or_drinking" and activity.get("confidence", 0) >= 0.5
            if drinking and not self.drinking and (self.last_sip is None or now - self.last_sip >= 60):
                self.last_sip = now
                self.present_without_sip = 0.0
                self.emit("sip", {"ts": now})
            self.drinking = drinking

    def update(self, present, looking, blink_rate, *, paused=False):
        with self.lock:
            now = self.clock()
            self._roll_day(now)
            dt = max(0, now - self.last) if self.last is not None else 0
            self.last = now
            if paused:
                self.screen_since = self.away_since = self.low_since = None
                self.desk_since = self.absent_since = None
                self.previous_present = False
                self.low_blink = False
                self.eyes_due = False
                return
            if present:
                if self.previous_present:
                    self.present_without_sip += dt
                if self.desk_since is None:
                    self.desk_since = now
                if self.absent_since is not None and now - self.absent_since >= config.BREAK_GAP_SECONDS:
                    self.desk_since = now
                self.absent_since = None
            else:
                if self.absent_since is None:
                    self.absent_since = now
                if now - self.absent_since >= config.BREAK_GAP_SECONDS:
                    self.desk_since = None
            self.previous_present = present
            if present and looking:
                if self.screen_since is None:
                    self.screen_since = now
                self.away_since = None
            else:
                if self.away_since is None:
                    self.away_since = now
                if now - self.away_since >= 20:
                    if self.eyes_due:
                        self.emit("eyes_break_taken", {"ts": now})
                    self.screen_since = None
                    self.eyes_due = False
            if present and blink_rate < 8:
                if self.low_since is None:
                    self.low_since = now
            else:
                self.low_since = None
            self.low_blink = self.low_since is not None and now - self.low_since >= 300
            if present and looking and self.screen_since is not None and now - self.screen_since >= 1200:
                if not self.eyes_due:
                    self.eyes_due = True
                    self.emit("eyes_break_due", {"ts": now})
                self.notify("eyes", "Give your eyes a break: look 20 feet away for at least 20 seconds.")
            if self.low_blink:
                self.notify("blink", "Your blink rate has stayed low. Blink slowly a few times and relax your eyes.")
            if present and self.present_without_sip >= 5400:
                self.notify("hydrate", "You've been here for 90 minutes without a sip. Have some water.")
            if present and self.desk_since is not None and now - self.desk_since >= 3000:
                self.notify("stand", "You've been at the desk for 50 minutes without a break. Stand up and stretch.")

    def snapshot(self):
        with self.lock:
            now = self.clock()
            self._roll_day(now)
            while self.touches and now - self.touches[0] >= 3600:
                self.touches.popleft()
            return {"eyes_on_screen_minutes": round((now - self.screen_since) / 60, 2) if self.screen_since is not None else 0.0,
                    "low_blink": self.low_blink,
                    "minutes_since_sip": round((now - self.last_sip) / 60, 2) if self.last_sip is not None else None,
                    "face_touches_last_hour": len(self.touches)}
