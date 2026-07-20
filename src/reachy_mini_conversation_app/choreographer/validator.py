"""Numeric validation of baked trajectories against SafetyLimits.

Operates purely on the RecordedMove-shaped dict produced by the baker:
``{"description": str, "time": [...], "set_target_data": [{"head": 4x4,
"antennas": [l, r], "body_yaw": float}, ...]}``. Returns human/LLM-readable
violation strings; an empty list means the trajectory is safe to play.
"""

from __future__ import annotations
from math import degrees
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial.transform import Rotation

from reachy_mini_conversation_app.choreographer.limits import DEFAULT_LIMITS, SafetyLimits


def _fmt(value: float, unit: str) -> str:
    """Format a magnitude with its unit for violation messages."""
    if unit == "deg":
        return f"{degrees(value):.0f}deg"
    return f"{value:.3f}{unit}"


def _extract_channels(
    frames: list[dict[str, Any]],
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Split frames into positions (N,3), head euler angles (N,3), antennas (N,2), body yaw (N,)."""
    heads = np.array([frame["head"] for frame in frames], dtype=np.float64)
    positions = heads[:, :3, 3]
    angles = Rotation.from_matrix(heads[:, :3, :3]).as_euler("xyz")
    antennas = np.array([frame["antennas"] for frame in frames], dtype=np.float64)
    body_yaw = np.array([frame.get("body_yaw") or 0.0 for frame in frames], dtype=np.float64)
    return positions, angles, antennas, body_yaw


def _check_structure(move: dict[str, Any]) -> list[str]:
    """Validate the container shape before any numeric checks."""
    violations: list[str] = []
    time = move.get("time")
    frames = move.get("set_target_data")
    if not isinstance(time, list) or not isinstance(frames, list):
        return ["move must contain 'time' and 'set_target_data' lists"]
    if len(time) != len(frames):
        return [f"'time' has {len(time)} entries but 'set_target_data' has {len(frames)}"]
    if len(time) < 2:
        return ["trajectory needs at least 2 frames"]
    for index, frame in enumerate(frames):
        head = np.asarray(frame.get("head", []), dtype=object)
        antennas = frame.get("antennas")
        if head.shape != (4, 4):
            violations.append(f"frame {index}: 'head' must be a 4x4 matrix")
        if not (isinstance(antennas, (list, tuple)) and len(antennas) == 2):
            violations.append(f"frame {index}: 'antennas' must be [left, right]")
        if violations:
            return violations
    return violations


def _check_peaks(
    positions: NDArray[np.float64],
    angles: NDArray[np.float64],
    antennas: NDArray[np.float64],
    body_yaw: NDArray[np.float64],
    limits: SafetyLimits,
) -> list[str]:
    """Cap absolute offsets per channel."""
    violations: list[str] = []
    checks: list[tuple[str, float, float, str]] = [
        ("head x offset", float(np.abs(positions[:, 0]).max()), limits.max_position_offset_m, "m"),
        ("head y offset", float(np.abs(positions[:, 1]).max()), limits.max_position_offset_m, "m"),
        ("head z offset", float(np.abs(positions[:, 2]).max()), limits.max_position_offset_m, "m"),
        ("head roll", float(np.abs(angles[:, 0]).max()), limits.max_roll_pitch_rad, "deg"),
        ("head pitch", float(np.abs(angles[:, 1]).max()), limits.max_roll_pitch_rad, "deg"),
        ("head yaw", float(np.abs(angles[:, 2]).max()), limits.max_yaw_rad, "deg"),
        ("antennas", float(np.abs(antennas).max()), limits.max_antenna_rad, "deg"),
        ("body yaw", float(np.abs(body_yaw).max()), limits.max_body_yaw_rad, "deg"),
    ]
    for channel, peak, cap, unit in checks:
        if peak > cap:
            violations.append(f"{channel} peaks at {_fmt(peak, unit)}, limit {_fmt(cap, unit)}")
    return violations


def _check_velocities(
    time: NDArray[np.float64],
    positions: NDArray[np.float64],
    angles: NDArray[np.float64],
    antennas: NDArray[np.float64],
    body_yaw: NDArray[np.float64],
    limits: SafetyLimits,
) -> list[str]:
    """Cap frame-to-frame rates; this is what the daemon does not enforce."""
    violations: list[str] = []
    dt = np.diff(time)
    translation_vel = float((np.abs(np.diff(positions, axis=0)) / dt[:, None]).max())
    # Angle diffs wrapped to [-pi, pi] so a sawtooth yaw doesn't fake a huge velocity.
    angle_steps = np.arctan2(np.sin(np.diff(angles, axis=0)), np.cos(np.diff(angles, axis=0)))
    head_rot_vel = float((np.abs(angle_steps) / dt[:, None]).max())
    antenna_vel = float((np.abs(np.diff(antennas, axis=0)) / dt[:, None]).max())
    body_yaw_vel = float((np.abs(np.diff(body_yaw)) / dt).max())

    checks: list[tuple[str, float, float, str]] = [
        ("head translation velocity", translation_vel, limits.max_translation_velocity_m_s, "m/s"),
        ("head rotation velocity", head_rot_vel, limits.max_head_rotation_velocity_rad_s, "deg"),
        ("antenna velocity", antenna_vel, limits.max_antenna_velocity_rad_s, "deg"),
        ("body yaw velocity", body_yaw_vel, limits.max_body_yaw_velocity_rad_s, "deg"),
    ]
    for channel, peak, cap, unit in checks:
        if peak > cap:
            if unit == "deg":
                violations.append(f"{channel} peaks at {degrees(peak):.0f}deg/s, limit {degrees(cap):.0f}deg/s")
            else:
                violations.append(f"{channel} peaks at {peak:.3f}{unit}, limit {cap:.3f}{unit}")
    return violations


def _check_start_pose(
    positions: NDArray[np.float64],
    angles: NDArray[np.float64],
    antennas: NDArray[np.float64],
    limits: SafetyLimits,
) -> list[str]:
    """Require the first frame to be near neutral so queuing the move never jerks."""
    violations: list[str] = []
    start_pos = float(np.abs(positions[0]).max())
    start_angle = float(np.abs(angles[0]).max())
    start_antenna = float(np.abs(antennas[0]).max())
    if start_pos > limits.max_start_position_m:
        violations.append(
            f"first frame starts {_fmt(start_pos, 'm')} from neutral, limit {_fmt(limits.max_start_position_m, 'm')};"
            " start the move at the neutral pose (all offsets 0 at t=0)"
        )
    if start_angle > limits.max_start_head_angle_rad:
        violations.append(
            f"first frame head angle is {_fmt(start_angle, 'deg')} from neutral,"
            f" limit {_fmt(limits.max_start_head_angle_rad, 'deg')}; start the move at the neutral pose"
        )
    if start_antenna > limits.max_start_antenna_rad:
        violations.append(
            f"first frame antennas are {_fmt(start_antenna, 'deg')} from neutral,"
            f" limit {_fmt(limits.max_start_antenna_rad, 'deg')}; start the move at the neutral pose"
        )
    return violations


def validate_trajectory(move: dict[str, Any], limits: SafetyLimits = DEFAULT_LIMITS) -> list[str]:
    """Check a baked trajectory against safety limits.

    Returns a list of violation messages; an empty list means the move is safe.
    Messages are written to be fed back to the codegen LLM verbatim.
    """
    violations = _check_structure(move)
    if violations:
        return violations

    time = np.asarray(move["time"], dtype=np.float64)
    frames: list[dict[str, Any]] = move["set_target_data"]

    if not np.all(np.isfinite(time)):
        return ["'time' contains non-finite values"]
    if np.any(np.diff(time) <= 0):
        return ["'time' must be strictly increasing"]

    try:
        positions, angles, antennas, body_yaw = _extract_channels(frames)
    except (ValueError, TypeError) as error:
        return [f"could not parse frames as numeric data: {error}"]

    for name, array in (
        ("head", positions),
        ("antennas", antennas),
        ("body_yaw", body_yaw),
    ):
        if not np.all(np.isfinite(array)):
            return [f"'{name}' contains non-finite values (NaN or inf)"]

    duration = float(time[-1] - time[0])
    if duration < limits.min_duration_s:
        violations.append(f"duration {duration:.2f}s is below the minimum {limits.min_duration_s:.1f}s")
    if duration > limits.max_duration_s:
        violations.append(f"duration {duration:.1f}s exceeds the maximum {limits.max_duration_s:.0f}s")

    violations.extend(_check_peaks(positions, angles, antennas, body_yaw, limits))
    violations.extend(_check_velocities(time, positions, angles, antennas, body_yaw, limits))
    violations.extend(_check_start_pose(positions, angles, antennas, limits))
    return violations
