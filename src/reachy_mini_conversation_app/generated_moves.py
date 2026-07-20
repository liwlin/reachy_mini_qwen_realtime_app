"""Queue-move wrapper for LLM-generated trajectories.

Mirrors EmotionQueueMove: wraps the SDK RecordedMove parser around a baked
trajectory dict so generated moves are ordinary citizens of the
MovementManager queue (sequencing, breathing suppression, barge-in).
"""

from __future__ import annotations
import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray

from reachy_mini.motion.move import Move
from reachy_mini.motion.recorded_move import RecordedMove


logger = logging.getLogger(__name__)


class GeneratedQueueMove(Move):  # type: ignore
    """Wrapper exposing a generated trajectory through the official Move interface."""

    def __init__(self, move_dict: dict[str, Any], name: str = "generated"):
        """Wrap a RecordedMove-shaped dict (already validated by the choreographer)."""
        self.recorded_move = RecordedMove(move_dict)
        self.name = name

    @property
    def duration(self) -> float:
        """Duration property required by official Move interface."""
        return float(self.recorded_move.duration)

    def evaluate(self, t: float) -> tuple[NDArray[np.float64] | None, NDArray[np.float64] | None, float | None]:
        """Evaluate the generated move at time t."""
        try:
            head_pose, antennas, body_yaw = self.recorded_move.evaluate(t)
            if isinstance(antennas, tuple):
                antennas = np.array([antennas[0], antennas[1]])
            return (head_pose, antennas, body_yaw)
        except Exception as e:
            logger.error(f"Error evaluating generated move '{self.name}' at t={t}: {e}")
            from reachy_mini.utils import create_head_pose

            neutral_head_pose = create_head_pose(0, 0, 0, 0, 0, 0, degrees=True)
            return (neutral_head_pose, np.array([0.0, 0.0], dtype=np.float64), 0.0)
