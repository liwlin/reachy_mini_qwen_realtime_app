"""Motion catalog, ownership, stopping, and emergency behavior tests."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from reachy_mini_conversation_app.local_control.catalogs import MUSIC_DANCE_NAMES
from reachy_mini_conversation_app.local_control.qwen_client import QwenUnavailableError
from reachy_mini_conversation_app.local_control.daemon_client import QWEN_APP_NAME, LocalControlError
from reachy_mini_conversation_app.local_control.motion_control import MotionCoordinator, MotionControlError


def _app_status(name: str | None) -> dict[str, object] | None:
    if name is None:
        return None
    return {"state": "running", "error": None, "info": {"name": name}}


@pytest.mark.asyncio
async def test_catalog_reports_live_counts_and_does_not_probe_missing_music_cache(tmp_path: Path) -> None:
    """Dashboard refresh stays robot-local and reports actual, not advertised, counts."""
    daemon = AsyncMock()

    async def moves(dataset: str) -> list[str]:
        if dataset.endswith("emotions-library"):
            return ["welcoming2", "sad1"]
        if dataset.endswith("dances-library"):
            return ["head_tilt_roll"]
        raise AssertionError("Missing music cache must not reach Daemon")

    daemon.list_recorded_moves.side_effect = moves

    catalog = await MotionCoordinator(daemon, AsyncMock(), hf_cache_root=tmp_path).catalog()

    assert catalog == {
        "emotion": {
            "label": "表情",
            "category": "emotion",
            "available": True,
            "count": 2,
            "expected_count": None,
            "moves": [
                {"name": "welcoming2", "label": "欢迎 2", "emoji": "👋"},
                {"name": "sad1", "label": "难过 1", "emoji": "😢"},
            ],
        },
        "pollen_dance": {
            "label": "官方舞蹈",
            "category": "dance",
            "available": True,
            "count": 1,
            "expected_count": None,
            "moves": [{"name": "head_tilt_roll", "label": "侧头摇摆", "emoji": "🎵"}],
        },
        "music_dance": {
            "label": "音乐舞蹈",
            "category": "dance",
            "available": False,
            "count": 0,
            "expected_count": 14,
            "moves": [],
        },
    }


@pytest.mark.asyncio
async def test_music_catalog_uses_only_official_names_when_cache_exists(tmp_path: Path) -> None:
    """An unexpected file in the community dataset cannot become a browser action."""
    (tmp_path / "datasets--Anne-Charlotte--music").mkdir()
    daemon = AsyncMock()

    async def moves(dataset: str) -> list[str]:
        if dataset == "Anne-Charlotte/music":
            return [*MUSIC_DANCE_NAMES, "../../private"]
        return []

    daemon.list_recorded_moves.side_effect = moves

    music = (await MotionCoordinator(daemon, AsyncMock(), hf_cache_root=tmp_path).catalog())["music_dance"]

    assert music["available"] is True
    assert music["count"] == 14
    assert [move["name"] for move in music["moves"]] == list(MUSIC_DANCE_NAMES)


@pytest.mark.asyncio
async def test_unknown_motion_inputs_and_disabled_motors_fail_before_playback(tmp_path: Path) -> None:
    """Unknown source/move values and sleeping motors never reach the play route."""
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1"]
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)

    with pytest.raises(MotionControlError, match="unknown_source"):
        await coordinator.play("shell", "whoami")
    with pytest.raises(MotionControlError, match="unknown_move"):
        await coordinator.play("emotion", "run_shell")
    daemon.motor_status.return_value = {"mode": "disabled"}
    with pytest.raises(MotionControlError, match="motors_disabled"):
        await coordinator.play("emotion", "happy1")

    daemon.play_recorded_move.assert_not_awaited()
    qwen.suspend_motion.assert_not_awaited()


@pytest.mark.asyncio
async def test_play_suspends_qwen_until_daemon_motion_finishes(tmp_path: Path) -> None:
    """A normal recorded move has one exclusive Qwen→Daemon→Qwen ownership handoff."""
    events: list[str] = []
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1"]
    daemon.motor_status.return_value = {"mode": "enabled"}
    daemon.app_status.return_value = _app_status(QWEN_APP_NAME)

    async def suspend() -> dict[str, str]:
        events.append("qwen_suspend")
        return {"status": "suspended"}

    async def play(_dataset: str, _name: str) -> dict[str, str]:
        events.append("daemon_play")
        return {"uuid": "12345678-1234-5678-1234-567812345678"}

    async def wait(_uuid: str) -> None:
        events.append("daemon_wait")

    async def resume() -> dict[str, str]:
        events.append("qwen_resume")
        return {"status": "resumed"}

    qwen.suspend_motion.side_effect = suspend
    qwen.resume_motion.side_effect = resume
    daemon.play_recorded_move.side_effect = play
    daemon.wait_for_motion.side_effect = wait
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)

    started = await coordinator.play("emotion", "happy1")
    await coordinator.wait_for_idle()

    assert started == {
        "status": "started",
        "uuid": "12345678-1234-5678-1234-567812345678",
        "source": "emotion",
        "name": "happy1",
    }
    assert events == ["qwen_suspend", "daemon_play", "daemon_wait", "qwen_resume"]
    assert await coordinator.status() == {"state": "idle", "source": None, "name": None, "error": None}


@pytest.mark.asyncio
async def test_concurrent_play_is_rejected_until_ordinary_stop(tmp_path: Path) -> None:
    """A second phone tap cannot stack a move while the first still owns motors."""
    stopped = asyncio.Event()
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1", "sad1"]
    daemon.motor_status.return_value = {"mode": "enabled"}
    daemon.app_status.return_value = None
    daemon.play_recorded_move.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}

    async def wait(_uuid: str) -> None:
        await stopped.wait()

    async def stop_all() -> list[str]:
        stopped.set()
        return ["12345678-1234-5678-1234-567812345678"]

    daemon.wait_for_motion.side_effect = wait
    daemon.stop_all_motions.side_effect = stop_all
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)

    await coordinator.play("emotion", "happy1")
    with pytest.raises(MotionControlError, match="motion_busy"):
        await coordinator.play("emotion", "sad1")
    result = await coordinator.stop(resume_qwen=True)
    await coordinator.wait_for_idle()

    assert result["motors_disabled"] is False
    daemon.set_motor_mode.assert_not_awaited()


@pytest.mark.asyncio
async def test_motion_timeout_keeps_qwen_suspended_until_explicit_recovery(tmp_path: Path) -> None:
    """Ambiguous Daemon ownership never resumes Qwen output automatically."""
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1"]
    daemon.motor_status.return_value = {"mode": "enabled"}
    daemon.app_status.return_value = _app_status(QWEN_APP_NAME)
    daemon.play_recorded_move.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}
    daemon.wait_for_motion.side_effect = LocalControlError("motion_timeout")
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)

    await coordinator.play("emotion", "happy1")
    await coordinator.wait_for_idle()

    assert await coordinator.status() == {
        "state": "error",
        "source": "emotion",
        "name": "happy1",
        "error": "motion_timeout",
    }
    qwen.resume_motion.assert_not_awaited()
    with pytest.raises(MotionControlError, match="motion_busy"):
        await coordinator.play("emotion", "happy1")


@pytest.mark.asyncio
async def test_emergency_disables_motors_even_when_cleanup_steps_fail(tmp_path: Path) -> None:
    """Motor disable is an independent final safety attempt, not skipped on RPC errors."""
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.stop_all_motions.side_effect = LocalControlError("motion_stop_failed")
    qwen.stop_actions.side_effect = QwenUnavailableError("qwen_rpc_unavailable")
    qwen.suspend_motion.side_effect = QwenUnavailableError("qwen_rpc_unavailable")
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)

    result = await coordinator.emergency_stop()

    daemon.set_motor_mode.assert_awaited_once_with("disabled")
    assert result == {
        "qwen_stopped": False,
        "qwen_suspended": False,
        "daemon_stopped": False,
        "motors_disabled": True,
    }
