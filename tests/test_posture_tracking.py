"""Regression for stale face centres, dropout hysteresis and score smoothing."""

from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from facet.face import FaceTracker
from facet.posture import L_SH, R_SH, PostureAnalyzer

FRAME = np.zeros((360, 640, 3), dtype=np.uint8)


def pose(cx=0.5, width=0.4, head_y=0.2):
    points = [SimpleNamespace(x=cx, y=head_y, visibility=1.0) for _ in range(33)]
    points[L_SH] = SimpleNamespace(x=cx + width / 2, y=0.6, visibility=1.0)
    points[R_SH] = SimpleNamespace(x=cx - width / 2, y=0.6, visibility=1.0)
    return points


@pytest.fixture
def analyzer(monkeypatch):
    from facet import posture

    detector = Mock()
    detector.detect_for_video.return_value = SimpleNamespace(pose_landmarks=[pose()])
    factory = Mock(return_value=detector)
    monkeypatch.setattr(posture.vision.PoseLandmarker, "create_from_options", factory)
    instance = PostureAnalyzer()
    options = factory.call_args.args[0]
    assert options.num_poses == 2
    assert options.running_mode == posture.vision.RunningMode.VIDEO
    assert options.base_options.delegate == posture.BaseOptions.Delegate.CPU
    instance.set_reference({"neck": 0.4 / (0.4 * 16 / 9), "shoulder_y": 0.6, "shoulder_width": 0.4 * 16 / 9})
    yield instance
    instance.close()
    detector.close.assert_called_once()


def update(instance, now=10.0, seen=None, center=(0.1, 0.1), face_size=0.2):
    return instance.update(FRAME, int(now * 1000), center, face_size, 0.2, seen, now=now)


def test_stale_face_center_reproduces_old_rejection_and_now_accepts(analyzer):
    # Nose is over .12 from the old face location after turning/looking down.
    assert np.hypot(0.5 - 0.1, 0.2 - 0.1) > 0.12
    assert not update(analyzer, seen=10).visible  # a FRESH different face is still gated
    fixed = update(analyzer, now=11, seen=10)
    assert fixed.visible and not fixed.stale and fixed.score == 100
    assert fixed.skeleton["nose"][:2] == [round(0.5 * 16 / 9, 4), 0.2]


@pytest.mark.parametrize("age,visible", [(0, False), (0.5, False), (0.5001, True), (5, True)])
def test_half_second_freshness_boundary(analyzer, age, visible):
    assert update(analyzer, seen=10 - age).visible is visible


def test_missing_face_timestamp_does_not_gate(analyzer):
    assert update(analyzer).visible


@pytest.mark.parametrize("failure", ["missing", "other_person", "shoulders", "degenerate"])
def test_hold_keeps_entire_posture_for_three_seconds(analyzer, failure):
    good = update(analyzer, seen=10, center=(0.5, 0.2))
    expected = asdict(good)
    if failure == "missing":
        analyzer.landmarker.detect_for_video.return_value.pose_landmarks = []
    elif failure == "shoulders":
        analyzer.landmarker.detect_for_video.return_value.pose_landmarks[0][L_SH].visibility = 0.2
    elif failure == "degenerate":
        analyzer.landmarker.detect_for_video.return_value.pose_landmarks = [pose(width=0)]
    for now in (10.1, 11, 13):
        held = update(analyzer, now=now, seen=now, center=(0.1, 0.1) if failure == "other_person" else (0.5, 0.2))
        assert asdict(held) == {**expected, "stale": True}
    expired = update(analyzer, now=13.001, seen=13.001)
    assert not expired.visible and not expired.stale and expired.skeleton == {}


def test_pose_reacquisition_clears_stale_and_refreshes_hold(analyzer):
    update(analyzer)
    analyzer.miss(12)
    fresh = update(analyzer, now=12.5)
    assert fresh.visible and not fresh.stale
    assert analyzer.miss(15.5).visible
    assert not analyzer.miss(15.501).visible


def test_score_ema_prevents_one_frame_score_jump(analyzer):
    assert update(analyzer).score == 100
    changed = update(analyzer, now=10.1, face_size=0.344)
    assert changed.score == 91  # raw lean score 70, EMA alpha .3
    assert changed.state == "good"
    assert update(analyzer, now=10.2, face_size=0.344).score == 84.7


def test_stale_face_chooses_central_large_pose(analyzer):
    analyzer.landmarker.detect_for_video.return_value.pose_landmarks = [pose(cx=0.08, width=0.15), pose(cx=0.55, width=0.4)]
    chosen = update(analyzer)
    assert chosen.visible
    assert chosen.skeleton["nose"][0] == round(0.55 * 16 / 9, 4)
    chosen = update(analyzer, now=11, center=(0.08, 0.2), seen=11)
    assert chosen.skeleton["nose"][0] == round(0.08 * 16 / 9, 4)


def test_camera_records_face_timestamp_and_normalized_view_without_preview():
    face = FaceTracker()
    lms = [SimpleNamespace(x=0.4, y=0.2), SimpleNamespace(x=0.6, y=0.4)]
    result = SimpleNamespace(face_landmarks=[lms], face_blendshapes=[[]], facial_transformation_matrixes=[])
    face._process(result, FRAME, FRAME, 10, 30)
    assert face._last_seen == 10
    assert face._last_center == pytest.approx((0.5, 0.3))
    assert face._face_box == pytest.approx((0.4, 0.2, 0.2, 0.2))
    view = face.view()
    assert all(0 <= v <= 1 for v in view.values())
    assert view["x"] + view["w"] <= 1
    assert view["y"] + view["h"] <= 1
    assert face.preview_jpeg is None
    result.face_landmarks = []
    face._process(result, FRAME, FRAME, 11, 30)
    assert face._last_seen == 10  # missed frames do not refresh the timestamp
    assert not face.get_snapshot().present


def test_snapshot_uses_current_pose_even_when_camera_stalls():
    from facet.posture import Posture

    face = FaceTracker()
    face._posture = Posture(visible=True, score=80, state="good")
    assert face.get_snapshot().posture.score == 80
    face._posture = Posture(visible=True, score=80, state="good", stale=True)
    assert face.get_snapshot().posture.stale
    face._posture = Posture()
    assert not face.get_snapshot().posture.visible
    face.paused.set()
    assert not face.get_snapshot().present
