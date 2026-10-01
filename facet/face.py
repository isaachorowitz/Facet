"""Camera capture and MediaPipe face measurement.

Everything here is measured, not guessed: muscle activations (blendshapes), head
pose, blinks, gaze, and distance. The Clef judge reads the face crop separately,
so the two channels can be compared on the dashboard.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from contextlib import ExitStack
from dataclasses import dataclass, field, replace

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from . import config
from .posture import Posture, PostureAnalyzer
from .frames import FrameFeed

logger = logging.getLogger(__name__)

# Metrics shown live and stored per window. Values are 0..1 unless noted.
METRICS = (
    "smile",
    "genuine_smile",
    "smile_asymmetry",
    "brow_furrow",
    "brow_raise",
    "eye_squint",
    "eye_openness",
    "eye_wide",
    "lip_press",
    "jaw_forward",
    "jaw_open",
    "frown",
    "sneer",
    "gaze_down",
    "gaze_side",
    "tension",
    "yaw",  # degrees
    "pitch",  # degrees
    "roll",  # degrees
    "face_size",  # face width / frame width, a distance proxy
    "movement",  # head motion over the last few seconds
)


def _avg(shapes: dict[str, float], *names: str) -> float:
    return sum(shapes.get(n, 0.0) for n in names) / len(names)


def frame_metrics(shapes: dict[str, float], matrix: np.ndarray | None, bbox_w: float) -> dict[str, float]:
    smile = _avg(shapes, "mouthSmileLeft", "mouthSmileRight")
    cheek = _avg(shapes, "cheekSquintLeft", "cheekSquintRight")
    brow_furrow = _avg(shapes, "browDownLeft", "browDownRight")
    eye_squint = _avg(shapes, "eyeSquintLeft", "eyeSquintRight")
    lip_press = _avg(shapes, "mouthPressLeft", "mouthPressRight") * 0.7 + _avg(
        shapes, "mouthRollLower", "mouthRollUpper"
    ) * 0.3
    jaw_forward = shapes.get("jawForward", 0.0)
    m = {
        "smile": smile,
        # Duchenne marker: the cheeks lift with the mouth in a felt smile.
        "genuine_smile": min(1.0, smile * (0.4 + cheek * 1.5)),
        "smile_asymmetry": abs(shapes.get("mouthSmileLeft", 0) - shapes.get("mouthSmileRight", 0)),
        "brow_furrow": brow_furrow,
        "brow_raise": shapes.get("browInnerUp", 0) * 0.5 + _avg(shapes, "browOuterUpLeft", "browOuterUpRight") * 0.5,
        "eye_squint": eye_squint,
        "eye_openness": 1.0 - _avg(shapes, "eyeBlinkLeft", "eyeBlinkRight"),
        "eye_wide": _avg(shapes, "eyeWideLeft", "eyeWideRight"),
        "lip_press": lip_press,
        "jaw_forward": jaw_forward,
        "jaw_open": shapes.get("jawOpen", 0.0),
        "frown": _avg(shapes, "mouthFrownLeft", "mouthFrownRight"),
        "sneer": _avg(shapes, "noseSneerLeft", "noseSneerRight"),
        "gaze_down": _avg(shapes, "eyeLookDownLeft", "eyeLookDownRight"),
        "gaze_side": abs(
            _avg(shapes, "eyeLookOutLeft", "eyeLookInRight") - _avg(shapes, "eyeLookInLeft", "eyeLookOutRight")
        ),
        "face_size": bbox_w,
    }
    # Facial tension: the muscles that tighten under strain, minus a smile.
    m["tension"] = max(
        0.0,
        min(1.0, (brow_furrow * 1.4 + eye_squint * 0.8 + lip_press * 1.6 + jaw_forward * 2.0) / 3.0 - smile * 0.3),
    )
    if matrix is not None:
        r = matrix[:3, :3]
        m["pitch"] = math.degrees(math.atan2(r[2, 1], r[2, 2]))
        m["yaw"] = math.degrees(math.asin(max(-1.0, min(1.0, -r[2, 0]))))
        m["roll"] = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    else:
        m["pitch"] = m["yaw"] = m["roll"] = 0.0
    return m


@dataclass
class FaceSnapshot:
    present: bool = False
    metrics: dict[str, float] = field(default_factory=dict)
    blink_rate: float = 0.0  # blinks per minute over the last minute
    looking_at_screen: bool = False
    yawning: bool = False
    fps: float = 0.0
    shapes: dict[str, float] = field(default_factory=dict)
    posture: Posture = field(default_factory=Posture)


POSTURE_KEYS = ("posture_score", "neck", "shoulder_tilt", "shoulder_y", "shoulder_width", "lean", "sink")


class FaceTracker(threading.Thread):
    """Owns the webcam. Publishes the latest measurement, crop, and preview frame."""

    def __init__(self) -> None:
        super().__init__(daemon=True, name="face")
        self.lock = threading.Lock()
        self.snapshot = FaceSnapshot()
        self.crop: np.ndarray | None = None  # RGB head-and-shoulders crop for Clef
        self.crop_time = 0.0
        self.preview_jpeg: bytes | None = None
        self.window: list[dict[str, float]] = []  # per-frame metrics for the storage window
        self.window_blinks = 0
        self.window_present = 0
        self.window_frames = 0
        self.paused = threading.Event()
        self.stopped = threading.Event()
        self.camera_on = False
        self.error: str | None = None
        self._blinks: deque[float] = deque()
        self._eyes_closed = False
        self._jaw_open_since: float | None = None
        self._nose: deque[tuple[float, float, float]] = deque()
        self._last_seen: float | None = None
        self._face_box: tuple[float, float, float, float] | None = None
        self._frame_size = (1, 1)
        self.frames = FrameFeed()
        self._last_center: tuple[float, float] | None = None
        self._smoothed: dict[str, float] = {}
        self._view: tuple[float, float, float] | None = None
        self._view_box = (0.0, 0.0, 1.0, 1.0)
        self.posture_analyzer: PostureAnalyzer | None = None
        self.ref_face_size: float | None = None  # set from your baseline
        self.posture_ref: dict[str, float] | None = None  # set from your calibration
        self.posture_learned: dict[str, float] | None = None  # set from stored history
        self._posture = Posture()
        self._frame_i = 0
        self._pose_ready = threading.Event()
        self.preview_clients = 0  # open /video.mjpg streams; no encoding when nobody watches
        self._last_preview = 0.0
        self._warm_frames = 0
        self._capture = self._landmarker = self._pose_thread = None

    def _portrait(self, frame: np.ndarray, cx: float, cy: float, height: float) -> np.ndarray:
        """Crop a 6:5 window of the given height centered on (cx, cy), clamped to the frame."""
        h, w = frame.shape[:2]
        vh = min(float(h), height, w / 1.2)
        vw = vh * 1.2
        x0 = min(max(0.0, cx - vw / 2), w - vw)
        y0 = min(max(0.0, cy - vh * 0.5), h - vh)
        self._view_box = (x0, y0, vw, vh)
        region = frame[int(y0) : int(y0 + vh), int(x0) : int(x0 + vw)]
        return cv2.resize(region, (720, 600), interpolation=cv2.INTER_AREA)

    # -- public -----------------------------------------------------------
    def take_window(self) -> dict | None:
        """Return and reset the averaged metrics since the last call."""
        with self.lock:
            frames, rows = self.window_frames, self.window
            blinks, present = self.window_blinks, self.window_present
            self.window, self.window_frames, self.window_blinks, self.window_present = [], 0, 0, 0
            snap = self.snapshot
        if frames == 0:
            return None
        out: dict = {"present": present / frames, "blinks": blinks, "blink_rate": snap.blink_rate}
        if rows:
            for k in METRICS:
                out[k] = float(np.mean([r[k] for r in rows if k in r]))
            out["looking_at_screen"] = float(np.mean([r.get("_screen", 0.0) for r in rows]))
            for k in POSTURE_KEYS:
                vals = [r[k] for r in rows if k in r]
                if vals:
                    out[k] = float(np.mean(vals))
        return out

    def latest_crop(self) -> tuple[np.ndarray | None, float]:
        with self.lock:
            return self.crop, self.crop_time

    def sensor_frame(self):
        """Latest shared 640x360 full RGB frame and matching face metadata."""
        return self.frames.latest()

    def view(self) -> dict[str, float]:
        with self.lock:
            w, h = self._frame_size
            x, y, vw, vh = self._view_box
            return {"x": x / w, "y": y / h, "w": vw / w, "h": vh / h}

    def get_snapshot(self) -> FaceSnapshot:
        with self.lock:
            return FaceSnapshot() if self.paused.is_set() else replace(self.snapshot, posture=self._posture)

    # -- loop -------------------------------------------------------------
    def run(self) -> None:
        try:
            self._capture_frames()
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            logger.exception("Face tracker failed")
        finally:
            self.stopped.set()
            self._pose_ready.set()
            self.camera_on = False
            try:
                with ExitStack() as cleanup:
                    if self.posture_analyzer is not None:
                        cleanup.callback(self.posture_analyzer.close)
                    if self._pose_thread is not None:
                        cleanup.callback(self._pose_thread.join)
                    if self._landmarker is not None:
                        cleanup.callback(self._landmarker.close)
                    if self._capture is not None:
                        cleanup.callback(self._capture.release)
            except Exception as exc:
                self.error = f"cleanup: {exc}"
                logger.exception("Face tracker cleanup failed")

    def stop(self) -> None:
        self.stopped.set()
        self._pose_ready.set()

    def _capture_frames(self) -> None:
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(config.FACE_MODEL), delegate=BaseOptions.Delegate.CPU),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=2,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        landmarker = self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self.posture_analyzer = PostureAnalyzer()
        pose_thread = self._pose_thread = threading.Thread(target=self._pose_loop, daemon=True, name="pose")
        pose_thread.start()
        cap = None
        t0 = time.monotonic()
        last_ts = -1
        fps_times: deque[float] = deque(maxlen=30)
        while not self.stopped.is_set():
            if self.paused.is_set():
                if cap is not None:
                    cap.release()
                    cap, self._capture, self.camera_on = None, None, False
                    with self.lock:
                        self.snapshot = FaceSnapshot()
                        self.preview_jpeg = None
                        self.crop = None
                        self.frames.clear()
                        self._last_seen = None
                self.stopped.wait(0.2)
                continue
            if cap is None:
                cap = self._capture = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_AVFOUNDATION)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
                if not cap.isOpened():
                    self.error = f"camera {config.CAMERA_INDEX} could not be opened"
                    logger.error(self.error)
                    cap.release()
                    cap = self._capture = None
                    self.stopped.wait(2)
                    continue
                self.camera_on, self.error = True, None
            ok, frame = cap.read()
            if not ok or frame is None:
                self.stopped.wait(0.05)
                continue
            if self._warm_frames < 60:  # the first frames after opening can be black
                self._warm_frames += 1
                if frame.mean() < 1.0:
                    continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ts = int((time.monotonic() - t0) * 1000)
            if ts <= last_ts:
                ts = last_ts + 1
            last_ts = ts
            result = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
            self._frame_i += 1
            now = time.time()
            fps_times.append(now)
            self._process(result, rgb, frame, now, len(fps_times) / max(1e-3, fps_times[-1] - fps_times[0]))
            if self.frames.publish(rgb, ts, now, self._face_box if self._last_seen is not None and now - self._last_seen <= 0.5 else None,
                                   self._last_center, self._last_seen):
                self._pose_ready.set()

    def _pose_loop(self) -> None:
        """Posture changes slowly; scoring it off the camera thread keeps face tracking at full rate."""
        last_pose = 0.0
        last_pose_ts = -1
        while not self.stopped.is_set():
            if not self._pose_ready.wait(timeout=0.5):
                if self.paused.is_set():
                    self._posture = Posture()
                elif self.posture_analyzer is not None:
                    self._posture = self.posture_analyzer.miss(time.time())
                continue
            self._pose_ready.clear()
            if self.stopped.is_set():
                break
            if self.paused.is_set():
                self._posture = Posture()
                continue
            if self.stopped.wait(max(0, 0.1 - (time.monotonic() - last_pose))):
                break
            item = self.frames.latest_pose()
            if item is None:
                continue
            frame, ts, captured, center, seen = item
            if ts <= last_pose_ts:
                continue  # no new frame yet; MediaPipe VIDEO mode rejects a repeated timestamp
            last_pose_ts = ts
            last_pose = time.monotonic()
            analyzer = self.posture_analyzer
            analyzer.set_reference(self.posture_ref)
            analyzer.learned_fallback = self.posture_learned
            try:
                self._posture = analyzer.update(frame, ts, center, self._smoothed.get("face_size", 0.0), self.ref_face_size, seen, now=captured)
            except Exception as exc:
                self.error = f"pose: {exc}"
                logger.exception("Posture tracker failed")

    def _pick_face(self, result, w: int, h: int) -> int | None:
        if not result.face_landmarks:
            return None
        best, best_score = None, -1.0
        for i, lms in enumerate(result.face_landmarks):
            xs = [p.x for p in lms]
            ys = [p.y for p in lms]
            width = max(xs) - min(xs)
            cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
            score = width
            if self._last_center is not None:
                # Stay with the same person unless someone is clearly bigger (closer).
                dist = math.hypot(cx - self._last_center[0], cy - self._last_center[1])
                score += max(0.0, 0.15 - dist)
            if score > best_score:
                best, best_score = i, score
        return best

    def _process(self, result, rgb: np.ndarray, frame_bgr: np.ndarray, now: float, fps: float) -> None:
        h, w = rgb.shape[:2]
        idx = self._pick_face(result, w, h)
        snap = FaceSnapshot(fps=fps, posture=self._posture)
        crop = None
        preview = None
        blinked = False
        want_preview = self.preview_clients > 0 and now - self._last_preview >= 1 / 12
        if idx is not None:
            lms = result.face_landmarks[idx]
            xs = np.array([p.x for p in lms])
            ys = np.array([p.y for p in lms])
            x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
            self._last_center = ((x0 + x1) / 2, (y0 + y1) / 2)
            self._last_seen = now
            self._face_box = (float(x0), float(y0), float(x1 - x0), float(y1 - y0))
            shapes = {c.category_name: float(c.score) for c in result.face_blendshapes[idx]}
            matrix = (
                np.array(result.facial_transformation_matrixes[idx])
                if result.facial_transformation_matrixes
                else None
            )
            raw = frame_metrics(shapes, matrix, float(x1 - x0))

            # Blinks: rising edge of closed eyes.
            closed = (shapes.get("eyeBlinkLeft", 0) + shapes.get("eyeBlinkRight", 0)) / 2 > 0.5
            if closed and not self._eyes_closed:
                self._blinks.append(now)
                blinked = True
            self._eyes_closed = closed
            while self._blinks and now - self._blinks[0] > 60:
                self._blinks.popleft()

            # Yawn: mouth wide open for more than 1.5 s.
            if raw["jaw_open"] > 0.55:
                self._jaw_open_since = self._jaw_open_since or now
            else:
                self._jaw_open_since = None
            yawning = self._jaw_open_since is not None and now - self._jaw_open_since > 1.5

            # Head movement: spread of the nose tip over the last 3 s, in face widths.
            nose = lms[1]
            self._nose.append((now, nose.x, nose.y))
            while self._nose and now - self._nose[0][0] > 3:
                self._nose.popleft()
            pts = np.array([(x, y) for _, x, y in self._nose])
            raw["movement"] = float(min(1.0, pts.std(axis=0).sum() / max(1e-3, raw["face_size"]) * 1.5))

            # Light smoothing for display; storage uses the raw per-frame values.
            for k, v in raw.items():
                prev = self._smoothed.get(k, v)
                self._smoothed[k] = prev * 0.6 + v * 0.4
            looking = abs(raw["yaw"]) < 25 and -25 < raw["pitch"] < 20 and raw["gaze_down"] < 0.55
            snap = FaceSnapshot(
                present=True,
                metrics=dict(self._smoothed),
                blink_rate=float(len(self._blinks)),
                looking_at_screen=looking,
                yawning=yawning,
                fps=fps,
                shapes=shapes,
                posture=self._posture,
            )
            pz = self._posture
            if pz.visible and not pz.stale:
                raw.update(neck=pz.neck, shoulder_tilt=pz.shoulder_tilt, lean=pz.lean, sink=pz.sink,
                           shoulder_y=self.posture_analyzer._smooth.get("shoulder_y", 0.0),
                           shoulder_width=self.posture_analyzer._smooth.get("shoulder_width", 0.0))
                if pz.state != "unknown":
                    raw["posture_score"] = pz.score

            # Head-and-shoulders square crop for Clef: face plus room for posture.
            fw, fh = (x1 - x0) * w, (y1 - y0) * h
            side = int(max(fw, fh) * 2.2)
            cx, cy = int((x0 + x1) / 2 * w), int(((y0 + y1) / 2) * h + fh * 0.35)
            sx0, sy0 = max(0, cx - side // 2), max(0, cy - side // 2)
            sx1, sy1 = min(w, sx0 + side), min(h, sy0 + side)
            region = rgb[sy0:sy1, sx0:sx1]
            if region.size and now - self.crop_time >= 0.25:  # the judge samples at most a few per second
                crop = cv2.resize(region, (config.CROP_SIZE, config.CROP_SIZE), interpolation=cv2.INTER_AREA)

            # Portrait "mirror" preview: a 4:5 window that follows the face, eased
            # so it glides instead of jittering, with a faint landmark constellation.
            target = (cx, int((y0 + y1) / 2 * h + fh * 0.55), max(fh * 3.2, fw * 2.8))
            if self._view is None:
                self._view = target
            self._view = tuple(a * 0.85 + b * 0.15 for a, b in zip(self._view, target))
            if want_preview:
                preview = self._portrait(frame_bgr, *self._view)
                vx0, vy0, vw, vh = self._view_box
                for p in lms[::4]:
                    px, py = (p.x * w - vx0) / vw * 720, (p.y * h - vy0) / vh * 600
                    cv2.circle(preview, (int(px), int(py)), 1, (164, 214, 127), -1, cv2.LINE_AA)
            raw["_screen"] = 1.0 if looking else 0.0

        jpeg_bytes = None
        if want_preview:
            if preview is None:
                if self._view is None:
                    self._view = (w / 2, h / 2, h * 0.9)
                preview = self._portrait(frame_bgr, *self._view)
            ok, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 82])
            jpeg_bytes = jpeg.tobytes() if ok else None
            self._last_preview = now
        # The overlay mapping is available even without an MJPEG subscriber.
        cx, cy, height = self._view or (w / 2, h / 2, h * 0.9)
        vh = min(float(h), height, w / 1.2)
        vw = vh * 1.2
        with self.lock:
            self._frame_size = (w, h)
            self._view_box = (min(max(0.0, cx - vw / 2), w - vw), min(max(0.0, cy - vh / 2), h - vh), vw, vh)
            self.snapshot = snap
            if jpeg_bytes is not None:
                self.preview_jpeg = jpeg_bytes
            if crop is not None:
                self.crop, self.crop_time = crop, now
            self.window_frames += 1
            if idx is not None:
                self.window.append(raw)
                self.window_present += 1
            if blinked:
                self.window_blinks += 1
