"""Qwen JSON-RPC client tests for local mobile control."""

import json

import pytest
from websockets.asyncio.server import serve

from reachy_mini_conversation_app.local_control.qwen_client import (
    QwenRpcError,
    QwenRpcClient,
    QwenUnavailableError,
)


@pytest.mark.asyncio
async def test_qwen_client_correlates_response_after_notification() -> None:
    """Unsolicited conversation events do not satisfy an RPC request."""

    async def handler(websocket: object) -> None:
        request = json.loads(await websocket.recv())  # type: ignore[attr-defined]
        await websocket.send(  # type: ignore[attr-defined]
            json.dumps({"jsonrpc": "2.0", "method": "conversation.activity", "params": {"reason": "listening"}})
        )
        await websocket.send(  # type: ignore[attr-defined]
            json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": {"backend_connected": True}})
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = QwenRpcClient(f"ws://127.0.0.1:{port}")
        result = await client.status()

    assert result == {"backend_connected": True}


@pytest.mark.asyncio
async def test_qwen_client_sends_only_fixed_action_rpc() -> None:
    """Action helpers construct the expected JSON-RPC methods and parameters."""
    requests: list[dict[str, object]] = []

    async def handler(websocket: object) -> None:
        request = json.loads(await websocket.recv())  # type: ignore[attr-defined]
        requests.append(request)
        await websocket.send(  # type: ignore[attr-defined]
            json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": {"status": "ok"}})
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = QwenRpcClient(f"ws://127.0.0.1:{port}")
        await client.execute_action("look_left")

    assert requests[0]["method"] == "robot.actions.execute"
    assert requests[0]["params"] == {"name": "look_left"}


@pytest.mark.asyncio
async def test_qwen_client_surfaces_stable_rpc_reason() -> None:
    """RPC failures expose a stable reason rather than an upstream payload dump."""

    async def handler(websocket: object) -> None:
        request = json.loads(await websocket.recv())  # type: ignore[attr-defined]
        await websocket.send(  # type: ignore[attr-defined]
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {"code": -32000, "message": "private upstream detail", "data": {"reason": "not_running"}},
                }
            )
        )

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = QwenRpcClient(f"ws://127.0.0.1:{port}")
        with pytest.raises(QwenRpcError, match="not_running"):
            await client.status()


@pytest.mark.asyncio
async def test_qwen_client_times_out_without_response() -> None:
    """A connected but silent Qwen RPC endpoint cannot hang the mobile API."""

    async def handler(websocket: object) -> None:
        await websocket.recv()  # type: ignore[attr-defined]
        await websocket.wait_closed()  # type: ignore[attr-defined]

    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        client = QwenRpcClient(f"ws://127.0.0.1:{port}", timeout_s=0.05)
        with pytest.raises(QwenUnavailableError, match="qwen_rpc_timeout"):
            await client.status()

