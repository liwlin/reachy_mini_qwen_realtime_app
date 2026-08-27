"""Always-on same-origin API for LAN mobile control."""

from typing import Literal
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Cookie, Depends, FastAPI, Response, HTTPException
from pydantic import Field, BaseModel
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from reachy_mini_conversation_app.local_actions import list_local_actions
from reachy_mini_conversation_app.local_control.security import (
    SessionAuthorizer,
    AuthenticationError,
)
from reachy_mini_conversation_app.local_control.qwen_client import (
    QwenRpcError,
    QwenRpcClient,
    QwenUnavailableError,
)
from reachy_mini_conversation_app.local_control.daemon_client import (
    DaemonClient,
    LocalControlError,
)


SESSION_COOKIE = "reachy_local_session"
_ACTION_NAMES = frozenset(item["name"] for item in list_local_actions())


class PinPayload(BaseModel):
    """Local device-PIN login payload."""

    pin: str = Field(min_length=1, max_length=32)


class WifiConnectPayload(BaseModel):
    """Wi-Fi credentials used only for one loopback connect request."""

    ssid: str = Field(min_length=1, max_length=32)
    password: str = Field(max_length=63)


class WifiForgetPayload(BaseModel):
    """Saved network selected for removal."""

    ssid: str = Field(min_length=1, max_length=32)


def create_local_control_app(
    daemon_client: DaemonClient,
    qwen_client: QwenRpcClient,
    authorizer: SessionAuthorizer,
    static_dir: Path | None = None,
) -> FastAPI:
    """Create the authenticated local mobile-control API."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await daemon_client.close()

    app = FastAPI(title="Reachy Mini Local Control", lifespan=lifespan)

    def require_session(reachy_local_session: str | None = Cookie(default=None)) -> str:
        if reachy_local_session is None or not authorizer.is_valid(reachy_local_session):
            raise HTTPException(status_code=401, detail="authentication_required")
        return reachy_local_session

    @app.exception_handler(LocalControlError)
    async def handle_daemon_error(_request: object, error: LocalControlError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"error": str(error)})

    @app.exception_handler(QwenUnavailableError)
    async def handle_qwen_unavailable(_request: object, error: QwenUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": str(error)})

    @app.exception_handler(QwenRpcError)
    async def handle_qwen_error(_request: object, error: QwenRpcError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": str(error)})

    @app.exception_handler(ValueError)
    async def handle_validation_error(_request: object, error: ValueError) -> JSONResponse:
        message = str(error)
        allowed = {"invalid_ssid", "invalid_wifi_password", "invalid_motor_mode"}
        return JSONResponse(status_code=422, content={"error": message if message in allowed else "invalid_input"})

    @app.post("/api/session", status_code=204)
    async def create_session(payload: PinPayload, response: Response) -> None:
        try:
            token = authorizer.authenticate(payload.pin)
        except AuthenticationError:
            raise HTTPException(status_code=401, detail="invalid_pin") from None
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            secure=False,
            max_age=12 * 60 * 60,
        )

    @app.delete("/api/session", status_code=204)
    async def delete_session(
        response: Response,
        reachy_local_session: str = Cookie(alias=SESSION_COOKIE),
    ) -> None:
        if not authorizer.is_valid(reachy_local_session):
            raise HTTPException(status_code=401, detail="authentication_required")
        authorizer.revoke(reachy_local_session)
        response.delete_cookie(SESSION_COOKIE, samesite="strict")

    @app.get("/api/status")
    async def get_status(_session: str = Depends(require_session)) -> dict[str, object]:
        daemon = await daemon_client.status()
        motors = await daemon_client.motor_status()
        current_app = await daemon_client.app_status()
        wifi = await daemon_client.wifi_status()
        qwen: dict[str, object]
        if current_app is not None and current_app.get("state") == "running":
            try:
                qwen = await qwen_client.status()
            except (QwenUnavailableError, QwenRpcError):
                qwen = {"backend_connected": False, "backend_error": "unavailable"}
        else:
            qwen = {"backend_connected": False, "backend_error": "not_running"}
        return {"daemon": daemon, "motors": motors, "app": current_app, "wifi": wifi, "qwen": qwen}

    @app.post("/api/qwen/start")
    async def start_qwen(_session: str = Depends(require_session)) -> dict[str, object]:
        return await daemon_client.start_qwen()

    @app.post("/api/qwen/stop", status_code=204)
    async def stop_qwen(_session: str = Depends(require_session)) -> None:
        await daemon_client.stop_qwen()

    @app.post("/api/qwen/restart")
    async def restart_qwen(_session: str = Depends(require_session)) -> dict[str, object]:
        return await daemon_client.restart_qwen()

    @app.post("/api/motors/{mode}", status_code=204)
    async def set_motor_mode(
        mode: Literal["enabled", "disabled"],
        _session: str = Depends(require_session),
    ) -> None:
        await daemon_client.set_motor_mode(mode)

    @app.post("/api/robot/wake", status_code=204)
    async def wake(_session: str = Depends(require_session)) -> None:
        await daemon_client.wake()

    @app.post("/api/robot/sleep", status_code=204)
    async def sleep(_session: str = Depends(require_session)) -> None:
        await daemon_client.sleep()

    @app.post("/api/robot/stop", status_code=204)
    async def stop(_session: str = Depends(require_session)) -> None:
        await daemon_client.stop_motion()
        try:
            await qwen_client.stop_actions()
        except (QwenUnavailableError, QwenRpcError):
            return

    @app.get("/api/actions")
    async def get_actions(_session: str = Depends(require_session)) -> list[dict[str, str]]:
        return list_local_actions()

    @app.post("/api/actions/{name}")
    async def execute_action(name: str, _session: str = Depends(require_session)) -> dict[str, object]:
        if name not in _ACTION_NAMES:
            raise HTTPException(status_code=404, detail="unknown_action")
        return await qwen_client.execute_action(name)

    @app.get("/api/wifi/status")
    async def get_wifi_status(_session: str = Depends(require_session)) -> dict[str, object]:
        return await daemon_client.wifi_status()

    @app.post("/api/wifi/scan")
    async def scan_wifi(_session: str = Depends(require_session)) -> list[str]:
        return await daemon_client.scan_wifi()

    @app.post("/api/wifi/connect", status_code=202)
    async def connect_wifi(
        payload: WifiConnectPayload,
        _session: str = Depends(require_session),
    ) -> dict[str, str]:
        await daemon_client.connect_wifi(payload.ssid, payload.password)
        return {"status": "connecting"}

    @app.post("/api/wifi/forget", status_code=204)
    async def forget_wifi(
        payload: WifiForgetPayload,
        _session: str = Depends(require_session),
    ) -> None:
        await daemon_client.forget_wifi(payload.ssid)

    @app.get("/api/wifi/error")
    async def get_wifi_error(_session: str = Depends(require_session)) -> dict[str, str | None]:
        return await daemon_client.wifi_error()

    resolved_static_dir = static_dir or Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=resolved_static_dir), name="local-control-assets")

    @app.get("/", include_in_schema=False)
    async def dashboard() -> FileResponse:
        return FileResponse(resolved_static_dir / "index.html")

    @app.get("/setup", include_in_schema=False)
    async def setup() -> FileResponse:
        return FileResponse(resolved_static_dir / "setup.html")

    return app
