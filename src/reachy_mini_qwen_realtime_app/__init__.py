"""Wireless-visible entry point package for Reachy Mini Qwen Realtime."""

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from reachy_mini_qwen_realtime_app.main import ReachyMiniQwenRealtimeApp


__all__ = ["ReachyMiniQwenRealtimeApp"]


def __getattr__(name: str) -> Any:
    """Load the public app class lazily so ``python -m ...main`` executes it once."""
    if name == "ReachyMiniQwenRealtimeApp":
        from reachy_mini_qwen_realtime_app.main import ReachyMiniQwenRealtimeApp

        return ReachyMiniQwenRealtimeApp
    raise AttributeError(name)
