"""Narrator scheduling, IPC lifecycle and generation contracts with faked inference."""

import os
import queue
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from facet import narrator as module
from facet.narrator import Narrator, NarratorModel, NarratorWorker, clean_caption

FRAME = np.zeros((360, 640, 3), dtype=np.uint8)


def test_caption_is_one_you_sentence_with_at_most_twenty_two_words():
    assert clean_caption('You type at your desk. Someone else walks past.') == 'You type at your desk.'
    assert clean_caption('<think>private reasoning</think>\nYou hold a mug.') == 'You hold a mug.'
    value = clean_caption('You are working ' + 'carefully ' * 30)
    assert len(value.split()) == 22 and value.startswith("You") and value.endswith(".")
    with pytest.raises(ValueError, match="address you"):
        clean_caption("The person is working.")


def test_mlx_template_disables_thinking_greedy_decoding_and_text_mode(monkeypatch):
    generator = Mock(return_value=SimpleNamespace(text="You hold a pen."))
    template = Mock(return_value="formatted prompt")
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace(generate=generator))
    monkeypatch.setitem(sys.modules, "mlx_vlm.prompt_utils", SimpleNamespace(apply_chat_template=template))
    model = NarratorModel.__new__(NarratorModel)
    model.model, model.processor = SimpleNamespace(config={"model_type": "qwen3_5"}), object()
    assert model.generate("Describe", image=FRAME) == "You hold a pen."
    assert template.call_args.kwargs == {"num_images": 1, "enable_thinking": False}
    assert generator.call_args.kwargs["temperature"] == 0.0
    assert generator.call_args.kwargs["max_tokens"] == 48
    assert generator.call_args.kwargs["image"] is FRAME
    model.generate("Recap", max_tokens=320)
    assert template.call_args.kwargs == {"num_images": 0, "enable_thinking": False}
    assert generator.call_args.kwargs["image"] is None
    assert generator.call_args.kwargs["max_tokens"] == 320


def test_caption_uses_full_downscaled_frame_with_no_face_crop():
    model = NarratorModel.__new__(NarratorModel)
    model.generate = Mock(return_value="You hold a mug.")
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:, 0, 0], frame[:, -1, 2] = 255, 255
    assert model.caption(frame) == "You hold a mug."
    image = model.generate.call_args.args[1]
    assert image.size == (640, 360)
    assert np.asarray(image)[0, 0, 0] > 0 and np.asarray(image)[0, -1, 2] > 0
    assert "identity" in model.generate.call_args.args[0]
    assert "present-tense" in model.generate.call_args.args[0]


def test_recap_honesty_prompt_and_word_count_retry():
    model = NarratorModel.__new__(NarratorModel)
    valid = " ".join(["You worked at your desk and took a brief pause."] * 15)
    model.generate = Mock(side_effect=["Too short.", valid])
    result = model.recap({"summary": {"minutes_present": 12}, "marks": [], "notable_captions": [], "nudges": []})
    assert result == valid and 120 <= len(result.split()) <= 180
    assert model.generate.call_count == 2
    prompt = model.generate.call_args.args[0]
    assert '"minutes_present": 12' in prompt
    assert "ONLY facts" in prompt and "untrusted evidence" in prompt
    assert model.generate.call_args.kwargs == {"max_tokens": 320}
    model.generate = Mock(return_value="Too short.")
    with pytest.raises(ValueError, match="120 to 180"):
        model.recap({})


def test_narrator_busy_skips_cycle_without_touching_frames_or_clef():
    get_frame, present, callback = Mock(), Mock(return_value=True), Mock()
    instance = Narrator(get_frame, present, callback)
    instance.worker = Mock()
    instance.busy.acquire()
    try:
        instance.cycle()
        instance.status = "ready"
        with pytest.raises(RuntimeError, match="busy"):
            instance.recap({})
    finally:
        instance.busy.release()
    get_frame.assert_not_called()
    instance.worker.assert_not_called()
    callback.assert_not_called()


def test_narrator_captions_only_present_fresh_frames_and_respects_pause():
    now = time.time()
    callback = Mock()
    frame = Mock(return_value=(FRAME, 123, now, None))
    present = Mock(return_value=False)
    instance = Narrator(frame, present, callback)
    instance.worker = Mock(return_value="You work at your desk.")
    instance.cycle()
    frame.assert_not_called()
    present.return_value = True
    instance.paused.set()
    instance.cycle()
    frame.assert_not_called()
    instance.paused.clear()
    frame.return_value = (FRAME, 123, now - 5, None)
    instance.cycle()
    instance.worker.assert_not_called()
    frame.return_value = (FRAME, 123, now, None)
    instance.cycle()
    assert instance.worker.call_args.args[0][0] == "caption"
    assert instance.worker.call_args.args[0][1] is FRAME
    callback.assert_called_once_with({"ts": now, "text": "You work at your desk."})
    assert not instance.busy.locked()


def test_pause_during_caption_discards_it():
    callback = Mock()
    instance = Narrator(lambda: (FRAME, 1, time.time(), None), lambda: True, callback)

    def generate(request):
        instance.paused.set()
        return "You work."

    instance.worker = Mock(side_effect=generate)
    instance.cycle()
    callback.assert_not_called()


def test_caption_and_recap_failures_release_busy_lock():
    instance = Narrator(lambda: (FRAME, 1, time.time(), None), lambda: True, Mock())
    instance.worker = Mock(side_effect=RuntimeError("synthetic failure"))
    with pytest.raises(RuntimeError):
        instance.cycle()
    assert not instance.busy.locked()
    instance.status = "ready"
    with pytest.raises(RuntimeError):
        instance.recap({})
    assert not instance.busy.locked()


def test_stop_unblocks_narrator_loading_and_closes_its_worker(monkeypatch):
    entered, closed = threading.Event(), threading.Event()
    worker = Mock()

    def loading():
        entered.set()
        assert closed.wait(2)
        raise RuntimeError("Narrator closed")

    worker.wait_ready.side_effect = loading
    worker.close.side_effect = closed.set
    monkeypatch.setattr(module, "NarratorWorker", lambda: worker)
    instance = Narrator(lambda: None, lambda: False, Mock())
    instance.start()
    assert entered.wait(2)
    instance.stop()
    instance.join(2)
    assert not instance.is_alive() and instance.error is None
    assert worker.close.call_count >= 1


def test_narrator_loading_failure_is_reported_and_closed(monkeypatch):
    worker = Mock()
    worker.wait_ready.side_effect = RuntimeError("synthetic load failure")
    monkeypatch.setattr(module, "NarratorWorker", lambda: worker)
    instance = Narrator(lambda: None, lambda: False, Mock())
    instance.run()
    assert instance.status == "failed" and instance.error == "synthetic load failure"
    worker.close.assert_called_once()


def test_worker_detects_exit_or_closed_without_waiting_for_judge():
    worker = NarratorWorker.__new__(NarratorWorker)
    worker.closed, worker._ready = threading.Event(), True
    worker.responses = Mock()
    worker.responses.get.side_effect = queue.Empty
    worker.process = Mock()
    worker.process.is_alive.return_value = False
    with pytest.raises(RuntimeError, match="Narrator worker exited"):
        worker._receive()
    worker.closed.set()
    with pytest.raises(RuntimeError, match="Narrator worker closed"):
        worker._receive()


def synthetic_narrator_worker(requests, responses, repo, parent_pid):
    responses.put(("ready", None))
    while (job := requests.get()) is not None:
        responses.put(("ok", {"operation": job[0], "payload": job[1]}))


def test_narrator_has_own_spawned_process_and_separate_caption_recap_ipc(monkeypatch):
    monkeypatch.setattr(module, "_worker_main", synthetic_narrator_worker)
    # Fixture forbids real model workers; use the imported original class with a fake child target.
    worker = NarratorWorker()
    try:
        assert worker.process.pid != os.getpid()
        assert worker.process.name == "facet-narrator"
        assert worker(("caption", "synthetic frame")) == {"operation": "caption", "payload": "synthetic frame"}
        assert worker(("recap", {"date": "2026-09-30"})) == {"operation": "recap", "payload": {"date": "2026-09-30"}}
    finally:
        worker.close()
    assert not worker.process.is_alive() and worker.process.exitcode == 0


def test_long_caption_keeps_a_complete_clause_instead_of_a_dangling_preposition():
    raw = "You sit at a desk, wearing a sleeveless top and holding a pen, with a laptop displaying a webpage in front of you."
    assert clean_caption(raw) == "You sit at a desk, wearing a sleeveless top and holding a pen."
