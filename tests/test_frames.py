"""The shared mailbox stays bounded and keeps 15 Hz on real camera cadences."""

import numpy as np
import pytest

from facet.frames import FrameFeed


@pytest.mark.parametrize("fps", [29, 30, 31, 60])
def test_shared_frames_are_sampled_at_fifteen_hz_without_camera_cadence_rounding(fps):
    feed = FrameFeed()
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    published = 0
    for i in range(fps * 10):
        published += feed.publish(rgb, i + 1, 1000 + i / fps, (0.4, 0.2, 0.2, 0.2), (0.5, 0.3), 1000 + i / fps)
    assert 149 <= published <= 151
    latest, pose = feed.latest(), feed.latest_pose()
    assert latest[0].shape == (360, 640, 3)
    assert latest[0] is pose[0]  # one resize; identical full frame for every consumer
    assert latest[1:3] == pose[1:3]
    assert pose[3:] == ((0.5, 0.3), pose[2])


def test_mailbox_clears_on_pause_and_skips_catchup_after_a_gap():
    feed = FrameFeed()
    rgb = np.zeros((360, 640, 3), dtype=np.uint8)
    assert feed.publish(rgb, 1, 1000, None, None, None)
    frame = feed.latest()
    assert not feed.publish(rgb, 2, 1000.02, None, None, None)
    assert feed.latest() is frame
    feed.clear()
    assert feed.latest() is None and feed.latest_pose() is None
    assert feed.publish(rgb, 3, 1500, None, None, None)
    assert not feed.publish(rgb, 4, 1500.02, None, None, None)
