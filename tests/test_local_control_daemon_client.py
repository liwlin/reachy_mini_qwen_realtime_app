"""Loopback daemon client tests for local mobile control."""

import json
import base64

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey, X25519PrivateKey

from reachy_mini_conversation_app.local_control.daemon_client import (
    DaemonClient,
    LocalControlError,
)


@pytest.mark.asyncio
async def test_daemon_client_starts_qwen_on_the_fixed_app_path() -> None:
    """The mobile API cannot choose an arbitrary application name."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"state": "running", "error": None})

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        result = await client.start_qwen()
    finally:
        await client.close()

    assert result == {"state": "running", "error": None}
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/apps/start-app/reachy_mini_qwen_realtime_app"


@pytest.mark.asyncio
async def test_daemon_client_uses_only_expected_lifecycle_paths() -> None:
    """Robot lifecycle helpers map to the public Daemon 1.9 REST surface."""
    seen: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.url.path == "/api/move/running":
            return httpx.Response(200, json=[{"uuid": "12345678-1234-5678-1234-567812345678"}])
        if request.method == "GET":
            return httpx.Response(200, json={})
        if request.url.path in {"/api/move/play/wake_up", "/api/move/play/goto_sleep"}:
            return httpx.Response(200, json={"uuid": "12345678-1234-5678-1234-567812345678"})
        if request.url.path == "/api/move/stop":
            assert json.loads(request.content) == {"uuid": "12345678-1234-5678-1234-567812345678"}
            return httpx.Response(200, json={"status": "stopped"})
        if request.url.path == "/api/apps/restart-current-app":
            return httpx.Response(200, json={"state": "running", "error": None})
        return httpx.Response(204)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        await client.status()
        await client.motor_status()
        await client.set_motor_mode("enabled")
        await client.wake()
        await client.sleep()
        await client.stop_motion("12345678-1234-5678-1234-567812345678")
        await client.app_status()
        await client.stop_qwen()
        await client.restart_qwen()
    finally:
        await client.close()

    assert seen == [
        ("GET", "/api/daemon/status"),
        ("GET", "/api/motors/status"),
        ("POST", "/api/motors/set_mode/enabled"),
        ("POST", "/api/move/play/wake_up"),
        ("POST", "/api/move/play/goto_sleep"),
        ("GET", "/api/move/running"),
        ("POST", "/api/move/stop"),
        ("GET", "/api/apps/current-app-status"),
        ("POST", "/api/apps/stop-current-app"),
        ("POST", "/api/apps/restart-current-app"),
    ]


@pytest.mark.asyncio
async def test_daemon_client_reaches_installed_apps_and_recorded_moves() -> None:
    """Catalog helpers use only the fixed Daemon app and recorded-move surfaces."""
    requests: list[httpx.Request] = []
    app_info = {"name": "coding_lab", "source_kind": "installed", "description": "", "url": None, "extra": {}}

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/apps/list-available/installed":
            return httpx.Response(200, json=[app_info])
        if request.url.path == "/api/apps/start-app/coding_lab":
            return httpx.Response(200, json={"state": "starting", "error": None})
        if request.url.path == "/api/apps/stop-current-app":
            return httpx.Response(204)
        if request.url.path.endswith("/recorded-move-datasets/list/pollen-robotics/reachy-mini-emotions-library"):
            return httpx.Response(200, json=["happy1", "sad1"])
        if request.url.path.endswith(
            "/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/happy1"
        ):
            return httpx.Response(200, json={"uuid": "12345678-1234-5678-1234-567812345678"})
        raise AssertionError(f"Unexpected route: {request.method} {request.url.path}")

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        assert await client.list_installed_apps() == [app_info]
        assert await client.start_app("coding_lab") == {"state": "starting", "error": None}
        assert await client.stop_current_app() is None
        assert await client.list_recorded_moves("pollen-robotics/reachy-mini-emotions-library") == ["happy1", "sad1"]
        assert await client.play_recorded_move("pollen-robotics/reachy-mini-emotions-library", "happy1") == {
            "uuid": "12345678-1234-5678-1234-567812345678"
        }
    finally:
        await client.close()

    assert [(request.method, request.url.path) for request in requests] == [
        ("GET", "/api/apps/list-available/installed"),
        ("POST", "/api/apps/start-app/coding_lab"),
        ("POST", "/api/apps/stop-current-app"),
        ("GET", "/api/move/recorded-move-datasets/list/pollen-robotics/reachy-mini-emotions-library"),
        (
            "POST",
            "/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/happy1",
        ),
    ]


@pytest.mark.asyncio
async def test_stop_all_motions_stops_every_running_uuid() -> None:
    """Emergency cleanup discovers every live move instead of trusting one cached UUID."""
    first = "12345678-1234-5678-1234-567812345678"
    second = "87654321-4321-8765-4321-876543218765"
    stopped: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/move/running":
            return httpx.Response(200, json=[{"uuid": first}, {"uuid": second}])
        if request.method == "POST" and request.url.path == "/api/move/stop":
            stopped.append(str(json.loads(request.content)["uuid"]))
            return httpx.Response(200, json={"message": "stopped"})
        raise AssertionError(f"Unexpected route: {request.method} {request.url.path}")

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        result = await client.stop_all_motions()
    finally:
        await client.close()

    assert result == [first, second]
    assert stopped == [first, second]


@pytest.mark.asyncio
async def test_catalog_helpers_reject_malformed_daemon_payloads() -> None:
    """Malformed upstream catalogs fail closed before reaching the browser."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "mapping"})

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(LocalControlError, match="app_catalog_invalid_response"):
            await client.list_installed_apps()
        with pytest.raises(LocalControlError, match="recorded_moves_invalid_response"):
            await client.list_recorded_moves("pollen-robotics/reachy-mini-emotions-library")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_daemon_client_does_not_stop_a_completed_platform_move() -> None:
    """A stale wake/sleep UUID is not forwarded to Daemon's erroring stop route."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        result = await client.stop_motion("12345678-1234-5678-1234-567812345678")
    finally:
        await client.close()

    assert result is None
    assert [(request.method, request.url.path) for request in requests] == [("GET", "/api/move/running")]


@pytest.mark.asyncio
async def test_daemon_client_rejects_unknown_motor_mode_without_request() -> None:
    """The gateway never forwards arbitrary path fragments as motor modes."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="invalid_motor_mode"):
            await client.set_motor_mode("turbo")
    finally:
        await client.close()

    assert requests == []


@pytest.mark.asyncio
async def test_wait_for_motion_polls_until_the_uuid_finishes() -> None:
    """Sleep/wake coordination waits for Daemon to release motor ownership."""
    move_uuid = "12345678-1234-5678-1234-567812345678"
    responses = [
        httpx.Response(200, json=[{"uuid": move_uuid}]),
        httpx.Response(200, json=[]),
    ]
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses.pop(0)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        await client.wait_for_motion(move_uuid, timeout_s=0.5, poll_interval_s=0)
    finally:
        await client.close()

    assert [request.url.path for request in requests] == ["/api/move/running", "/api/move/running"]


@pytest.mark.asyncio
async def test_daemon_client_connects_wifi_without_leaking_password() -> None:
    """Wi-Fi credentials are sealed for the daemon and stay out of URLs/results."""
    requests: list[httpx.Request] = []
    server_private_key = X25519PrivateKey.generate()
    server_public_key = server_private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/wifi/prov_key":
            return httpx.Response(
                200,
                json={
                    "kid": "test-key",
                    "pk": base64.b64encode(server_public_key).decode("ascii"),
                    "alg": "x25519-hkdf-sha256-aesgcm",
                },
            )
        payload = json.loads(request.content)
        phone_public_key = X25519PublicKey.from_public_bytes(base64.b64decode(payload["epk"]))
        shared = server_private_key.exchange(phone_public_key)
        key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"12345",
            info=b"reachy-mini-wifi-psk-v1",
        ).derive(shared)
        plaintext = AESGCM(key).decrypt(
            base64.b64decode(payload["nonce"]),
            base64.b64decode(payload["ct"]),
            payload["ssid"].encode("utf-8"),
        )
        assert plaintext == b"private-passphrase"
        return httpx.Response(204)

    client = DaemonClient(provisioning_pin="12345", transport=httpx.MockTransport(handler))
    try:
        result = await client.connect_wifi("EventNet", "private-passphrase")
    finally:
        await client.close()

    assert result is None
    assert [request.url.path for request in requests] == ["/wifi/prov_key", "/wifi/connect_sealed"]
    assert all("private-passphrase" not in str(request.url) for request in requests)
    assert b"private-passphrase" not in requests[1].content
    assert "private-passphrase" not in repr(result)


@pytest.mark.asyncio
async def test_daemon_client_error_hides_upstream_query_and_secret() -> None:
    """HTTP failures report an operation and status without credential-bearing URLs."""
    server_private_key = X25519PrivateKey.generate()
    server_public_key = server_private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wifi/prov_key":
            return httpx.Response(200, json={"kid": "test-key", "pk": base64.b64encode(server_public_key).decode()})
        return httpx.Response(400, json={"detail": f"failed {request.url}"})

    client = DaemonClient(provisioning_pin="12345", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(LocalControlError) as captured:
            await client.connect_wifi("EventNet", "private-passphrase")
    finally:
        await client.close()

    message = str(captured.value)
    assert message == "wifi_connect_failed:400"
    assert "private-passphrase" not in message
    assert "EventNet" not in message


@pytest.mark.asyncio
async def test_daemon_client_validates_wifi_credentials_before_request() -> None:
    """Invalid SSIDs and short protected-network passwords never reach NetworkManager."""
    requests: list[httpx.Request] = []

    server_private_key = X25519PrivateKey.generate()
    server_public_key = server_private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/wifi/prov_key":
            return httpx.Response(200, json={"kid": "test-key", "pk": base64.b64encode(server_public_key).decode()})
        return httpx.Response(204)

    client = DaemonClient(provisioning_pin="12345", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="invalid_ssid"):
            await client.connect_wifi("bad\nssid", "password")
        with pytest.raises(ValueError, match="invalid_wifi_password"):
            await client.connect_wifi("EventNet", "short")
        await client.connect_wifi("OpenNet", "")
    finally:
        await client.close()

    assert [request.url.path for request in requests] == ["/wifi/prov_key", "/wifi/connect_sealed"]


@pytest.mark.asyncio
async def test_daemon_client_requires_pin_for_sealed_wifi_without_request() -> None:
    """The gateway never falls back to the plaintext query-string endpoint."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(LocalControlError, match="wifi_provisioning_unavailable"):
            await client.connect_wifi("EventNet", "private-passphrase")
    finally:
        await client.close()

    assert requests == []


@pytest.mark.asyncio
async def test_daemon_client_wifi_surface_returns_sanitized_values() -> None:
    """The client exposes SSID/status data but normalizes raw nmcli failures."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/wifi/status":
            return httpx.Response(
                200,
                json={"mode": "wlan", "known_networks": ["EventNet"], "connected_network": "EventNet"},
            )
        if request.url.path == "/wifi/scan_and_list":
            return httpx.Response(200, json=["EventNet", "Guest"])
        if request.url.path == "/wifi/error":
            return httpx.Response(200, json={"error": "Secrets were required, but not provided"})
        return httpx.Response(204)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        assert (await client.wifi_status())["connected_network"] == "EventNet"
        assert await client.scan_wifi() == ["EventNet", "Guest"]
        assert await client.wifi_error() == {"error": "authentication_failed"}
        await client.forget_wifi("EventNet")
    finally:
        await client.close()
