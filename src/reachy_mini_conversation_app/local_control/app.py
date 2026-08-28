"""Always-on same-origin API for LAN mobile control."""

from typing import Literal
from pathlib import Path
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Cookie, Depends, FastAPI, Response, HTTPException
from pydantic import Field, BaseModel, StrictInt
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from reachy_mini_conversation_app.local_actions import list_local_actions
from reachy_mini_conversation_app.local_control.security import (
    SessionAuthorizer,
    AuthenticationError,
)
from reachy_mini_conversation_app.local_control.app_catalog import AppSwitchError, InstalledAppService
from reachy_mini_conversation_app.local_control.qwen_client import (
    QwenRpcError,
    QwenRpcClient,
    QwenUnavailableError,
)
from reachy_mini_conversation_app.local_control.daemon_client import (
    QWEN_APP_NAME,
    DaemonClient,
    LocalControlError,
    validate_ssid,
)
from reachy_mini_conversation_app.local_control.motion_control import MotionCoordinator, MotionControlError


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


class SavedWifiPayload(BaseModel):
    """Previously saved Wi-Fi network selected for activation."""

    ssid: str = Field(min_length=1, max_length=32)


class VolumePayload(BaseModel):
    """Strict local audio volume accepted by the narrow Daemon proxy."""

    volume: StrictInt = Field(ge=0, le=100)


def create_local_control_app(
    daemon_client: DaemonClient,
    qwen_client: QwenRpcClient,
    authorizer: SessionAuthorizer,
    static_dir: Path | None = None,
    hf_cache_root: Path | None = None,
) -> FastAPI:
    """Create the authenticated local mobile-control API."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        await daemon_client.close()

    app = FastAPI(title="Reachy Mini Local Control", lifespan=lifespan)
    installed_apps = InstalledAppService(daemon_client)
    motions = MotionCoordinator(daemon_client, qwen_client, hf_cache_root=hf_cache_root)
    active_platform_move_uuid: str | None = None

    async def suspend_qwen_motion() -> bool:
        current_app = await daemon_client.app_status()
        if current_app is None or current_app.get("state") != "running":
            return False
        info = current_app.get("info")
        if not isinstance(info, dict) or info.get("name") != QWEN_APP_NAME:
            return False
        await qwen_client.suspend_motion()
        return True

    async def resume_qwen_motion(was_suspended: bool) -> None:
        if was_suspended:
            await qwen_client.resume_motion()

    def move_uuid(result: dict[str, object]) -> str:
        value = result.get("uuid")
        if not isinstance(value, str):
            raise LocalControlError("motion_invalid_response")
        return value

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

    @app.exception_handler(AppSwitchError)
    async def handle_app_switch_error(_request: object, error: AppSwitchError) -> JSONResponse:
        status_code = {
            "unknown_app": 404,
            "not_current_app": 409,
            "current_stop_failed": 502,
            "target_start_failed": 502,
        }.get(error.reason, 409)
        return JSONResponse(
            status_code=status_code,
            content={"error": error.reason, "rollback_restored": error.rollback_restored},
        )

    @app.exception_handler(MotionControlError)
    async def handle_motion_control_error(_request: object, error: MotionControlError) -> JSONResponse:
        status_code = {
            "unknown_source": 404,
            "unknown_move": 404,
            "motion_source_unavailable": 409,
            "motion_busy": 409,
            "motors_disabled": 409,
        }.get(error.reason, 502)
        return JSONResponse(status_code=status_code, content={"error": error.reason})

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
            path="/api",
        )

    @app.delete("/api/session", status_code=204)
    async def delete_session(
        response: Response,
        reachy_local_session: str = Cookie(alias=SESSION_COOKIE),
    ) -> None:
        if not authorizer.is_valid(reachy_local_session):
            raise HTTPException(status_code=401, detail="authentication_required")
        authorizer.revoke(reachy_local_session)
        response.delete_cookie(SESSION_COOKIE, path="/api", samesite="strict")

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

    @app.get("/api/media/volume")
    async def get_speaker_volume(_session: str = Depends(require_session)) -> dict[str, object]:
        return await daemon_client.speaker_volume()

    @app.post("/api/media/volume")
    async def set_speaker_volume(
        payload: VolumePayload,
        _session: str = Depends(require_session),
    ) -> dict[str, object]:
        return await daemon_client.set_speaker_volume(payload.volume)

    @app.get("/api/media/microphone")
    async def get_microphone_volume(_session: str = Depends(require_session)) -> dict[str, object]:
        return await daemon_client.microphone_volume()

    @app.post("/api/media/microphone")
    async def set_microphone_volume(
        payload: VolumePayload,
        _session: str = Depends(require_session),
    ) -> dict[str, object]:
        return await daemon_client.set_microphone_volume(payload.volume)

    @app.get("/api/apps")
    async def list_apps(_session: str = Depends(require_session)) -> list[dict[str, object]]:
        return await installed_apps.list_apps()

    @app.post("/api/apps/{name}/switch")
    async def switch_app(name: str, _session: str = Depends(require_session)) -> dict[str, object]:
        return await installed_apps.switch_app(name)

    @app.post("/api/apps/{name}/stop")
    async def stop_app(name: str, _session: str = Depends(require_session)) -> dict[str, str]:
        return await installed_apps.stop_app(name)

    @app.get("/api/motions/catalog")
    async def motion_catalog(_session: str = Depends(require_session)) -> dict[str, dict[str, object]]:
        return await motions.catalog()

    @app.get("/api/motions/status")
    async def motion_status(_session: str = Depends(require_session)) -> dict[str, object]:
        return await motions.status()

    @app.post("/api/motions/{source_id}/{name}/play", status_code=202)
    async def play_motion(
        source_id: str,
        name: str,
        _session: str = Depends(require_session),
    ) -> dict[str, object]:
        return await motions.play(source_id, name)

    @app.post("/api/motions/stop")
    async def stop_motion(_session: str = Depends(require_session)) -> dict[str, bool]:
        return await motions.stop(resume_qwen=True)

    @app.post("/api/robot/emergency-stop")
    async def emergency_stop(_session: str = Depends(require_session)) -> dict[str, bool]:
        return await motions.emergency_stop()

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
        nonlocal active_platform_move_uuid
        qwen_suspended = await suspend_qwen_motion()
        await daemon_client.set_motor_mode("enabled")
        result = await daemon_client.wake()
        active_platform_move_uuid = move_uuid(result)
        await daemon_client.wait_for_motion(active_platform_move_uuid)
        active_platform_move_uuid = None
        await resume_qwen_motion(qwen_suspended)

    @app.post("/api/robot/sleep", status_code=204)
    async def sleep(_session: str = Depends(require_session)) -> None:
        nonlocal active_platform_move_uuid
        await suspend_qwen_motion()
        result = await daemon_client.sleep()
        active_platform_move_uuid = move_uuid(result)
        await daemon_client.wait_for_motion(active_platform_move_uuid)
        active_platform_move_uuid = None

    @app.post("/api/robot/stop", status_code=204)
    async def stop(_session: str = Depends(require_session)) -> None:
        nonlocal active_platform_move_uuid
        try:
            await qwen_client.stop_actions()
        except (QwenUnavailableError, QwenRpcError):
            pass
        if active_platform_move_uuid is not None:
            move_uuid, active_platform_move_uuid = active_platform_move_uuid, None
            await daemon_client.stop_motion(move_uuid)

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

    @app.post("/api/wifi/switch", status_code=202)
    async def switch_saved_wifi(
        payload: SavedWifiPayload,
        _session: str = Depends(require_session),
    ) -> dict[str, str]:
        ssid = validate_ssid(payload.ssid)
        status = await daemon_client.wifi_status()
        known_networks = status.get("known_networks")
        if not isinstance(known_networks, list) or ssid not in known_networks:
            raise HTTPException(status_code=404, detail="unknown_saved_network")
        if status.get("connected_network") == ssid:
            return {"status": "already_connected", "ssid": ssid}
        await daemon_client.connect_wifi(ssid, "")
        return {"status": "switching", "ssid": ssid}

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

    @app.get("/apps", include_in_schema=False)
    async def apps_page() -> FileResponse:
        return FileResponse(resolved_static_dir / "apps.html")

    @app.get("/motions", include_in_schema=False)
    async def motions_page() -> FileResponse:
        return FileResponse(resolved_static_dir / "motions.html")

    @app.get("/media", include_in_schema=False)
    async def media_page() -> FileResponse:
        return FileResponse(resolved_static_dir / "media.html")

    @app.get("/setup", include_in_schema=False)
    async def setup() -> FileResponse:
        return FileResponse(resolved_static_dir / "setup.html")

    return app
