"""HTTP API tests for the always-on local mobile gateway."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from reachy_mini_conversation_app.local_control.app import create_local_control_app
from reachy_mini_conversation_app.local_control.security import SessionAuthorizer
from reachy_mini_conversation_app.local_control.qwen_client import QwenUnavailableError


def _clients() -> tuple[AsyncMock, AsyncMock]:
    daemon = AsyncMock()
    daemon.status.return_value = {"state": "running", "version": "1.9.0", "error": None}
    daemon.motor_status.return_value = {"mode": "enabled"}
    daemon.app_status.return_value = {
        "state": "running",
        "error": None,
        "info": {"name": "reachy_mini_qwen_realtime_app"},
    }
    daemon.wifi_status.return_value = {
        "mode": "wlan",
        "known_networks": ["EventNet"],
        "connected_network": "EventNet",
    }
    daemon.start_qwen.return_value = {"state": "running", "error": None}
    daemon.restart_qwen.return_value = {"state": "running", "error": None}
    daemon.wake.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}
    daemon.sleep.return_value = {"uuid": "87654321-4321-8765-4321-876543218765"}
    daemon.scan_wifi.return_value = ["EventNet", "Guest"]
    daemon.wifi_error.return_value = {"error": None}
    qwen = AsyncMock()
    qwen.status.return_value = {
        "backend": "qwen",
        "backend_connected": True,
        "backend_error": None,
    }
    qwen.execute_action.return_value = {"status": "looking left"}
    qwen.stop_actions.return_value = {"status": "stopped"}
    qwen.suspend_motion.return_value = {"status": "suspended"}
    qwen.resume_motion.return_value = {"status": "resumed"}
    return daemon, qwen


def _logged_in_client() -> tuple[TestClient, AsyncMock, AsyncMock]:
    daemon, qwen = _clients()
    app = create_local_control_app(daemon, qwen, SessionAuthorizer("12345"))
    client = TestClient(app)
    response = client.post("/api/session", json={"pin": "12345"})
    assert response.status_code == 204
    assert response.cookies.get("reachy_local_session")
    cookie_header = response.headers["set-cookie"]
    assert "Path=/api" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header
    return client, daemon, qwen


def test_protected_routes_require_a_valid_session() -> None:
    """LAN reachability alone does not authorize robot control."""
    daemon, qwen = _clients()
    app = create_local_control_app(daemon, qwen, SessionAuthorizer("12345"))

    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 401
        assert client.post("/api/qwen/start").status_code == 401
        assert client.post("/api/robot/stop").status_code == 401


def test_status_aggregates_daemon_motor_wifi_and_qwen() -> None:
    """One phone request reports every readiness boundary needed on site."""
    client, _daemon, _qwen = _logged_in_client()
    with client:
        response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "daemon": {"state": "running", "version": "1.9.0", "error": None},
        "motors": {"mode": "enabled"},
        "app": {
            "state": "running",
            "error": None,
            "info": {"name": "reachy_mini_qwen_realtime_app"},
        },
        "wifi": {"mode": "wlan", "known_networks": ["EventNet"], "connected_network": "EventNet"},
        "qwen": {"backend": "qwen", "backend_connected": True, "backend_error": None},
    }


def test_qwen_lifecycle_and_action_routes_are_fixed() -> None:
    """The browser can control only the Qwen app and allowlisted actions."""
    client, daemon, qwen = _logged_in_client()
    with client:
        assert client.post("/api/qwen/start").json()["state"] == "running"
        assert client.post("/api/qwen/stop").status_code == 204
        assert client.post("/api/qwen/restart").json()["state"] == "running"
        assert client.post("/api/actions/look_left").json() == {"status": "looking left"}
        assert client.post("/api/actions/run_shell").status_code == 404

    daemon.start_qwen.assert_awaited_once_with()
    daemon.stop_qwen.assert_awaited_once_with()
    daemon.restart_qwen.assert_awaited_once_with()
    qwen.execute_action.assert_awaited_once_with("look_left")


def test_platform_safety_routes_coordinate_qwen_and_daemon_motion() -> None:
    """Sleep yields motor ownership; wake enables motors before restoring Qwen motion."""
    client, daemon, qwen = _logged_in_client()
    events: list[str] = []

    async def record_suspend() -> dict[str, str]:
        events.append("qwen_suspend")
        return {"status": "suspended"}

    async def record_sleep() -> dict[str, str]:
        events.append("daemon_sleep")
        return {"uuid": "87654321-4321-8765-4321-876543218765"}

    async def record_motor(mode: str) -> None:
        events.append(f"motor_{mode}")

    async def record_wake() -> dict[str, str]:
        events.append("daemon_wake")
        return {"uuid": "12345678-1234-5678-1234-567812345678"}

    async def record_wait(move_uuid: str) -> None:
        events.append(f"wait_{move_uuid}")

    async def record_resume() -> dict[str, str]:
        events.append("qwen_resume")
        return {"status": "resumed"}

    qwen.suspend_motion.side_effect = record_suspend
    daemon.sleep.side_effect = record_sleep
    daemon.set_motor_mode.side_effect = record_motor
    daemon.wake.side_effect = record_wake
    daemon.wait_for_motion.side_effect = record_wait
    qwen.resume_motion.side_effect = record_resume
    with client:
        assert client.post("/api/robot/sleep").status_code == 204
        assert client.post("/api/robot/wake").status_code == 204
        assert client.post("/api/robot/stop").status_code == 204
        assert client.post("/api/motors/enabled").status_code == 204
        assert client.post("/api/motors/turbo").status_code == 422

    daemon.stop_motion.assert_not_awaited()
    daemon.wake.assert_awaited_once_with()
    daemon.sleep.assert_awaited_once_with()
    assert daemon.set_motor_mode.await_args_list[0].args == ("enabled",)
    assert qwen.suspend_motion.await_count == 2
    qwen.resume_motion.assert_awaited_once_with()
    assert events[:8] == [
        "qwen_suspend",
        "daemon_sleep",
        "wait_87654321-4321-8765-4321-876543218765",
        "qwen_suspend",
        "motor_enabled",
        "daemon_wake",
        "wait_12345678-1234-5678-1234-567812345678",
        "qwen_resume",
    ]


def test_running_qwen_must_yield_before_platform_sleep() -> None:
    """A running Qwen app cannot be bypassed when its motion RPC is unavailable."""
    client, daemon, qwen = _logged_in_client()
    qwen.suspend_motion.side_effect = QwenUnavailableError("qwen_rpc_unavailable")

    with client:
        response = client.post("/api/robot/sleep")

    assert response.status_code == 503
    daemon.sleep.assert_not_awaited()


def test_platform_sleep_still_works_when_qwen_is_not_running() -> None:
    """No Qwen RPC is required when the managed application is already stopped."""
    client, daemon, qwen = _logged_in_client()
    daemon.app_status.return_value = None

    with client:
        response = client.post("/api/robot/sleep")

    assert response.status_code == 204
    qwen.suspend_motion.assert_not_awaited()
    daemon.sleep.assert_awaited_once_with()


def test_logout_revokes_the_browser_session() -> None:
    """Logging out invalidates the current cookie immediately."""
    client, _daemon, _qwen = _logged_in_client()
    with client:
        assert client.delete("/api/session").status_code == 204
        assert client.get("/api/status").status_code == 401


def test_wifi_routes_scan_connect_forget_and_report_status() -> None:
    """The setup page receives a narrow Wi-Fi API without credential echo."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        assert client.get("/api/wifi/status").json()["connected_network"] == "EventNet"
        assert client.post("/api/wifi/scan").json() == ["EventNet", "Guest"]
        connected = client.post(
            "/api/wifi/connect",
            json={"ssid": "EventNet", "password": "private-passphrase"},
        )
        assert connected.status_code == 202
        assert connected.json() == {"status": "connecting"}
        assert "private-passphrase" not in connected.text
        assert client.post("/api/wifi/forget", json={"ssid": "Guest"}).status_code == 204
        assert client.get("/api/wifi/error").json() == {"error": None}

    daemon.connect_wifi.assert_awaited_once_with("EventNet", "private-passphrase")
    daemon.forget_wifi.assert_awaited_once_with("Guest")


def test_wifi_connect_rejects_control_characters_without_forwarding() -> None:
    """Malformed SSIDs are rejected before reaching the daemon."""
    client, daemon, _qwen = _logged_in_client()
    daemon.connect_wifi.side_effect = ValueError("invalid_ssid")
    with client:
        response = client.post(
            "/api/wifi/connect",
            json={"ssid": "bad\nssid", "password": "private-passphrase"},
        )

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_ssid"}
    assert "private-passphrase" not in response.text
