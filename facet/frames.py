"""One latest-frame mailbox shared by pose, hands and narration.

Sampling advances a deadline instead of waiting a full interval after each frame,
so a 31 fps camera still supplies 15 fps rather than rounding down to 10 fps.
"""

import threading

import cv2


class FrameFeed:
    def __init__(self, hz=15):
        self.interval = 1 / hz
        self.next_frame = 0.0
        self.lock = threading.Lock()
        self.frame = self.pose_frame = None

    def publish(self, rgb, ts_ms, now, face_box, face_center, face_seen_at):
        if now < self.next_frame:
            return False
        if now - self.next_frame > self.interval:
            self.next_frame = now + self.interval
        else:
            self.next_frame += self.interval
        small = cv2.resize(rgb, (640, 360), interpolation=cv2.INTER_AREA)
        with self.lock:
            self.frame = (small, ts_ms, now, face_box)
            self.pose_frame = (small, ts_ms, now, face_center, face_seen_at)
        return True

    def latest(self):
        with self.lock:
            return self.frame

    def latest_pose(self):
        with self.lock:
            return self.pose_frame

    def clear(self):
        with self.lock:
            self.frame = self.pose_frame = None
