"""Packaged notification sounds played through the robot's media pipeline."""

from pathlib import Path
from importlib import resources
from typing import Protocol


class SupportsPlaySound(Protocol):
    """Anything exposing the SDK media player's play_sound."""

    def play_sound(self, sound_file: str) -> None:
        """Play an audio file by path."""
        ...


def play(media: SupportsPlaySound, filename: str) -> None:
    """Play a packaged sound by bare filename (blocking; offload from async code)."""
    if Path(filename).name != filename:
        raise ValueError(f"expected a bare packaged sound filename, got {filename!r}")
    sound_path = resources.files(__package__).joinpath(filename)
    media.play_sound(str(sound_path))
