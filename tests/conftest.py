"""Isolate every test from the live database, hardware and models."""

import os
import tempfile

import pytest

# This happens before test-module imports or any Hub/Store can be constructed.
_session_data = tempfile.TemporaryDirectory(prefix="facet-tests-")
os.environ["FACET_DATA"] = _session_data.name
os.environ["FACET_HEADLESS"] = "1"

from facet import config
from facet.store import Store


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    from facet import face, judge, voice, narrator

    monkeypatch.setenv("FACET_DATA", str(tmp_path))
    monkeypatch.setenv("FACET_HEADLESS", "1")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "facet.db")

    def forbidden(*args, **kwargs):
        pytest.fail("Tests must never start hardware, download models or load Clef")

    monkeypatch.setattr(config, "ensure_models", forbidden)
    monkeypatch.setattr(face.cv2, "VideoCapture", forbidden)
    monkeypatch.setattr(face.vision.FaceLandmarker, "create_from_options", forbidden)
    monkeypatch.setattr(face.vision.PoseLandmarker, "create_from_options", forbidden)
    monkeypatch.setattr(face.vision.GestureRecognizer, "create_from_options", forbidden)
    monkeypatch.setattr(narrator, "NarratorWorker", forbidden)
    monkeypatch.setattr(narrator, "NarratorModel", forbidden)
    monkeypatch.setattr(voice.sd, "InputStream", forbidden)
    monkeypatch.setattr(voice.sd, "query_devices", forbidden)
    monkeypatch.setattr(judge, "_load_clef", forbidden)
    monkeypatch.setattr(voice.VoiceListener, "_analyze_loop", forbidden)


@pytest.fixture
def store():
    instance = Store()
    yield instance
    instance.close()


def pytest_sessionfinish(session, exitstatus):
    _session_data.cleanup()
