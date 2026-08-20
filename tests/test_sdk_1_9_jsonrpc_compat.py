"""Regression tests for the Daemon 1.9 JSON-RPC compatibility boundary."""

import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _rpc_module() -> object:
    return importlib.import_module("reachy_mini_conversation_app.sdk_jsonrpc")


def test_sdk_1_9_compat_dispatches_jsonrpc_requests() -> None:
    """The app-local server must keep the v1 UI RPC surface on SDK 1.9."""
    compat = _rpc_module()
    rpc = compat.JsonRpcServer()
    app = FastAPI()

    @rpc.method("compat.echo")
    def echo(params: dict[str, object]) -> dict[str, object]:
        return params

    rpc.mount(app)
    with TestClient(app).websocket_connect("/rpc") as websocket:
        websocket.send_json({"jsonrpc": "2.0", "id": "compat-1", "method": "compat.echo", "params": {"ok": True}})
        response = websocket.receive_json()

    assert response == {"jsonrpc": "2.0", "id": "compat-1", "result": {"ok": True}}


def test_sdk_1_9_compat_preserves_machine_readable_error_reason() -> None:
    """UI callers must receive the stable error reason used by v1 JavaScript."""
    compat = _rpc_module()
    rpc = compat.JsonRpcServer()
    app = FastAPI()

    @rpc.method("compat.fail")
    def fail(_params: dict[str, object]) -> None:
        raise compat.JsonRpcError("not ready", reason="not_ready")

    rpc.mount(app)
    with TestClient(app).websocket_connect("/rpc") as websocket:
        websocket.send_json({"jsonrpc": "2.0", "id": 7, "method": "compat.fail", "params": {}})
        response = websocket.receive_json()

    assert response["id"] == 7
    assert response["error"]["data"]["reason"] == "not_ready"


def test_sdk_1_9_compat_rejects_wrong_jsonrpc_version() -> None:
    """Only JSON-RPC 2.0 frames may reach registered app handlers."""
    compat = _rpc_module()
    rpc = compat.JsonRpcServer()
    app = FastAPI()
    calls = 0

    @rpc.method("compat.echo")
    def echo(params: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return params

    rpc.mount(app)
    with TestClient(app).websocket_connect("/rpc") as websocket:
        websocket.send_json({"jsonrpc": "1.0", "id": 8, "method": "compat.echo", "params": {}})
        response = websocket.receive_json()

    assert calls == 0
    assert response["error"]["code"] == -32600
    assert response["error"]["data"]["reason"] == "invalid_request"
