"""Tests for GeneratedQueueMove and the packaged sounds helper."""

import math

import numpy as np
import pytest

from reachy_mini_conversation_app import sounds
from reachy_mini_conversation_app.generated_moves import GeneratedQueueMove


def test_generated_queue_move_wraps_trajectory(make_move):
    move = GeneratedQueueMove(make_move(duration_s=2.0), name="wave")
    assert math.isclose(move.duration, 2.0, abs_tol=0.05)
    head, antennas, body_yaw = move.evaluate(0.5)
    assert head is not None and head.shape == (4, 4)
    assert antennas is not None and antennas.shape == (2,)
    assert body_yaw == 0.0
    assert np.all(np.isfinite(head))


def test_generated_queue_move_interpolates_between_frames(make_move):
    move = GeneratedQueueMove(make_move(duration_s=2.0))
    quarter = move.evaluate(0.2501)[0]
    assert quarter is not None


class FakeMedia:
    def __init__(self):
        self.played = []

    def play_sound(self, sound_file: str) -> None:
        self.played.append(sound_file)


def test_sounds_play_resolves_packaged_file():
    media = FakeMedia()
    sounds.play(media, "move_ready.wav")
    assert len(media.played) == 1
    assert media.played[0].endswith("move_ready.wav")


def test_sounds_play_rejects_paths():
    with pytest.raises(ValueError):
        sounds.play(FakeMedia(), "../etc/passwd")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
