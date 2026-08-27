"""Loopback daemon client tests for local mobile control."""

import httpx
import pytest

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
        if request.method == "GET":
            return httpx.Response(200, json={})
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
        await client.stop_motion()
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
        ("POST", "/api/move/stop"),
        ("GET", "/api/apps/current-app-status"),
        ("POST", "/api/apps/stop-current-app"),
        ("POST", "/api/apps/restart-current-app"),
    ]


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
async def test_daemon_client_connects_wifi_without_leaking_password() -> None:
    """Wi-Fi credentials stay in the loopback request and out of results."""
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        result = await client.connect_wifi("EventNet", "private-passphrase")
    finally:
        await client.close()

    assert result is None
    assert requests[0].url.path == "/wifi/connect"
    assert requests[0].url.params["ssid"] == "EventNet"
    assert requests[0].url.params["password"] == "private-passphrase"
    assert "private-passphrase" not in repr(result)


@pytest.mark.asyncio
async def test_daemon_client_error_hides_upstream_query_and_secret() -> None:
    """HTTP failures report an operation and status without credential-bearing URLs."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": f"failed {request.url}"})

    client = DaemonClient(transport=httpx.MockTransport(handler))
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

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(204)

    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="invalid_ssid"):
            await client.connect_wifi("bad\nssid", "password")
        with pytest.raises(ValueError, match="invalid_wifi_password"):
            await client.connect_wifi("EventNet", "short")
        await client.connect_wifi("OpenNet", "")
    finally:
        await client.close()

    assert len(requests) == 1
    assert requests[0].url.params["ssid"] == "OpenNet"


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
