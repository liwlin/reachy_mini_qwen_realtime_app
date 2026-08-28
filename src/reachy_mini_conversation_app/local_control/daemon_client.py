"""Narrow loopback client for the Reachy Mini Daemon 1.9 API."""

import os
import re
import base64
import asyncio
from uuid import UUID
from urllib.parse import quote

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey, X25519PrivateKey


DAEMON_BASE_URL = "http://127.0.0.1:8000"
QWEN_APP_NAME = "reachy_mini_qwen_realtime_app"
_MOTOR_MODES = frozenset({"enabled", "disabled"})
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class LocalControlError(RuntimeError):
    """Report a sanitized failure at the local daemon boundary."""


def validate_ssid(ssid: str) -> str:
    """Normalize one SSID and reject control characters or invalid byte length."""
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
        provisioning_pin: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Create a client restricted to the configured loopback daemon."""
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            trust_env=False,
        )
        self._provisioning_pin = provisioning_pin

    async def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        operation: str,
        params: dict[str, str] | None = None,
        json_body: dict[str, str] | None = None,
    ) -> object | None:
        try:
            response = await self._client.request(method, path, params=params, json=json_body)
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

    async def wake(self) -> dict[str, object]:
        """Run the daemon wake-up motion."""
        return self._mapping(await self._request("POST", "/api/move/play/wake_up", "wake"), "wake")

    async def sleep(self) -> dict[str, object]:
        """Run the daemon sleep motion."""
        return self._mapping(await self._request("POST", "/api/move/play/goto_sleep", "sleep"), "sleep")

    async def wait_for_motion(
        self,
        move_uuid: str,
        *,
        timeout_s: float = 15.0,
        poll_interval_s: float = 0.1,
    ) -> None:
        """Wait until one Daemon move UUID is no longer running."""
        try:
            normalized_uuid = str(UUID(move_uuid))
        except ValueError:
            raise ValueError("invalid_move_uuid") from None
        deadline = asyncio.get_running_loop().time() + timeout_s
        while True:
            running = await self._request("GET", "/api/move/running", "motion_status")
            if not isinstance(running, list):
                raise LocalControlError("motion_status_invalid_response")
            running_uuids = {
                str(item.get("uuid"))
                for item in running
                if isinstance(item, dict) and isinstance(item.get("uuid"), str)
            }
            if normalized_uuid not in running_uuids:
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise LocalControlError("motion_timeout")
            await asyncio.sleep(max(0.0, poll_interval_s))

    async def stop_motion(self, move_uuid: str) -> object | None:
        """Stop one still-running daemon move UUID."""
        try:
            normalized_uuid = str(UUID(move_uuid))
        except ValueError:
            raise ValueError("invalid_move_uuid") from None
        running_uuids = set(await self.running_motions())
        if normalized_uuid not in running_uuids:
            return None
        return await self._request(
            "POST",
            "/api/move/stop",
            "motion_stop",
            json_body={"uuid": normalized_uuid},
        )

    async def running_motions(self) -> list[str]:
        """Return every valid Daemon move UUID currently running."""
        payload = await self._request("GET", "/api/move/running", "motion_status")
        if not isinstance(payload, list):
            raise LocalControlError("motion_status_invalid_response")
        running: list[str] = []
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("uuid"), str):
                raise LocalControlError("motion_status_invalid_response")
            try:
                running.append(str(UUID(item["uuid"])))
            except ValueError:
                raise LocalControlError("motion_status_invalid_response") from None
        return running

    async def stop_all_motions(self) -> list[str]:
        """Attempt to stop every running Daemon move and return their UUIDs."""
        running = await self.running_motions()
        failed = False
        for move_uuid in running:
            try:
                await self._request(
                    "POST",
                    "/api/move/stop",
                    "motion_stop",
                    json_body={"uuid": move_uuid},
                )
            except LocalControlError:
                failed = True
        if failed:
            raise LocalControlError("motion_stop_failed")
        return running

    async def app_status(self) -> dict[str, object] | None:
        """Return the current managed application status."""
        payload = await self._request("GET", "/api/apps/current-app-status", "app_status")
        if payload is None:
            return None
        return self._mapping(payload, "app_status")

    async def list_installed_apps(self) -> list[dict[str, object]]:
        """Return Daemon's installed application entries."""
        payload = await self._request("GET", "/api/apps/list-available/installed", "app_catalog")
        if not isinstance(payload, list):
            raise LocalControlError("app_catalog_invalid_response")
        try:
            return [self._mapping(item, "app_catalog") for item in payload]
        except LocalControlError:
            raise LocalControlError("app_catalog_invalid_response") from None

    async def start_app(self, name: str) -> dict[str, object]:
        """Start one catalog-validated installed app name."""
        encoded_name = quote(name, safe="")
        return self._mapping(
            await self._request("POST", f"/api/apps/start-app/{encoded_name}", "app_start"),
            "app_start",
        )

    async def stop_current_app(self) -> object | None:
        """Stop the application currently holding Daemon's app slot."""
        return await self._request("POST", "/api/apps/stop-current-app", "app_stop")

    async def start_qwen(self) -> dict[str, object]:
        """Start the fixed Qwen application."""
        path = f"/api/apps/start-app/{QWEN_APP_NAME}"
        return self._mapping(await self._request("POST", path, "qwen_start"), "qwen_start")

    async def stop_qwen(self) -> object | None:
        """Stop the current managed application."""
        return await self.stop_current_app()

    async def restart_qwen(self) -> dict[str, object]:
        """Restart the current managed application."""
        return self._mapping(
            await self._request("POST", "/api/apps/restart-current-app", "qwen_restart"),
            "qwen_restart",
        )

    async def list_recorded_moves(self, dataset: str) -> list[str]:
        """List moves from one server-selected recorded-move dataset."""
        encoded_dataset = quote(dataset, safe="/")
        payload = await self._request(
            "GET",
            f"/api/move/recorded-move-datasets/list/{encoded_dataset}",
            "recorded_moves",
        )
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise LocalControlError("recorded_moves_invalid_response")
        return list(payload)

    async def play_recorded_move(self, dataset: str, move: str) -> dict[str, object]:
        """Play one catalog-validated move from a fixed dataset."""
        encoded_dataset = quote(dataset, safe="/")
        encoded_move = quote(move, safe="")
        return self._mapping(
            await self._request(
                "POST",
                f"/api/move/play/recorded-move-dataset/{encoded_dataset}/{encoded_move}",
                "recorded_move_play",
            ),
            "recorded_move_play",
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
        normalized_ssid = validate_ssid(ssid)
        normalized_password = _validate_wifi_password(password)
        if self._provisioning_pin is None:
            raise LocalControlError("wifi_provisioning_unavailable")
        key_payload = self._mapping(
            await self._request("GET", "/wifi/prov_key", "wifi_provisioning_key"),
            "wifi_provisioning_key",
        )
        kid = key_payload.get("kid")
        public_key = key_payload.get("pk")
        if not isinstance(kid, str) or not isinstance(public_key, str):
            raise LocalControlError("wifi_provisioning_key_invalid_response")
        try:
            server_public_key = X25519PublicKey.from_public_bytes(base64.b64decode(public_key, validate=True))
        except (ValueError, TypeError):
            raise LocalControlError("wifi_provisioning_key_invalid_response") from None
        phone_private_key = X25519PrivateKey.generate()
        phone_public_key = phone_private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        shared = phone_private_key.exchange(server_public_key)
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._provisioning_pin.encode("utf-8"),
            info=b"reachy-mini-wifi-psk-v1",
        ).derive(shared)
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(
            nonce,
            normalized_password.encode("utf-8"),
            normalized_ssid.encode("utf-8"),
        )
        return await self._request(
            "POST",
            "/wifi/connect_sealed",
            "wifi_connect",
            json_body={
                "ssid": normalized_ssid,
                "kid": kid,
                "epk": base64.b64encode(phone_public_key).decode("ascii"),
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "ct": base64.b64encode(ciphertext).decode("ascii"),
            },
        )

    async def forget_wifi(self, ssid: str) -> object | None:
        """Forget one validated saved network."""
        return await self._request(
            "POST",
            "/wifi/forget",
            "wifi_forget",
            params={"ssid": validate_ssid(ssid)},
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
