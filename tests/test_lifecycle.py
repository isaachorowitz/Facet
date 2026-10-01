"""Exercise resource ownership with fakes, never camera/mic/model hardware."""

import logging
import os
import queue
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from facet import configure_logging, judge
from facet.app import Hub
from facet.face import FaceTracker
from facet.judge import ClefWorker, Judge
from facet.voice import VoiceListener


def test_face_failure_releases_camera_landmarkers_and_pose(monkeypatch):
    face = FaceTracker()
    camera, landmarker, posture = Mock(), Mock(), Mock()
    pose = threading.Thread(target=lambda: face.stopped.wait(2))

    def fail():
        face._capture, face._landmarker = camera, landmarker
        face.posture_analyzer, face._pose_thread = posture, pose
        face.camera_on = True
        pose.start()
        raise RuntimeError("synthetic frame failure")

    monkeypatch.setattr(face, "_capture_frames", fail)
    face.start()
    face.join(2)
    assert not face.is_alive() and not pose.is_alive()
    assert face.stopped.is_set() and not face.camera_on
    assert face.error == "RuntimeError: synthetic frame failure"
    camera.release.assert_called_once()
    landmarker.close.assert_called_once()
    posture.close.assert_called_once()


def test_face_cleanup_continues_if_release_fails(monkeypatch):
    face = FaceTracker()
    face._capture = Mock()
    face._capture.release.side_effect = RuntimeError("synthetic release failure")
    face._landmarker = Mock()
    face.posture_analyzer = Mock()
    monkeypatch.setattr(face, "_capture_frames", lambda: None)
    face.run()
    face._landmarker.close.assert_called_once()
    face.posture_analyzer.close.assert_called_once()
    assert face.error == "cleanup: synthetic release failure"


@pytest.mark.parametrize("fail", [False, True])
def test_voice_stop_or_failure_closes_stream_and_analysis(monkeypatch, fail):
    from facet import voice as module

    voice = VoiceListener(lambda seg: None)
    opened = threading.Event()
    stream = Mock()
    stream.start.side_effect = opened.set
    monkeypatch.setattr(voice, "_analyze_loop", lambda: voice.stopped.wait(2))
    monkeypatch.setattr(module, "pick_input_device", lambda: 0)
    monkeypatch.setattr(module.sd, "query_devices", lambda device: {"name": "Synthetic mic"})
    monkeypatch.setattr(module.sd, "InputStream", lambda **kwargs: stream)
    if fail:
        voice.blocks.get = Mock(side_effect=RuntimeError("synthetic audio failure"))
    voice.start()
    assert opened.wait(2)
    if fail:
        # run() finishes cleanup on failure without waiting for Hub.stop().
        voice.join(2)
    voice.stop()
    voice.join(2)
    assert not voice.is_alive() and not voice.analysis_thread.is_alive()
    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert not voice.speaking
    if fail:
        assert voice.error == "mic: synthetic audio failure"


def test_judge_stop_unblocks_loading_and_closes_worker(monkeypatch):
    entered, closed = threading.Event(), threading.Event()
    worker = Mock()

    def infer(request):
        entered.set()
        assert closed.wait(2)
        raise RuntimeError("Clef worker closed")

    worker.wait_ready.side_effect = lambda: infer({})
    worker.side_effect = infer
    worker.close.side_effect = closed.set
    monkeypatch.setattr(judge, "_load_clef", lambda: worker)
    instance = Judge(lambda: (None, 0), lambda *args: None)
    instance.start()
    assert entered.wait(2)
    instance.stop()
    instance.join(2)
    assert not instance.is_alive() and closed.is_set()
    assert instance.error is None
    assert worker.close.call_count >= 1


def test_judge_warmup_failure_is_surfaced_and_closed(monkeypatch):
    worker = Mock(side_effect=RuntimeError("synthetic model failure"))
    monkeypatch.setattr(judge, "_load_clef", lambda: worker)
    instance = Judge(lambda: (None, 0), lambda *args: None)
    instance.run()
    assert instance.status == "failed"
    assert instance.error == "RuntimeError: synthetic model failure"
    worker.close.assert_called_once()


def test_hub_joins_workers_and_background_tasks_before_closing_store(monkeypatch):
    hub = Hub()
    # Headless construction only; cooperative fake threads stand in for hardware.
    workers = [SimpleNamespace(stopped=threading.Event()) for _ in range(3)]
    for worker in workers:
        worker.thread = threading.Thread(target=lambda worker=worker: worker.stopped.wait(2))
        worker.stop = worker.stopped.set
        worker.join = worker.thread.join
        worker.thread.start()
        worker.ident = worker.thread.ident
    hub.face, hub.judge, hub.voice = workers
    hub.start_background(lambda: hub.stopped.wait(2), "synthetic-window")
    hub.stop()
    assert all(not w.thread.is_alive() for w in workers)
    assert all(not t.is_alive() for t in hub.background_threads)
    hub.stop()  # idempotent, including Store.close
    with pytest.raises(Exception, match="closed database"):
        hub.store._query("SELECT 1")


@pytest.mark.parametrize("escalation", ["none", "terminate", "kill"])
def test_clef_close_escalates_only_its_process_and_closes_queues(escalation):
    worker = ClefWorker.__new__(ClefWorker)
    worker.closed = threading.Event()
    worker._close_lock = threading.Lock()
    worker.requests, worker.responses = Mock(), Mock()
    worker.process = Mock()
    worker.process.is_alive.side_effect = {
        "none": [False, False], "terminate": [True, False], "kill": [True, True],
    }[escalation]
    worker.close()
    worker.close()
    worker.requests.put.assert_called_once_with(None)
    assert worker.process.terminate.call_count == (escalation != "none")
    assert worker.process.kill.call_count == (escalation == "kill")
    for channel in (worker.requests, worker.responses):
        channel.cancel_join_thread.assert_called_once()
        channel.close.assert_called_once()


def test_clef_receive_detects_exit_and_shutdown():
    worker = ClefWorker.__new__(ClefWorker)
    worker.closed = threading.Event()
    worker.responses = Mock()
    worker.responses.get.side_effect = queue.Empty
    worker.process = Mock()
    worker.process.is_alive.return_value = False
    with pytest.raises(RuntimeError, match="process exited"):
        worker._receive()
    worker.closed.set()
    with pytest.raises(RuntimeError, match="worker closed"):
        worker._receive()


def test_parent_watchdog_exits_when_parent_changes(monkeypatch):
    parents = iter([123, 123, 1])
    monkeypatch.setattr(judge.os, "getppid", lambda: next(parents))
    monkeypatch.setattr(judge.time, "sleep", lambda seconds: None)
    exit_call = Mock(side_effect=SystemExit(0))
    monkeypatch.setattr(judge.os, "_exit", exit_call)
    with pytest.raises(SystemExit):
        judge._watch_parent(123)
    exit_call.assert_called_once_with(0)


def synthetic_worker(requests, responses, repo, backend, device, parent_pid):
    """Spawn target with the same IPC/lifecycle but no Clef or model imports."""
    from facet.judge import _watch_parent

    threading.Thread(target=_watch_parent, args=(parent_pid,), daemon=True).start()
    responses.put(("ready", None))
    while (request := requests.get()) is not None:
        responses.put(("ok", {"answers": request}))


def test_spawned_worker_ipc_and_graceful_exit(monkeypatch):
    monkeypatch.setattr(judge, "_worker_main", synthetic_worker)
    worker = ClefWorker()
    try:
        assert worker.process.pid != os.getpid()
        assert worker({"synthetic": True}) == {"answers": {"synthetic": True}}
    finally:
        worker.close()
    assert not worker.process.is_alive()
    assert worker.process.exitcode == 0


def test_cli_overrides_and_config_defaults(monkeypatch):
    from facet import app as module

    run = Mock()
    browser = Mock()
    monkeypatch.setattr(module.uvicorn, "run", run)
    monkeypatch.setattr(module.webbrowser, "open", browser)
    monkeypatch.setattr("sys.argv", ["facet", "--host", "127.0.0.2", "--port", "8799", "--no-browser"])
    module.main()
    assert run.call_args.kwargs["host"] == "127.0.0.2"
    assert run.call_args.kwargs["port"] == 8799
    browser.assert_not_called()
    monkeypatch.setattr("sys.argv", ["facet", "--no-browser"])
    module.main()
    assert run.call_args.kwargs["host"] == module.config.HOST
    assert run.call_args.kwargs["port"] == module.config.PORT


def test_logging_is_idempotent_and_native_log_levels_are_set(monkeypatch):
    root = logging.getLogger()
    original = root.handlers[:]
    try:
        root.handlers = []
        configure_logging()
        configure_logging()
        assert len(root.handlers) == 1
        assert "%(asctime)s" in root.handlers[0].formatter._fmt
    finally:
        for handler in root.handlers:
            if handler not in original:
                handler.close()
        root.handlers = original
    assert os.environ["GLOG_minloglevel"] == "2"
    assert os.environ["TF_CPP_MIN_LOG_LEVEL"] == "2"
