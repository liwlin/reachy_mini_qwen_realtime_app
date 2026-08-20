"""Reachy Mini Apps entry point with a Daemon-discoverable secondary UI."""

from pathlib import Path

from reachy_mini_conversation_app import main as shared_main
from reachy_mini_conversation_app.main import ReachyMiniConversationApp


# Reachy Mini Daemon 1.9 reads this literal from <entry-point-name>/main.py.
custom_app_url = "http://0.0.0.0:7860/"


class ReachyMiniQwenRealtimeApp(ReachyMiniConversationApp):
    """Branded Wireless application wrapper around the shared v1 implementation."""

    custom_app_url = custom_app_url

    def _get_instance_path(self) -> Path:
        """Keep shared static assets and private instance data in the implementation package."""
        if shared_main.__file__ is None:
            raise RuntimeError("reachy_mini_conversation_app.main has no filesystem path")
        return Path(shared_main.__file__).resolve()
