"""Shared helpers for choreographer tests."""

import math

import pytest

from reachy_mini.utils import create_head_pose

FPS = 50.0


def build_move(duration_s=4.0, pos_amp=0.02, angle_amp=math.radians(15), antenna_amp=math.radians(45), freq_hz=1.0):
    """Build a gentle sinusoidal trajectory in the RecordedMove dict shape."""
    n = int(duration_s * FPS) + 1
    time = [i / FPS for i in range(n)]
    frames = []
    for t in time:
        s = math.sin(2 * math.pi * freq_hz * t)
        head = create_head_pose(0.0, pos_amp * s, 0.0, 0.0, angle_amp * s, 0.0, degrees=False)
        frames.append(
            {
                "head": head.tolist(),
                "antennas": [antenna_amp * s, -antenna_amp * s],
                "body_yaw": 0.0,
            }
        )
    return {"description": "test move", "time": time, "set_target_data": frames}


@pytest.fixture
def make_move():
    """Factory fixture for gentle test trajectories."""
    return build_move
