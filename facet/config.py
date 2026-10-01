"""Runtime settings. Override any of them with FACET_* environment variables."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("FACET_DATA", Path.home() / "Library/Application Support/Facet"))
DB_PATH = DATA_DIR / "facet.db"
FACE_MODEL = ROOT / "models" / "face_landmarker.task"
POSE_MODEL = ROOT / "models" / "pose_landmarker_lite.task"
HAND_MODEL = ROOT / "models" / "gesture_recognizer.task"
MEDIAPIPE_MODELS = {
    HAND_MODEL: "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/latest/gesture_recognizer.task",
    FACE_MODEL: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task",
    POSE_MODEL: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
}


def ensure_models() -> None:
    """Download the MediaPipe models on first run; they are not checked in."""
    import urllib.request

    for path, url in MEDIAPIPE_MODELS.items():
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            urllib.request.urlretrieve(url, tmp)
            tmp.rename(path)

HOST = os.environ.get("FACET_HOST", "127.0.0.1")
PORT = int(os.environ.get("FACET_PORT", "8765"))

CAMERA_INDEX = int(os.environ.get("FACET_CAMERA", "0"))
CAMERA_WIDTH, CAMERA_HEIGHT = 1280, 720

# Mic: first input device whose name contains one of these, else the system default.
MIC_PREFERENCE = [s for s in os.environ.get("FACET_MIC", "Seiren,MX Brio").split(",") if s]

CLEF_REPO = os.environ.get("FACET_CLEF", "Cloudflare/clef-flash")
CLEF_DEVICE = os.environ.get("FACET_DEVICE", "mps")  # where the small head runs
CLEF_BACKEND = os.environ.get("FACET_BACKEND", "mlx")  # mlx (fast) or torch (the release code path)
CROP_SIZE = int(os.environ.get("FACET_CROP", "384"))
FACE_JUDGE_INTERVAL = float(os.environ.get("FACET_JUDGE_INTERVAL", "1.2"))
OVERALL_INTERVAL = 15.0

PARAKEET_REPO = "mlx-community/parakeet-tdt-0.6b-v3"
VOICE_EMOTION_REPO = "superb/hubert-large-superb-er"

FACE_WINDOW_SECONDS = 5.0  # one stored face-metric row per window
BREAK_GAP_SECONDS = 180  # absence longer than this counts as a break

NARRATOR_REPO = os.environ.get("FACET_NARRATOR", "mlx-community/Qwen3.5-9B-MLX-4bit")
CAPTION_INTERVAL = 12.0
