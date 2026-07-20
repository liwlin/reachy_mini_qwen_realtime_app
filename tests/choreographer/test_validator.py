"""Tests for the trajectory safety validator."""

import math

import numpy as np
import pytest

from reachy_mini.utils import create_head_pose
from reachy_mini_conversation_app.choreographer.limits import DEFAULT_LIMITS
from reachy_mini_conversation_app.choreographer.validator import validate_trajectory


def test_gentle_move_passes(make_move):
    """Check gentle move passes."""
    assert validate_trajectory(make_move()) == []


def test_excessive_position_amplitude_rejected(make_move):
    """Check excessive position amplitude rejected."""
    violations = validate_trajectory(make_move(pos_amp=0.09, freq_hz=0.2))
    assert any("head y offset" in v for v in violations)


def test_excessive_rotation_velocity_rejected(make_move):
    """Check excessive rotation velocity rejected."""
    violations = validate_trajectory(make_move(angle_amp=math.radians(29), freq_hz=6.0))
    assert any("rotation velocity" in v for v in violations)


def test_non_finite_values_rejected(make_move):
    """Check non finite values rejected."""
    move = make_move()
    move["set_target_data"][3]["antennas"][0] = float("nan")
    violations = validate_trajectory(move)
    assert any("non-finite" in v for v in violations)


def test_offset_start_pose_rejected(make_move):
    """Check offset start pose rejected."""
    move = make_move()
    bad = create_head_pose(0.0, 0.03, 0.0, 0.0, 0.0, 0.0, degrees=False)
    move["set_target_data"][0]["head"] = bad.tolist()
    violations = validate_trajectory(move)
    assert any("first frame" in v for v in violations)


def test_too_short_move_rejected(make_move):
    """Check too short move rejected."""
    violations = validate_trajectory(make_move(duration_s=0.2))
    assert any("below the minimum" in v for v in violations)


def test_too_long_move_rejected(make_move):
    """Check too long move rejected."""
    violations = validate_trajectory(make_move(duration_s=DEFAULT_LIMITS.max_duration_s + 5, freq_hz=0.5))
    assert any("exceeds the maximum" in v for v in violations)


def test_structure_errors_reported(make_move):
    """Check structure errors reported."""
    assert validate_trajectory({"time": [0, 1]}) == ["move must contain 'time' and 'set_target_data' lists"]
    move = make_move()
    move["time"] = move["time"][:-1]
    assert "entries" in validate_trajectory(move)[0]


def test_non_monotonic_time_rejected(make_move):
    """Check non monotonic time rejected."""
    move = make_move()
    move["time"][5] = move["time"][4]
    assert validate_trajectory(move) == ["'time' must be strictly increasing"]


def test_missing_body_yaw_defaults_to_zero(make_move):
    """Check missing body yaw defaults to zero."""
    move = make_move()
    for frame in move["set_target_data"]:
        frame["body_yaw"] = None
    assert validate_trajectory(move) == []


def test_np_arrays_accepted_in_frames(make_move):
    """Check np arrays accepted in frames."""
    move = make_move()
    for frame in move["set_target_data"]:
        frame["head"] = np.array(frame["head"])
    assert validate_trajectory(move) == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
