"""CLI entry point for the Reachy Mini local mobile controller."""

import argparse

import uvicorn

from reachy_mini.utils.hardware_id import get_pin
from reachy_mini_conversation_app.local_control.app import create_local_control_app
from reachy_mini_conversation_app.local_control.security import SessionAuthorizer
from reachy_mini_conversation_app.local_control.qwen_client import QwenRpcClient
from reachy_mini_conversation_app.local_control.daemon_client import DaemonClient


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reachy Mini local mobile control")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=7861, type=int)
    return parser.parse_args()


def main() -> None:
    """Run the always-on LAN control gateway."""
    args = _parse_args()
    pin = get_pin()
    app = create_local_control_app(
        DaemonClient(provisioning_pin=pin),
        QwenRpcClient(),
        SessionAuthorizer(pin),
    )
    uvicorn.run(app, host=args.host, port=args.port, access_log=True)


if __name__ == "__main__":
    main()
