"""Installed-app catalog and switch coordinator tests."""

import asyncio
from unittest.mock import AsyncMock, call

import pytest

from reachy_mini_conversation_app.local_control.app_catalog import AppSwitchError, InstalledAppService
from reachy_mini_conversation_app.local_control.daemon_client import LocalControlError


def _installed(name: str, *, title: str | None = None) -> dict[str, object]:
    return {
        "name": name,
        "source_kind": "installed",
        "description": "",
        "url": None,
        "extra": {"cardData": {"title": title or name, "emoji": "📦"}},
    }


def _running(name: str, error: str | None = None) -> dict[str, object]:
    return {"state": "running", "error": error, "info": {"name": name}}


@pytest.mark.asyncio
async def test_list_apps_returns_sanitized_entries_with_active_state() -> None:
    """Phone app cards are derived from current Daemon state, not trusted metadata."""
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [
        _installed("coding_lab", title="Coding Lab"),
        {
            **_installed("reachy_mini_qwen_realtime_app", title="Reachy Mini Qwen Realtime"),
            "extra": {
                "venv_path": "/private/venv",
                "custom_app_url": "http://0.0.0.0:7860/",
                "cardData": {"title": "Reachy Mini Qwen Realtime", "emoji": "🎤"},
            },
        },
    ]
    daemon.app_status.return_value = _running("reachy_mini_qwen_realtime_app")

    result = await InstalledAppService(daemon).list_apps()

    assert result == [
        {"name": "coding_lab", "title": "Coding Lab", "emoji": "📦", "active": False},
        {
            "name": "reachy_mini_qwen_realtime_app",
            "title": "Reachy Mini Qwen Realtime",
            "emoji": "🎤",
            "active": True,
            "custom_ui_port": 7860,
        },
    ]


@pytest.mark.asyncio
async def test_switch_stops_current_then_starts_target() -> None:
    """A confirmed switch releases the single app slot before target startup."""
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [_installed("qwen"), _installed("coding_lab")]
    daemon.app_status.side_effect = [_running("qwen"), None, _running("coding_lab")]

    result = await InstalledAppService(daemon, poll_interval_s=0).switch_app("coding_lab")

    assert result == {"active": "coding_lab", "changed": True}
    assert daemon.method_calls == [
        call.list_installed_apps(),
        call.app_status(),
        call.stop_current_app(),
        call.app_status(),
        call.start_app("coding_lab"),
        call.app_status(),
    ]


@pytest.mark.asyncio
async def test_failed_target_restores_previous_app() -> None:
    """A failed target start attempts one rollback to the previously healthy app."""
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [_installed("qwen"), _installed("coding_lab")]
    daemon.app_status.side_effect = [_running("qwen"), None, _running("qwen")]
    daemon.start_app.side_effect = [LocalControlError("app_start_failed:500"), {"state": "starting"}]

    with pytest.raises(AppSwitchError) as raised:
        await InstalledAppService(daemon, poll_interval_s=0).switch_app("coding_lab")

    assert raised.value.reason == "target_start_failed"
    assert raised.value.rollback_restored is True
    assert daemon.start_app.await_args_list == [call("coding_lab"), call("qwen")]


@pytest.mark.asyncio
async def test_unknown_same_and_noncurrent_app_branches_fail_closed() -> None:
    """Only fresh installed/current state can authorize lifecycle changes."""
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [_installed("coding_lab"), _installed("marionette")]
    daemon.app_status.return_value = _running("coding_lab")
    service = InstalledAppService(daemon, poll_interval_s=0)

    with pytest.raises(AppSwitchError, match="unknown_app"):
        await service.switch_app("run_shell")
    assert await service.switch_app("coding_lab") == {"active": "coding_lab", "changed": False}
    with pytest.raises(AppSwitchError, match="not_current_app"):
        await service.stop_app("marionette")

    daemon.stop_current_app.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_current_app_waits_until_slot_is_released() -> None:
    """Stop success means Daemon has released the app slot, not only accepted a request."""
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [_installed("coding_lab")]
    daemon.app_status.side_effect = [_running("coding_lab"), _running("coding_lab"), None]

    result = await InstalledAppService(daemon, poll_interval_s=0).stop_app("coding_lab")

    assert result == {"stopped": "coding_lab"}
    assert daemon.app_status.await_count == 3


@pytest.mark.asyncio
async def test_concurrent_switches_serialize_before_reading_catalog() -> None:
    """A second switch cannot observe or mutate the app slot mid-transaction."""
    entered = asyncio.Event()
    release = asyncio.Event()
    daemon = AsyncMock()
    calls = 0

    async def list_installed() -> list[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return [_installed("coding_lab")]

    daemon.list_installed_apps.side_effect = list_installed
    daemon.app_status.return_value = _running("coding_lab")
    service = InstalledAppService(daemon, poll_interval_s=0)

    first = asyncio.create_task(service.switch_app("coding_lab"))
    await entered.wait()
    second = asyncio.create_task(service.switch_app("coding_lab"))
    await asyncio.sleep(0)
    assert daemon.list_installed_apps.await_count == 1
    release.set()
    assert await asyncio.gather(first, second) == [
        {"active": "coding_lab", "changed": False},
        {"active": "coding_lab", "changed": False},
    ]
