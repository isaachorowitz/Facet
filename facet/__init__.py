"""Facet: a local mirror that reads your face and voice through the day."""

import logging
import os

# Set before importing MediaPipe/TensorFlow, including in spawned workers.
os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
