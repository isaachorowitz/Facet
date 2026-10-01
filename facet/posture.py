"""Upper-body posture from MediaPipe Pose, scored against your own upright posture.

A front-facing webcam sees posture as: how far the head sits above the shoulder
line (it drops as you crane forward or slump), whether the shoulders are level,
whether the shoulder line sinks in the frame, and whether you lean in toward the
screen (the face grows). Each is compared with your reference posture: the
calibration you record, or until then the best-posture moments of the last hour.
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field, replace

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from . import config

NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 2, 5, 7, 8
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR, L_HIP, R_HIP = 11, 12, 13, 14, 15, 16, 23, 24
SKELETON_POINTS = {
    "nose": NOSE, "l_eye": L_EYE, "r_eye": R_EYE, "l_ear": L_EAR, "r_ear": R_EAR,
    "l_sh": L_SH, "r_sh": R_SH, "l_el": L_EL, "r_el": R_EL, "l_wr": L_WR, "r_wr": R_WR,
    "l_hip": L_HIP, "r_hip": R_HIP,
}
MODEL = config.POSE_MODEL


@dataclass
class Posture:
    stale: bool = False
    visible: bool = False
    score: float = 0.0  # 0..100, 100 = your reference posture
    state: str = "unknown"  # good | fair | poor | unknown
    issues: list[str] = field(default_factory=list)
    neck: float = 0.0  # head height above shoulders, in shoulder widths
    shoulder_tilt: float = 0.0  # degrees, + = left shoulder lower (in the image)
    lean: float = 0.0  # face size relative to reference, 1.0 = same
    sink: float = 0.0  # shoulder line drop, in shoulder widths
    skeleton: dict[str, list[float]] = field(default_factory=dict)  # x, y (aspect-correct), visibility
    reference: str = "learning"  # calibrated | learned | learning
    ref_neck: float = 0.0  # reference head height above shoulders, for the ghost figure


def score_posture(s: dict[str, float], ref: dict[str, float] | None, lean: float) -> tuple[float, str, list[str]]:
    """Score smoothed measurements against an upright reference without side effects."""
    issues: list[str] = []
    if ref is None:
        score, state = 0.0, "unknown"
    else:
        neck_drop = max(0.0, (ref["neck"] - s["neck"]) / max(1e-3, ref["neck"]))
        sink = max(0.0, (s["shoulder_y"] - ref["shoulder_y"]) / max(1e-3, ref["shoulder_width"]))
        tilt = max(0.0, abs(s["shoulder_tilt"]) - 4.0)
        lean_pen = max(0.0, lean - 1.12)
        penalty = min(1.0, neck_drop / 0.22 * 0.5 + sink / 0.3 * 0.2 + tilt / 10 * 0.15 + lean_pen / 0.3 * 0.15)
        score = round(100 * (1 - penalty), 1)
        state = "good" if score >= 75 else "fair" if score >= 55 else "poor"
        if neck_drop > 0.12:
            issues.append("Head dropping forward")
        if sink > 0.15:
            issues.append("Sinking into the chair")
        if tilt > 3:
            issues.append(f"{'Left' if s['shoulder_tilt'] > 0 else 'Right'} shoulder low")
        if lean_pen > 0.08:
            issues.append("Leaning into the screen")
    return score, state, issues


class PostureAnalyzer:
    def __init__(self) -> None:
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL), delegate=BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=2,  # prefer the tracked face, or the central/largest body during face misses
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)
        self.calibrated: dict[str, float] | None = None
        self.learned_fallback: dict[str, float] | None = None  # from stored history
        self._history: deque[tuple[float, float, float, float]] = deque()  # ts, neck, shoulder_y, sw
        self._smooth: dict[str, float] = {}
        self.latest = Posture()
        self._last_good: float | None = None
        self._score_ema: float | None = None

    def close(self) -> None:
        self.landmarker.close()

    def set_reference(self, ref: dict[str, float] | None) -> None:
        self.calibrated = ref

    def _reference(self, now: float) -> tuple[dict[str, float] | None, str]:
        if self.calibrated:
            return self.calibrated, "calibrated"
        while self._history and now - self._history[0][0] > 3600:
            self._history.popleft()
        if len(self._history) < 240:  # two minutes at two samples a second
            return (self.learned_fallback, "learned") if self.learned_fallback else (None, "learning")
        arr = np.array([(n, y, w) for _, n, y, w in self._history])
        # Your best moments: the tall-neck end of the distribution.
        best = arr[arr[:, 0] >= np.percentile(arr[:, 0], 70)]
        return {"neck": float(np.median(best[:, 0])), "shoulder_y": float(np.median(best[:, 1])), "shoulder_width": float(np.median(best[:, 2]))}, "learned"

    def miss(self, now: float) -> Posture:
        if self._last_good is not None and now - self._last_good <= 3.0:
            self.latest = replace(self.latest, stale=True)
        else:
            self.latest = Posture()
            self._smooth.clear()
            self._score_ema = None
        return self.latest

    def update(self, rgb_small: np.ndarray, ts_ms: int, face_center: tuple[float, float] | None, face_size: float, ref_face_size: float | None, face_seen_at: float | None = None, *, now: float | None = None) -> Posture:
        h, w = rgb_small.shape[:2]
        aspect = w / h
        result = self.landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_small), ts_ms)
        now = time.time() if now is None else now
        if not result.pose_landmarks:
            return self.miss(now)
        fresh = face_center is not None and face_seen_at is not None and 0 <= now - face_seen_at <= 0.5
        poses = [p for p in result.pose_landmarks if min(p[L_SH].visibility, p[R_SH].visibility) >= 0.5]
        if not poses:
            return self.miss(now)
        if fresh:
            lm = min(poses, key=lambda p: math.hypot(p[NOSE].x - face_center[0], p[NOSE].y - face_center[1]))
            if math.hypot(lm[NOSE].x - face_center[0], lm[NOSE].y - face_center[1]) > 0.12:
                return self.miss(now)
        else:
            # Shoulder width rewards the larger body; distance rewards centrality.
            lm = max(poses, key=lambda p: math.hypot((p[L_SH].x - p[R_SH].x) * aspect, p[L_SH].y - p[R_SH].y)
                     / (1 + 2 * abs((p[L_SH].x + p[R_SH].x) / 2 - 0.5)))

        P = lambda i: np.array([lm[i].x * aspect, lm[i].y])  # noqa: E731  aspect-correct
        ls, rs = P(L_SH), P(R_SH)
        mid = (ls + rs) / 2
        sw = float(np.linalg.norm(ls - rs))
        head = (P(NOSE) + P(L_EAR) + P(R_EAR)) / 3
        if sw < 1e-3:
            return self.miss(now)
        raw = {
            "neck": float((mid[1] - head[1]) / sw),
            # The image is not mirrored here: the person's left shoulder is image-right.
            "shoulder_tilt": float(math.degrees(math.atan2(rs[1] - ls[1], ls[0] - rs[0]))),
            "shoulder_y": float(mid[1]),
            "shoulder_width": sw,
        }
        for k, v in raw.items():
            self._smooth[k] = self._smooth.get(k, v) * 0.7 + v * 0.3
        s = self._smooth
        if not self._history or now - self._history[-1][0] >= 0.5:
            self._history.append((now, s["neck"], s["shoulder_y"], s["shoulder_width"]))
        ref, ref_kind = self._reference(now)

        lean = face_size / ref_face_size if ref_face_size else 1.0
        score, state, issues = score_posture(s, ref, lean)
        if ref is not None:
            self._score_ema = score if self._score_ema is None else self._score_ema * 0.7 + score * 0.3
            score = round(self._score_ema, 1)
            state = "good" if score >= 75 else "fair" if score >= 55 else "poor"
        self._last_good = now
        sink = max(0.0, (s["shoulder_y"] - ref["shoulder_y"]) / max(1e-3, ref["shoulder_width"])) if ref else 0.0
        self.latest = Posture(
            visible=True, score=score, state=state, issues=issues,
            neck=round(s["neck"], 3), shoulder_tilt=round(s["shoulder_tilt"], 1), lean=round(lean, 3), sink=round(sink, 3),
            skeleton=self._skeleton(lm, aspect), reference=ref_kind,
            ref_neck=round(ref["neck"], 3) if ref else 0.0,
        )
        return self.latest

    @staticmethod
    def _skeleton(lm, aspect: float) -> dict[str, list[float]]:
        return {name: [round(lm[i].x * aspect, 4), round(lm[i].y, 4), round(lm[i].visibility, 2)] for name, i in SKELETON_POINTS.items()}
