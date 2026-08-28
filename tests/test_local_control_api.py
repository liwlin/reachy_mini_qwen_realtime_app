"""HTTP API tests for the always-on local mobile gateway."""

import time
from pathlib import Path
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
        "known_networks": ["EventNet", "BackupNet"],
        "connected_network": "EventNet",
    }
    daemon.start_qwen.return_value = {"state": "running", "error": None}
    daemon.restart_qwen.return_value = {"state": "running", "error": None}
    daemon.list_installed_apps.return_value = [
        {
            "name": "coding_lab",
            "source_kind": "installed",
            "description": "",
            "url": None,
            "extra": {"cardData": {"title": "Coding Lab", "emoji": "🧪"}},
        },
        {
            "name": "reachy_mini_qwen_realtime_app",
            "source_kind": "installed",
            "description": "",
            "url": None,
            "extra": {
                "custom_app_url": "http://0.0.0.0:7860/",
                "cardData": {"title": "Reachy Mini Qwen Realtime", "emoji": "🎤"},
            },
        },
    ]
    daemon.start_app.return_value = {"state": "starting", "error": None}
    daemon.wake.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}
    daemon.sleep.return_value = {"uuid": "87654321-4321-8765-4321-876543218765"}
    daemon.list_recorded_moves.side_effect = lambda dataset: (
        ["happy1", "sad1"] if dataset.endswith("emotions-library") else ["dance1"]
    )
    daemon.play_recorded_move.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}
    daemon.stop_all_motions.return_value = []
    daemon.scan_wifi.return_value = ["EventNet", "Guest"]
    daemon.wifi_error.return_value = {"error": None}
    daemon.speaker_volume.return_value = {
        "volume": 42,
        "platform": "Linux",
        "device": "Reachy Mini Audio",
    }
    daemon.set_speaker_volume.return_value = {
        "volume": 55,
        "platform": "Linux",
        "device": "Reachy Mini Audio",
    }
    daemon.microphone_volume.return_value = {
        "volume": 61,
        "platform": "Linux",
        "device": "Reachy Mini Audio",
    }
    daemon.set_microphone_volume.return_value = {
        "volume": 73,
        "platform": "Linux",
        "device": "Reachy Mini Audio",
    }
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


def _logged_in_client(hf_cache_root: Path | None = None) -> tuple[TestClient, AsyncMock, AsyncMock]:
    daemon, qwen = _clients()
    app = create_local_control_app(daemon, qwen, SessionAuthorizer("12345"), hf_cache_root=hf_cache_root)
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
        assert client.get("/api/apps").status_code == 401
        assert client.get("/api/motions/catalog").status_code == 401
        assert client.post("/api/qwen/start").status_code == 401
        assert client.post("/api/robot/stop").status_code == 401
        assert client.get("/api/media/volume").status_code == 401
        assert client.post("/api/media/volume", json={"volume": 55}).status_code == 401
        assert client.get("/api/media/microphone").status_code == 401
        assert client.post("/api/media/microphone", json={"volume": 73}).status_code == 401


def test_media_volume_routes_read_and_write_fixed_audio_controls() -> None:
    """Authenticated media settings expose only sanitized speaker and microphone values."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        assert client.get("/api/media/volume").json() == {
            "volume": 42,
            "platform": "Linux",
            "device": "Reachy Mini Audio",
        }
        assert client.post("/api/media/volume", json={"volume": 55}).json() == {
            "volume": 55,
            "platform": "Linux",
            "device": "Reachy Mini Audio",
        }
        assert client.get("/api/media/microphone").json() == {
            "volume": 61,
            "platform": "Linux",
            "device": "Reachy Mini Audio",
        }
        assert client.post("/api/media/microphone", json={"volume": 73}).json() == {
            "volume": 73,
            "platform": "Linux",
            "device": "Reachy Mini Audio",
        }

    daemon.speaker_volume.assert_awaited_once_with()
    daemon.set_speaker_volume.assert_awaited_once_with(55)
    daemon.microphone_volume.assert_awaited_once_with()
    daemon.set_microphone_volume.assert_awaited_once_with(73)


def test_media_volume_routes_reject_invalid_values_before_daemon_calls() -> None:
    """FastAPI validation rejects ambiguous and unsafe volume representations."""
    client, daemon, _qwen = _logged_in_client()
    invalid_values = [-1, 101, 1.5, True, "50", None]
    with client:
        for value in invalid_values:
            assert client.post("/api/media/volume", json={"volume": value}).status_code == 422
            assert client.post("/api/media/microphone", json={"volume": value}).status_code == 422

    daemon.set_speaker_volume.assert_not_awaited()
    daemon.set_microphone_volume.assert_not_awaited()


def test_media_page_is_served_without_bypassing_api_authentication() -> None:
    """The public shell can load for PIN entry while its media state remains protected."""
    daemon, qwen = _clients()
    app = create_local_control_app(daemon, qwen, SessionAuthorizer("12345"))

    with TestClient(app) as client:
        page = client.get("/media")
        assert page.status_code == 200
        assert 'data-page="media"' in page.text
        assert client.get("/api/media/volume").status_code == 401


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
        "wifi": {
            "mode": "wlan",
            "known_networks": ["EventNet", "BackupNet"],
            "connected_network": "EventNet",
        },
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


def test_installed_app_catalog_is_sanitized_for_the_phone() -> None:
    """The local page sees installed display metadata and active state only."""
    client, _daemon, _qwen = _logged_in_client()
    with client:
        response = client.get("/api/apps")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "coding_lab", "title": "Coding Lab", "emoji": "🧪", "active": False},
        {
            "name": "reachy_mini_qwen_realtime_app",
            "title": "Reachy Mini Qwen Realtime",
            "emoji": "🎤",
            "active": True,
            "custom_ui_port": 7860,
        },
    ]


def test_installed_app_switch_and_stop_routes_follow_current_state() -> None:
    """Authenticated phone requests can switch and stop only installed/current apps."""
    client, daemon, _qwen = _logged_in_client()
    daemon.app_status.side_effect = [
        {
            "state": "running",
            "error": None,
            "info": {"name": "reachy_mini_qwen_realtime_app"},
        },
        None,
        {"state": "running", "error": None, "info": {"name": "coding_lab"}},
        {"state": "running", "error": None, "info": {"name": "coding_lab"}},
        None,
    ]
    with client:
        switched = client.post("/api/apps/coding_lab/switch")
        stopped = client.post("/api/apps/coding_lab/stop")

    assert switched.json() == {"active": "coding_lab", "changed": True}
    assert stopped.json() == {"stopped": "coding_lab"}
    assert daemon.start_app.await_args_list[0].args == ("coding_lab",)
    assert daemon.stop_current_app.await_count == 2


def test_installed_app_route_rejects_unknown_name_before_lifecycle_call() -> None:
    """Path injection and uninstalled names cannot reach Daemon lifecycle calls."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        response = client.post("/api/apps/run_shell/switch")

    assert response.status_code == 404
    assert response.json() == {"error": "unknown_app", "rollback_restored": False}
    daemon.start_app.assert_not_awaited()


def test_motion_catalog_play_status_and_stop_routes(tmp_path: Path) -> None:
    """The authenticated API exposes live fixed-source moves and serialized playback."""
    client, daemon, qwen = _logged_in_client(tmp_path)
    with client:
        catalog = client.get("/api/motions/catalog")
        started = client.post("/api/motions/emotion/happy1/play")
        time.sleep(0.02)
        status = client.get("/api/motions/status")
        stopped = client.post("/api/motions/stop")

    assert catalog.status_code == 200
    assert catalog.json()["emotion"]["count"] == 2
    assert catalog.json()["music_dance"]["available"] is False
    assert started.status_code == 202
    assert started.json()["name"] == "happy1"
    assert status.json() == {"state": "idle", "source": None, "name": None, "error": None}
    assert stopped.json()["motors_disabled"] is False
    daemon.play_recorded_move.assert_awaited_once_with("pollen-robotics/reachy-mini-emotions-library", "happy1")
    qwen.suspend_motion.assert_awaited_once_with()
    qwen.resume_motion.assert_awaited_once_with()


def test_motion_routes_reject_unknown_move_and_disabled_motors(tmp_path: Path) -> None:
    """Invalid or sleeping motion requests fail before Daemon playback."""
    client, daemon, _qwen = _logged_in_client(tmp_path)
    with client:
        unknown = client.post("/api/motions/emotion/run_shell/play")
        daemon.motor_status.return_value = {"mode": "disabled"}
        sleeping = client.post("/api/motions/emotion/happy1/play")

    assert unknown.status_code == 404
    assert unknown.json() == {"error": "unknown_move"}
    assert sleeping.status_code == 409
    assert sleeping.json() == {"error": "motors_disabled"}
    daemon.play_recorded_move.assert_not_awaited()


def test_emergency_stop_disables_motors_independently(tmp_path: Path) -> None:
    """The red phone control performs true motor disable, unlike ordinary stop."""
    client, daemon, qwen = _logged_in_client(tmp_path)
    with client:
        response = client.post("/api/robot/emergency-stop")

    assert response.status_code == 200
    assert response.json() == {
        "qwen_stopped": True,
        "qwen_suspended": True,
        "daemon_stopped": True,
        "motors_disabled": True,
    }
    qwen.stop_actions.assert_awaited_once_with()
    qwen.suspend_motion.assert_awaited_once_with()
    daemon.stop_all_motions.assert_awaited_once_with()
    daemon.set_motor_mode.assert_awaited_once_with("disabled")


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


def test_saved_network_switch_reuses_stored_credentials() -> None:
    """A known inactive SSID is activated without asking the phone for its password."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        response = client.post("/api/wifi/switch", json={"ssid": "BackupNet"})

    assert response.status_code == 202
    assert response.json() == {"status": "switching", "ssid": "BackupNet"}
    daemon.connect_wifi.assert_awaited_once_with("BackupNet", "")


def test_saved_network_switch_is_idempotent_and_rejects_unknown_names() -> None:
    """Current/unknown SSIDs cannot create or replace saved NetworkManager entries."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        current = client.post("/api/wifi/switch", json={"ssid": "EventNet"})
        unknown = client.post("/api/wifi/switch", json={"ssid": "InjectedNet"})

    assert current.json() == {"status": "already_connected", "ssid": "EventNet"}
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "unknown_saved_network"}
    daemon.connect_wifi.assert_not_awaited()


def test_saved_network_switch_rejects_control_characters() -> None:
    """Malformed path/log data is rejected before Wi-Fi status or connect calls."""
    client, daemon, _qwen = _logged_in_client()
    with client:
        response = client.post("/api/wifi/switch", json={"ssid": "bad\nssid"})

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_ssid"}
    daemon.wifi_status.assert_not_awaited()
    daemon.connect_wifi.assert_not_awaited()


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
