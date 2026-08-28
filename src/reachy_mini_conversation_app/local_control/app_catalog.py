"""Installed-app catalog and serialized lifecycle orchestration."""

import asyncio

from reachy_mini_conversation_app.local_control.catalogs import sanitize_installed_app
from reachy_mini_conversation_app.local_control.daemon_client import DaemonClient, LocalControlError


class AppSwitchError(RuntimeError):
    """Expose one stable application lifecycle failure reason."""

    def __init__(self, reason: str, rollback_restored: bool = False) -> None:
        """Store a stable reason and whether rollback restored the previous app."""
        super().__init__(reason)
        self.reason = reason
        self.rollback_restored = rollback_restored


class InstalledAppService:
    """List and switch installed apps while respecting Daemon's single app slot."""

    def __init__(
        self,
        daemon: DaemonClient,
        *,
        timeout_s: float = 20.0,
        poll_interval_s: float = 0.2,
    ) -> None:
        """Create a serialized app service using one narrow Daemon client."""
        self._daemon = daemon
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s
        self._lock = asyncio.Lock()

    @staticmethod
    def _current_name(status: dict[str, object] | None) -> str | None:
        if status is None:
            return None
        info = status.get("info")
        if not isinstance(info, dict):
            return None
        name = info.get("name")
        return name if isinstance(name, str) else None

    async def _installed_entries(self) -> list[dict[str, object]]:
        return await self._daemon.list_installed_apps()

    async def _installed_names(self) -> set[str]:
        names: set[str] = set()
        for entry in await self._installed_entries():
            sanitized = sanitize_installed_app(entry, None)
            names.add(str(sanitized["name"]))
        return names

    async def list_apps(self) -> list[dict[str, object]]:
        """Return sanitized installed apps annotated with current state."""
        current_name = self._current_name(await self._daemon.app_status())
        return [sanitize_installed_app(entry, current_name) for entry in await self._installed_entries()]

    async def _wait_current(self, expected_name: str | None) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._timeout_s
        while True:
            status = await self._daemon.app_status()
            current_name = self._current_name(status)
            if expected_name is None and status is None:
                return
            if current_name == expected_name and status is not None:
                error = status.get("error")
                if error is not None:
                    raise LocalControlError("app_start_failed")
                if status.get("state") == "running":
                    return
            if loop.time() >= deadline:
                raise LocalControlError("app_switch_timeout")
            await asyncio.sleep(self._poll_interval_s)

    async def _restore(self, previous_name: str | None) -> bool:
        if previous_name is None:
            return False
        try:
            await self._daemon.start_app(previous_name)
            await self._wait_current(previous_name)
        except LocalControlError:
            return False
        return True

    async def switch_app(self, name: str) -> dict[str, object]:
        """Stop the current app, start the target, and rollback on target failure."""
        async with self._lock:
            if name not in await self._installed_names():
                raise AppSwitchError("unknown_app")
            previous_name = self._current_name(await self._daemon.app_status())
            if previous_name == name:
                return {"active": name, "changed": False}

            if previous_name is not None:
                try:
                    await self._daemon.stop_current_app()
                    await self._wait_current(None)
                except LocalControlError as error:
                    raise AppSwitchError("current_stop_failed") from error

            try:
                await self._daemon.start_app(name)
                await self._wait_current(name)
            except LocalControlError as error:
                restored = await self._restore(previous_name)
                raise AppSwitchError("target_start_failed", restored) from error
            return {"active": name, "changed": True}

    async def stop_app(self, name: str) -> dict[str, str]:
        """Stop the named app only when it currently owns the app slot."""
        async with self._lock:
            if name not in await self._installed_names():
                raise AppSwitchError("unknown_app")
            if self._current_name(await self._daemon.app_status()) != name:
                raise AppSwitchError("not_current_app")
            try:
                await self._daemon.stop_current_app()
                await self._wait_current(None)
            except LocalControlError as error:
                raise AppSwitchError("current_stop_failed") from error
            return {"stopped": name}
