"""Short-lived JSON-RPC client for the local Qwen application."""

import json
import uuid
import asyncio

from websockets.exceptions import WebSocketException
from websockets.asyncio.client import connect


QWEN_RPC_URL = "ws://127.0.0.1:7860/rpc"


class QwenUnavailableError(RuntimeError):
    """Report that the Qwen application RPC cannot be reached."""


class QwenRpcError(RuntimeError):
    """Report a stable Qwen JSON-RPC reason."""


class QwenRpcClient:
    """Make isolated JSON-RPC calls to the locally running Qwen app."""

    def __init__(self, url: str = QWEN_RPC_URL, timeout_s: float = 8.0) -> None:
        """Store the fixed local endpoint and per-call timeout."""
        self._url = url
        self._timeout_s = timeout_s

    async def call(self, method: str, params: dict[str, object] | None = None) -> object:
        """Call one method and ignore unrelated notifications."""
        request_id = uuid.uuid4().hex
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        try:
            async with asyncio.timeout(self._timeout_s):
                async with connect(
                    self._url,
                    open_timeout=self._timeout_s,
                    close_timeout=1.0,
                    proxy=None,
                ) as websocket:
                    await websocket.send(json.dumps(request))
                    async for raw_message in websocket:
                        try:
                            message: object = json.loads(raw_message)
                        except (json.JSONDecodeError, TypeError):
                            continue
                        if not isinstance(message, dict) or message.get("id") != request_id:
                            continue
                        error = message.get("error")
                        if isinstance(error, dict):
                            data = error.get("data")
                            reason = data.get("reason") if isinstance(data, dict) else None
                            raise QwenRpcError(str(reason or "qwen_rpc_error"))
                        if "result" not in message:
                            raise QwenRpcError("qwen_rpc_invalid_response")
                        return message["result"]
        except QwenRpcError:
            raise
        except TimeoutError:
            raise QwenUnavailableError("qwen_rpc_timeout") from None
        except (OSError, WebSocketException):
            raise QwenUnavailableError("qwen_rpc_unavailable") from None
        raise QwenUnavailableError("qwen_rpc_closed")

    @staticmethod
    def _mapping(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise QwenRpcError("qwen_rpc_invalid_response")
        return {str(key): value for key, value in payload.items()}

    async def status(self) -> dict[str, object]:
        """Return Qwen backend readiness."""
        return self._mapping(await self.call("conversation.status"))

    async def actions(self) -> list[dict[str, str]]:
        """Return action metadata exposed by the Qwen process."""
        payload = await self.call("robot.actions.list")
        if not isinstance(payload, list):
            raise QwenRpcError("qwen_rpc_invalid_response")
        actions: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in item.items()):
                raise QwenRpcError("qwen_rpc_invalid_response")
            actions.append(dict(item))
        return actions

    async def execute_action(self, name: str) -> dict[str, object]:
        """Execute one action name through the Qwen allowlist."""
        return self._mapping(await self.call("robot.actions.execute", {"name": name}))

    async def stop_actions(self) -> dict[str, object]:
        """Clear the Qwen movement queue."""
        return self._mapping(await self.call("robot.actions.stop"))

