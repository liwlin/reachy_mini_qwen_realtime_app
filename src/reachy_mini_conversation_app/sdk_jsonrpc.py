"""App-local JSON-RPC 2.0 surface compatible with Reachy Mini SDK 1.9.

The upstream conversation app v1 UI uses SDK JSON-RPC helpers introduced after
the stable Wireless Daemon 1.9 release. Keeping the small wire/server boundary
local lets the app run after Wireless synchronizes ``apps_venv`` back to the
Daemon's SDK version, while preserving the same JSON-RPC frames.
"""

from __future__ import annotations
import json
import asyncio
import logging
from typing import Any, Literal, TypeVar
from collections.abc import Callable, Awaitable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import Field, BaseModel, ConfigDict, ValidationError


logger = logging.getLogger(__name__)

JSONRPC_VERSION = "2.0"
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
SERVER_ERROR = -32000

RpcId = str | int


class RpcErrorObj(BaseModel):
    """JSON-RPC error object with a stable reason in ``data``."""

    model_config = ConfigDict(extra="ignore")

    code: int
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class RpcRequest(BaseModel):
    """JSON-RPC request or notification."""

    model_config = ConfigDict(extra="ignore")

    jsonrpc: Literal["2.0"]
    id: RpcId | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_notification(self) -> bool:
        """Return true for one-way requests without an id."""
        return self.id is None


class RpcSuccess(BaseModel):
    """JSON-RPC success response."""

    jsonrpc: str = JSONRPC_VERSION
    id: RpcId | None
    result: Any


class RpcErrorResponse(BaseModel):
    """JSON-RPC error response."""

    jsonrpc: str = JSONRPC_VERSION
    id: RpcId | None
    error: RpcErrorObj


class RpcNotification(BaseModel):
    """JSON-RPC one-way notification."""

    jsonrpc: str = JSONRPC_VERSION
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(Exception):
    """Error raised by a method handler and returned to its caller."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        code: int = SERVER_ERROR,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Create an error with a stable reason and optional structured data."""
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.code = code
        self.data = data or {}

    def to_error_model(self) -> RpcErrorObj:
        """Render this exception as a validated wire error."""
        return RpcErrorObj(
            code=self.code,
            message=self.message,
            data={**self.data, "reason": self.reason},
        )


def parse_request(raw: str | bytes | dict[str, Any]) -> RpcRequest:
    """Parse and validate one inbound JSON-RPC request."""
    try:
        if isinstance(raw, dict):
            return RpcRequest.model_validate(raw)
        return RpcRequest.model_validate_json(raw)
    except ValidationError as exc:
        if any(error.get("type") == "json_invalid" for error in exc.errors()):
            raise JsonRpcError(str(exc), reason="parse_error", code=PARSE_ERROR) from exc
        raise JsonRpcError(str(exc), reason="invalid_request", code=INVALID_REQUEST) from exc


def make_result(request_id: RpcId | None, result: Any) -> dict[str, Any]:
    """Build a JSON-RPC success response."""
    return RpcSuccess(id=request_id, result=result).model_dump()


def error_from_exc(request_id: RpcId | None, exc: BaseException) -> dict[str, Any]:
    """Build a JSON-RPC error response from an exception."""
    if isinstance(exc, JsonRpcError):
        error = exc.to_error_model()
    else:
        error = RpcErrorObj(
            code=INTERNAL_ERROR,
            message=str(exc) or exc.__class__.__name__,
            data={"reason": "internal_error"},
        )
    return RpcErrorResponse(id=request_id, error=error).model_dump()


Handler = Callable[[dict[str, Any]], Any | Awaitable[Any]]
HandlerType = TypeVar("HandlerType")


class JsonRpcServer:
    """Mount a JSON-RPC method registry on a FastAPI WebSocket route."""

    def __init__(self) -> None:
        """Create an empty method registry and client set."""
        self._methods: dict[str, Handler] = {}
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def method(self, name: str) -> Callable[[HandlerType], HandlerType]:
        """Register a synchronous or asynchronous handler as a decorator."""

        def register_handler(handler: HandlerType) -> HandlerType:
            self.register(name, handler)  # type: ignore[arg-type]
            return handler

        return register_handler

    def register(self, name: str, handler: Handler) -> None:
        """Register one named handler."""
        self._methods[name] = handler

    async def broadcast(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send one notification to every connected client."""
        payload = RpcNotification(method=method, params=params or {}).model_dump_json()
        for websocket in list(self._clients):
            try:
                await websocket.send_text(payload)
            except Exception:
                self._clients.discard(websocket)

    def broadcast_threadsafe(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Schedule a notification from a realtime or audio thread."""
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self.broadcast(method, params), self._loop)

    def mount(self, app: FastAPI, path: str = "/rpc") -> None:
        """Mount the JSON-RPC WebSocket route."""

        @app.websocket(path)
        async def rpc_websocket(websocket: WebSocket) -> None:  # pragma: no cover - transport I/O
            await self._serve(websocket)

    async def _serve(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._loop = asyncio.get_running_loop()
        self._clients.add(websocket)
        try:
            while True:
                await self._dispatch(websocket, await websocket.receive_text())
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.warning("[/rpc] connection error: %s", exc)
        finally:
            self._clients.discard(websocket)

    async def _dispatch(self, websocket: WebSocket, raw: str) -> None:
        try:
            request = parse_request(raw)
        except JsonRpcError as exc:
            await websocket.send_text(json.dumps(error_from_exc(None, exc)))
            return

        handler = self._methods.get(request.method)
        if handler is None:
            if not request.is_notification:
                error = JsonRpcError(
                    f"unknown method: {request.method}",
                    reason="method_not_found",
                    code=METHOD_NOT_FOUND,
                )
                await websocket.send_text(json.dumps(error_from_exc(request.id, error)))
            return

        try:
            result = handler(request.params)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:
            if not request.is_notification:
                await websocket.send_text(json.dumps(error_from_exc(request.id, exc)))
            else:
                logger.warning("[/rpc] notification %s failed: %s", request.method, exc)
            return

        if not request.is_notification:
            await websocket.send_text(json.dumps(make_result(request.id, result)))
