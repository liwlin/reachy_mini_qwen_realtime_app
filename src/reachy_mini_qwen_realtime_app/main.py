"""Reachy Mini Apps entry point with a Daemon-discoverable secondary UI."""

from reachy_mini_conversation_app.main import ReachyMiniConversationApp


# Reachy Mini Daemon 1.9 reads this literal from <entry-point-name>/main.py.
custom_app_url = "http://0.0.0.0:7860/"


class ReachyMiniQwenRealtimeApp(ReachyMiniConversationApp):
    """Branded Wireless application wrapper around the shared v1 implementation."""

    custom_app_url = custom_app_url
