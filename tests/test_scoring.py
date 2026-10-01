import copy

import pytest

from facet.judge import simplify
from facet.posture import score_posture
from facet.voice import is_filler


@pytest.mark.parametrize("changes,lean,score,state,issues", [
    ({}, 1.0, 100, "good", []),
    ({"neck": 0.39}, 1.0, 50, "poor", ["Head dropping forward"]),
    ({"shoulder_tilt": 14}, 1.0, 85, "good", ["Left shoulder low"]),
    ({"shoulder_tilt": -14}, 1.0, 85, "good", ["Right shoulder low"]),
    ({}, 1.72, 70, "fair", ["Leaning into the screen"]),
    ({"shoulder_y": 0.8}, 1.0, 60, "fair", ["Sinking into the chair"]),
    ({"neck": 0, "shoulder_y": 1, "shoulder_tilt": 30}, 2.0, 0, "poor",
     ["Head dropping forward", "Sinking into the chair", "Left shoulder low", "Leaning into the screen"]),
])
def test_posture(changes, lean, score, state, issues):
    reference = {"neck": 0.5, "shoulder_y": 0.5, "shoulder_width": 0.5}
    measured = {**reference, "shoulder_tilt": 0, **changes}
    original = copy.deepcopy((measured, reference))
    assert score_posture(measured, reference, lean) == (score, state, issues)
    assert (measured, reference) == original


def test_no_posture_reference():
    assert score_posture({}, None, 2.0) == (0, "unknown", [])


@pytest.mark.parametrize("text,expected", [
    ("Mm-hmm.", True), ("Uh-huh", True), ("okay", True), ("OK!", True),
    ("uh, um", True), ("", True), ("   ", True),
    ("I am working on the dashboard.", False), ("Okay let's start.", False),
    ("okay okay okay", False), ("Hello", False),
])
def test_filler(text, expected):
    assert is_filler(text) is expected


def test_simplify():
    answers = {
        "smiling": {"type": "noul", "noul": 0.75},
        "expression": {"type": "choice", "choice": "happy", "confidence": 0.8,
                       "probabilities": {"happy": 0.8, "neutral": 0.2}, "extra": "ignored"},
        "stress": {"type": "score", "score": 1.23456},
    }
    original = copy.deepcopy(answers)
    assert simplify(answers) == {
        "smiling": 0.75,
        "expression": {"choice": "happy", "confidence": 0.8,
                       "probabilities": {"happy": 0.8, "neutral": 0.2}},
        "stress": 1.235,
    }
    assert answers == original
    assert simplify({}) == {}
