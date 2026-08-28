"""Recorded-move catalogs and exclusive motor-ownership coordination."""

import asyncio
from pathlib import Path
from contextlib import suppress

from reachy_mini_conversation_app.local_control.catalogs import (
    MOTION_SOURCES,
    MotionSourceDefinition,
    motion_display,
    hf_dataset_cache_path,
)
from reachy_mini_conversation_app.local_control.qwen_client import (
    QwenRpcError,
    QwenRpcClient,
    QwenUnavailableError,
)
from reachy_mini_conversation_app.local_control.daemon_client import QWEN_APP_NAME, DaemonClient, LocalControlError


class MotionControlError(RuntimeError):
    """Expose one stable motion coordination failure reason."""

    def __init__(self, reason: str) -> None:
        """Store the stable reason used by API error mapping."""
        super().__init__(reason)
        self.reason = reason


class MotionCoordinator:
    """Discover fixed motion sources and serialize their motor ownership."""

    def __init__(
        self,
        daemon: DaemonClient,
        qwen: QwenRpcClient,
        *,
        hf_cache_root: Path | None = None,
    ) -> None:
        """Create a coordinator around narrow Daemon and Qwen clients."""
        self._daemon = daemon
        self._qwen = qwen
        self._hf_cache_root = hf_cache_root or Path.home() / ".cache" / "huggingface" / "hub"
        self._lock = asyncio.Lock()
        self._monitor: asyncio.Task[None] | None = None
        self._resume_allowed = True
        self._qwen_suspended = False
        self._status: dict[str, object] = {"state": "idle", "source": None, "name": None, "error": None}
        self._catalog_cache: dict[str, dict[str, object]] | None = None

    async def _source_catalog(self, definition: MotionSourceDefinition) -> dict[str, object]:
        if definition.expected_names and not hf_dataset_cache_path(definition.dataset, self._hf_cache_root).is_dir():
            return {
                "label": definition.label,
                "category": definition.category,
                "available": False,
                "count": 0,
                "expected_count": len(definition.expected_names),
                "moves": [],
            }
        try:
            discovered = await self._daemon.list_recorded_moves(definition.dataset)
        except LocalControlError:
            return {
                "label": definition.label,
                "category": definition.category,
                "available": False,
                "count": 0,
                "expected_count": len(definition.expected_names) or None,
                "moves": [],
            }

        if definition.expected_names:
            discovered_set = set(discovered)
            names = [name for name in definition.expected_names if name in discovered_set]
        else:
            names = list(dict.fromkeys(discovered))
        moves = [motion_display(definition.source_id, name) for name in names]
        return {
            "label": definition.label,
            "category": definition.category,
            "available": True,
            "count": len(moves),
            "expected_count": len(definition.expected_names) or None,
            "moves": moves,
        }

    async def catalog(self, refresh: bool = False) -> dict[str, dict[str, object]]:
        """Return live source catalogs without probing a missing optional cache."""
        if self._catalog_cache is not None and not refresh:
            return self._catalog_cache
        self._catalog_cache = {
            source_id: await self._source_catalog(definition) for source_id, definition in MOTION_SOURCES.items()
        }
        return self._catalog_cache

    async def _validated_move(self, source_id: str, name: str) -> MotionSourceDefinition:
        definition = MOTION_SOURCES.get(source_id)
        if definition is None:
            raise MotionControlError("unknown_source")
        source = await self._source_catalog(definition)
        if not source["available"]:
            raise MotionControlError("motion_source_unavailable")
        moves = source.get("moves")
        if not isinstance(moves, list):
            raise MotionControlError("motion_catalog_invalid_response")
        names = {item["name"] for item in moves if isinstance(item, dict) and isinstance(item.get("name"), str)}
        if name not in names:
            raise MotionControlError("unknown_move")
        return definition

    async def _suspend_qwen_if_active(self) -> bool:
        current = await self._daemon.app_status()
        if current is None or current.get("state") != "running":
            return False
        info = current.get("info")
        if not isinstance(info, dict) or info.get("name") != QWEN_APP_NAME:
            return False
        await self._qwen.suspend_motion()
        return True

    def _release_lock(self) -> None:
        if self._lock.locked():
            self._lock.release()

    async def _monitor_move(self, move_uuid: str, qwen_suspended: bool) -> None:
        try:
            await self._daemon.wait_for_motion(move_uuid)
        except LocalControlError as error:
            self._status["state"] = "error"
            self._status["error"] = str(error)
            return

        if qwen_suspended and self._resume_allowed:
            try:
                await self._qwen.resume_motion()
            except (QwenUnavailableError, QwenRpcError) as error:
                self._status["state"] = "error"
                self._status["error"] = str(error)
                self._release_lock()
                return
        self._qwen_suspended = False
        self._status = {"state": "idle", "source": None, "name": None, "error": None}
        self._release_lock()

    async def play(self, source_id: str, name: str) -> dict[str, object]:
        """Start one validated recorded move and monitor ownership in background."""
        if self._lock.locked():
            raise MotionControlError("motion_busy")
        await self._lock.acquire()
        qwen_suspended = False
        move_started = False
        try:
            definition = await self._validated_move(source_id, name)
            if (await self._daemon.motor_status()).get("mode") != "enabled":
                raise MotionControlError("motors_disabled")
            qwen_suspended = await self._suspend_qwen_if_active()
            self._qwen_suspended = qwen_suspended
            started = await self._daemon.play_recorded_move(definition.dataset, name)
            move_uuid = started.get("uuid")
            if not isinstance(move_uuid, str):
                raise MotionControlError("motion_invalid_response")
            move_started = True
            self._resume_allowed = True
            self._status = {"state": "running", "source": source_id, "name": name, "error": None}
            self._monitor = asyncio.create_task(self._monitor_move(move_uuid, qwen_suspended))
            return {"status": "started", "uuid": move_uuid, "source": source_id, "name": name}
        except Exception:
            if qwen_suspended and not move_started:
                with suppress(QwenUnavailableError, QwenRpcError):
                    await self._qwen.resume_motion()
            self._qwen_suspended = False
            self._release_lock()
            raise

    async def wait_for_idle(self) -> None:
        """Wait for the current monitor task to finish without changing its state."""
        monitor = self._monitor
        if monitor is not None:
            await monitor

    async def status(self) -> dict[str, object]:
        """Return the current phone-triggered motion state."""
        return dict(self._status)

    async def stop(self, resume_qwen: bool = True) -> dict[str, bool]:
        """Stop Qwen and Daemon moves without disabling motors."""
        self._resume_allowed = resume_qwen
        qwen_stopped = True
        daemon_stopped = True
        try:
            await self._qwen.stop_actions()
        except (QwenUnavailableError, QwenRpcError):
            qwen_stopped = False
        try:
            await self._daemon.stop_all_motions()
        except LocalControlError:
            daemon_stopped = False

        monitor = self._monitor
        if monitor is not None and not monitor.done() and daemon_stopped:
            await monitor
        elif monitor is None or monitor.done():
            if self._qwen_suspended and resume_qwen:
                try:
                    await self._qwen.resume_motion()
                except (QwenUnavailableError, QwenRpcError):
                    qwen_stopped = False
            self._qwen_suspended = False
            self._status = {"state": "idle", "source": None, "name": None, "error": None}
            self._release_lock()
        return {
            "qwen_stopped": qwen_stopped,
            "daemon_stopped": daemon_stopped,
            "motors_disabled": False,
        }

    async def emergency_stop(self) -> dict[str, bool]:
        """Stop every known motion source and independently disable motors."""
        self._resume_allowed = False
        qwen_stopped = True
        qwen_suspended = True
        daemon_stopped = True
        motors_disabled = True
        try:
            await self._qwen.stop_actions()
        except (QwenUnavailableError, QwenRpcError):
            qwen_stopped = False
        try:
            await self._qwen.suspend_motion()
        except (QwenUnavailableError, QwenRpcError):
            qwen_suspended = False
        try:
            await self._daemon.stop_all_motions()
        except LocalControlError:
            daemon_stopped = False
        try:
            await self._daemon.set_motor_mode("disabled")
        except LocalControlError:
            motors_disabled = False

        monitor = self._monitor
        if monitor is not None and not monitor.done():
            monitor.cancel()
            with suppress(asyncio.CancelledError):
                await monitor
        self._qwen_suspended = qwen_suspended
        self._status = {"state": "idle", "source": None, "name": None, "error": None}
        self._release_lock()
        return {
            "qwen_stopped": qwen_stopped,
            "qwen_suspended": qwen_suspended,
            "daemon_stopped": daemon_stopped,
            "motors_disabled": motors_disabled,
        }
