"""Tests for the subprocess baker."""

import os

import pytest

from reachy_mini_conversation_app.choreographer.bake import BakeError, bake_source
from reachy_mini_conversation_app.choreographer.validator import validate_trajectory

NOD_SOURCE = """
def move(t_beats):
    params = OscillationParams(amplitude=0.15, subcycles_per_beat=1.0)
    return atomic_pitch(t_beats, params)
"""


def test_simple_nod_bakes_to_valid_trajectory():
    move = bake_source(NOD_SOURCE, bpm=120, duration_beats=4)
    assert len(move["time"]) == int(2.0 * 50) + 1  # 4 beats at 120 bpm = 2 s
    assert validate_trajectory(move) == []


def test_plain_math_source_works_without_library_helpers():
    source = """
import math

def move(t_beats):
    wave = 0.1 * math.sin(2 * math.pi * t_beats)
    return MoveOffsets(
        position_offset=np.array([0.0, 0.0, 0.0]),
        orientation_offset=np.array([wave, 0.0, 0.0]),
        antennas_offset=np.array([wave, -wave]),
    )
"""
    move = bake_source(source, bpm=60, duration_beats=2)
    assert validate_trajectory(move) == []


def test_hanging_source_times_out():
    with pytest.raises(BakeError, match="timed out"):
        bake_source("while True:\n    pass", bpm=120, duration_beats=4, timeout_s=3)


def test_syntax_error_reports_stderr():
    with pytest.raises(BakeError, match="SyntaxError"):
        bake_source("def move(t_beats)\n    return None", bpm=120, duration_beats=4)


def test_missing_move_function_rejected():
    with pytest.raises(BakeError, match="must define"):
        bake_source("x = 1", bpm=120, duration_beats=4)


def test_worker_environment_is_scrubbed(monkeypatch):
    monkeypatch.setenv("MY_SECRET_TOKEN", "hunter2")
    source = """
import os

def move(t_beats):
    raise RuntimeError("env=" + ",".join(sorted(os.environ)))
"""
    with pytest.raises(BakeError) as excinfo:
        bake_source(source, bpm=120, duration_beats=4)
    assert "MY_SECRET_TOKEN" not in str(excinfo.value)
    assert os.environ["MY_SECRET_TOKEN"] == "hunter2"


def test_printing_source_rejected_cleanly():
    source = """
def move(t_beats):
    print("noise")
    return atomic_pitch(t_beats, OscillationParams(amplitude=0.1))
"""
    with pytest.raises(BakeError, match="must not print"):
        bake_source(source, bpm=120, duration_beats=1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
