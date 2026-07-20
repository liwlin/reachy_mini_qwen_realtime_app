"""Hardware-safety limits for generated trajectories.

The daemon rejects unreachable head poses but does NOT rate-limit set_target
streams, and the dance library clamps nothing, so these caps are the actual
safety gate for LLM-generated motion. Values are conservative starting points
derived from the curated dances' parameter envelope; loosen only after
supervised runs on hardware.
"""

from __future__ import annotations
from math import radians
from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyLimits:
    """Caps enforced on every baked trajectory before it may be played."""

    max_position_offset_m: float = 0.04  # per axis, from the neutral head pose
    max_roll_pitch_rad: float = radians(30)
    max_yaw_rad: float = radians(60)
    max_antenna_rad: float = radians(100)
    max_body_yaw_rad: float = radians(120)

    max_translation_velocity_m_s: float = 0.15
    max_head_rotation_velocity_rad_s: float = radians(180)
    max_antenna_velocity_rad_s: float = radians(400)
    max_body_yaw_velocity_rad_s: float = radians(180)

    min_duration_s: float = 0.5
    max_duration_s: float = 30.0

    # First frame must start close to neutral so queuing the move never jumps.
    max_start_position_m: float = 0.02
    max_start_head_angle_rad: float = radians(15)
    max_start_antenna_rad: float = radians(30)


DEFAULT_LIMITS = SafetyLimits()
