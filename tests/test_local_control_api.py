"""HTTP API tests for the always-on local mobile gateway."""

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from reachy_mini_conversation_app.local_control.app import create_local_control_app
from reachy_mini_conversation_app.local_control.security import SessionAuthorizer


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
    return daemon, qwen


def _logged_in_client() -> tuple[TestClient, AsyncMock, AsyncMock]:
    daemon, qwen = _clients()
    app = create_local_control_app(daemon, qwen, SessionAuthorizer("12345"))
    client = TestClient(app)
    response = client.post("/api/session", json={"pin": "12345"})
    assert response.status_code == 204
    assert response.cookies.get("reachy_local_session")
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


def test_platform_safety_routes_work_without_qwen() -> None:
    """Emergency stop, motor mode, wake and sleep call the daemon directly."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        assert client.post("/api/robot/wake").status_code == 204
        assert client.post("/api/robot/stop").status_code == 204
        assert client.post("/api/robot/sleep").status_code == 204
        assert client.post("/api/motors/enabled").status_code == 204
        assert client.post("/api/motors/turbo").status_code == 422

    daemon.stop_motion.assert_awaited_once_with("12345678-1234-5678-1234-567812345678")
    daemon.wake.assert_awaited_once_with()
    daemon.sleep.assert_awaited_once_with()
    daemon.set_motor_mode.assert_awaited_once_with("enabled")


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
