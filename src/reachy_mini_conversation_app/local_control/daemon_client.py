"""Narrow loopback client for the Reachy Mini Daemon 1.9 API."""

import re

import httpx


DAEMON_BASE_URL = "http://127.0.0.1:8000"
QWEN_APP_NAME = "reachy_mini_qwen_realtime_app"
_MOTOR_MODES = frozenset({"enabled", "disabled"})
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class LocalControlError(RuntimeError):
    """Report a sanitized failure at the local daemon boundary."""


def _validate_ssid(ssid: str) -> str:
    normalized = ssid.strip()
    if not normalized or len(normalized.encode("utf-8")) > 32 or _CONTROL_CHARACTERS.search(normalized):
        raise ValueError("invalid_ssid")
    return normalized


def _validate_wifi_password(password: str) -> str:
    if password == "":
        return password
    if len(password) < 8 or len(password) > 63 or _CONTROL_CHARACTERS.search(password):
        raise ValueError("invalid_wifi_password")
    return password


class DaemonClient:
    """Call fixed daemon operations without exposing a general proxy."""

    def __init__(
        self,
        base_url: str = DAEMON_BASE_URL,
        timeout_s: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a client restricted to the configured loopback daemon."""
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            trust_env=False,
        )

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        operation: str,
        params: dict[str, str] | None = None,
    ) -> object | None:
        try:
            response = await self._client.request(method, path, params=params)
        except httpx.TimeoutException:
            raise LocalControlError(f"{operation}_timeout") from None
        except httpx.RequestError:
            raise LocalControlError(f"{operation}_unavailable") from None

        if response.is_error:
            raise LocalControlError(f"{operation}_failed:{response.status_code}")
        if response.status_code == 204 or not response.content:
            return None
        try:
            payload: object = response.json()
        except ValueError:
            raise LocalControlError(f"{operation}_invalid_response") from None
        return payload

    @staticmethod
    def _mapping(payload: object | None, operation: str) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise LocalControlError(f"{operation}_invalid_response")
        return {str(key): value for key, value in payload.items()}

    async def status(self) -> dict[str, object]:
        """Return daemon status."""
        return self._mapping(await self._request("GET", "/api/daemon/status", "daemon_status"), "daemon_status")

    async def motor_status(self) -> dict[str, object]:
        """Return the current motor mode."""
        return self._mapping(await self._request("GET", "/api/motors/status", "motor_status"), "motor_status")

    async def set_motor_mode(self, mode: str) -> object | None:
        """Set an allowlisted motor mode."""
        if mode not in _MOTOR_MODES:
            raise ValueError("invalid_motor_mode")
        return await self._request("POST", f"/api/motors/set_mode/{mode}", "motor_mode")

    async def wake(self) -> object | None:
        """Run the daemon wake-up motion."""
        return await self._request("POST", "/api/move/play/wake_up", "wake")

    async def sleep(self) -> object | None:
        """Run the daemon sleep motion."""
        return await self._request("POST", "/api/move/play/goto_sleep", "sleep")

    async def stop_motion(self) -> object | None:
        """Stop active daemon motion immediately."""
        return await self._request("POST", "/api/move/stop", "motion_stop")

    async def app_status(self) -> dict[str, object] | None:
        """Return the current managed application status."""
        payload = await self._request("GET", "/api/apps/current-app-status", "app_status")
        if payload is None:
            return None
        return self._mapping(payload, "app_status")

    async def start_qwen(self) -> dict[str, object]:
        """Start the fixed Qwen application."""
        path = f"/api/apps/start-app/{QWEN_APP_NAME}"
        return self._mapping(await self._request("POST", path, "qwen_start"), "qwen_start")

    async def stop_qwen(self) -> object | None:
        """Stop the current managed application."""
        return await self._request("POST", "/api/apps/stop-current-app", "qwen_stop")

    async def restart_qwen(self) -> dict[str, object]:
        """Restart the current managed application."""
        return self._mapping(
            await self._request("POST", "/api/apps/restart-current-app", "qwen_restart"),
            "qwen_restart",
        )

    async def wifi_status(self) -> dict[str, object]:
        """Return Wi-Fi mode and saved SSID names."""
        return self._mapping(await self._request("GET", "/wifi/status", "wifi_status"), "wifi_status")

    async def scan_wifi(self) -> list[str]:
        """Return unique nearby SSID names."""
        payload = await self._request("POST", "/wifi/scan_and_list", "wifi_scan")
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise LocalControlError("wifi_scan_invalid_response")
        return list(dict.fromkeys(payload))

    async def connect_wifi(self, ssid: str, password: str) -> object | None:
        """Ask NetworkManager to join a validated network."""
        normalized_ssid = _validate_ssid(ssid)
        normalized_password = _validate_wifi_password(password)
        return await self._request(
            "POST",
            "/wifi/connect",
            "wifi_connect",
            params={"ssid": normalized_ssid, "password": normalized_password},
        )

    async def forget_wifi(self, ssid: str) -> object | None:
        """Forget one validated saved network."""
        return await self._request(
            "POST",
            "/wifi/forget",
            "wifi_forget",
            params={"ssid": _validate_ssid(ssid)},
        )

    async def wifi_error(self) -> dict[str, str | None]:
        """Return a stable error category without leaking NetworkManager detail."""
        payload = self._mapping(await self._request("GET", "/wifi/error", "wifi_error"), "wifi_error")
        error = payload.get("error")
        if error is None:
            return {"error": None}
        message = str(error).lower()
        if "secret" in message or "password" in message or "authentication" in message:
            return {"error": "authentication_failed"}
        if "not found" in message or "no network" in message:
            return {"error": "network_not_found"}
        return {"error": "connection_failed"}
