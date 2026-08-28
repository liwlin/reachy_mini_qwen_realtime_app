# qwen.4 Local Mobile-Control Catalogs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release `1.0.1+qwen.4` with PIN-protected installed-app switching, dynamic emotion/dance catalogs, safe recorded-move playback, true emergency stop, and saved-Wi-Fi switching from the existing local mobile controller.

**Architecture:** Keep the always-on FastAPI gateway as the browser authority and add focused catalog/coordinator modules behind it. All browser-provided names are revalidated against Daemon or fixed source catalogs; recorded moves temporarily suspend Qwen motor output, while application switching and motion playback are serialized independently.

**Tech Stack:** Python 3.12/3.13, FastAPI, httpx, Qwen JSON-RPC over websockets, Reachy Mini Daemon 1.9 REST API, plain HTML/CSS/JavaScript, pytest, Ruff, strict Mypy, uv.

**Spec:** `docs/superpowers/specs/2026-08-28-local-mobile-control-catalogs-design.md`

## Global Constraints

- Keep Reachy Mini Wireless Daemon and Apps SDK at exactly 1.9.0.
- Add no new Python or browser dependencies.
- Keep every page functional without Hugging Face OAuth or signaling.
- Never accept a browser-provided dataset path, app URL, command, or unknown saved SSID.
- Do not commit API keys, device PINs, Wi-Fi credentials, local cache contents, user paths, or physical-test images.
- Do not bundle `Anne-Charlotte/music`; stage it only as device-local cache data.
- Keep qwen.3 wheel/hash/backup immutable and use it as rollback.
- Preserve Tina voice, `seed_fungus`, camera grounding, Exa MCP, personalities, and existing Qwen tools.
- Every implementation task follows RED → GREEN → refactor and ends in a Lore-format commit.

## File Structure

- Create `src/reachy_mini_conversation_app/local_control/catalogs.py`: fixed motion-source metadata, music-dance IDs, labels, and app-response sanitization.
- Create `src/reachy_mini_conversation_app/local_control/app_catalog.py`: installed-app listing, serialized switch/rollback, and stop-current orchestration.
- Create `src/reachy_mini_conversation_app/local_control/motion_control.py`: live motion catalogs, single-motion ownership, stop-all, and emergency stop.
- Modify `src/reachy_mini_conversation_app/local_control/daemon_client.py`: narrow Daemon methods required by the coordinators.
- Modify `src/reachy_mini_conversation_app/local_control/app.py`: authenticated route wiring and saved-network switching.
- Modify `src/reachy_mini_conversation_app/local_control/static/index.html`: secondary-page entry cards and stronger emergency-stop endpoint.
- Create `src/reachy_mini_conversation_app/local_control/static/apps.html`: installed-app page.
- Create `src/reachy_mini_conversation_app/local_control/static/motions.html`: searchable emotions/dances page.
- Modify `src/reachy_mini_conversation_app/local_control/static/setup.html`: saved-networks section.
- Modify `src/reachy_mini_conversation_app/local_control/static/app.js`: page-specific rendering and interactions using existing no-build JavaScript.
- Modify `src/reachy_mini_conversation_app/local_control/static/style.css`: cards, tabs, search, badges, dialogs, and responsive states.
- Create `tests/test_local_control_catalogs.py`, `tests/test_local_control_app_catalog.py`, and `tests/test_local_control_motion.py`.
- Modify existing local-control client/API/static tests plus community-release metadata and README.

---

### Task 1: Define Safe Dynamic Catalog Boundaries

**Files:**
- Create: `src/reachy_mini_conversation_app/local_control/catalogs.py`
- Create: `tests/test_local_control_catalogs.py`

**Interfaces:**
- Produces: `MotionSourceDefinition`, `MOTION_SOURCES`, `MUSIC_DANCE_NAMES`, `humanize_move_name(name: str) -> str`, `hf_dataset_cache_path(repo_id: str, cache_root: Path) -> Path`, and `sanitize_installed_app(raw: dict[str, object], current_name: str | None) -> dict[str, object]`.
- Consumes: no new project interfaces.

- [ ] **Step 1: Write failing catalog tests**

```python
def test_motion_sources_are_fixed_and_music_catalog_has_fourteen_names() -> None:
    assert set(MOTION_SOURCES) == {"emotion", "pollen_dance", "music_dance"}
    assert MOTION_SOURCES["music_dance"].dataset == "Anne-Charlotte/music"
    assert len(MUSIC_DANCE_NAMES) == 14


def test_installed_app_response_drops_internal_and_remote_metadata() -> None:
    raw = {
        "name": "coding_lab",
        "source_kind": "installed",
        "extra": {
            "venv_path": "/private/venv",
            "url": "https://example.invalid/private",
            "custom_app_url": "http://0.0.0.0:8042",
            "cardData": {"title": "Coding Lab", "emoji": "🧪"},
        },
    }


def test_hf_dataset_cache_path_matches_hub_layout(tmp_path: Path) -> None:
    assert hf_dataset_cache_path("Anne-Charlotte/music", tmp_path) == tmp_path / "datasets--Anne-Charlotte--music"
    assert sanitize_installed_app(raw, "coding_lab") == {
        "name": "coding_lab",
        "title": "Coding Lab",
        "emoji": "🧪",
        "active": True,
        "custom_ui_port": 8042,
    }
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `uv run pytest -q tests/test_local_control_catalogs.py`

Expected: collection fails because `local_control.catalogs` does not exist.

- [ ] **Step 3: Implement fixed definitions and sanitizers**

```python
@dataclass(frozen=True)
class MotionSourceDefinition:
    source_id: str
    dataset: str
    category: Literal["emotion", "dance"]
    label: str
    expected_names: tuple[str, ...] = ()


MUSIC_DANCE_NAMES = (
    "beyonce-single-ladies",
    "demon-hunters-1",
    "eagles-hotel-california",
    "eminem-lose-yourself",
    "feel-the-magic-in-the-air",
    "katy-perry-fireworks",
    "las-ketchup",
    "michael-jackson-thriller",
    "paint-it-black",
    "pharrell-williams-happy",
    "queen-we-will-rock-you",
    "spice-girls",
    "the-fratellis-whistle-for-the-choir",
    "the-white-stripes-seven-nation-army",
)
```

Parse `custom_app_url` with `urllib.parse.urlsplit`; return only an integer port for loopback/unspecified hosts and never return the original URL, venv path, author, or remote metadata.
Map dataset cache names by replacing `/` with `--` and prefixing `datasets--`;
reject repository IDs that contain empty, dot, or path-traversal segments.

- [ ] **Step 4: Run catalog tests and static checks**

Run: `uv run pytest -q tests/test_local_control_catalogs.py && uv run ruff check src/reachy_mini_conversation_app/local_control/catalogs.py tests/test_local_control_catalogs.py && uv run mypy src/reachy_mini_conversation_app/local_control/catalogs.py`

Expected: all commands pass.

- [ ] **Step 5: Commit the catalog boundary**

```text
Intent: Keep browser catalogs inside fixed robot-safe namespaces
Constraint: Counts come from live robot state, not UI constants
Tested: catalog unit tests, Ruff, Mypy
```

---

### Task 2: Extend the Narrow Daemon Client

**Files:**
- Modify: `src/reachy_mini_conversation_app/local_control/daemon_client.py`
- Modify: `tests/test_local_control_daemon_client.py`

**Interfaces:**
- Produces: `list_installed_apps()`, `start_app(name)`, `stop_current_app()`, `list_recorded_moves(dataset)`, `play_recorded_move(dataset, move)`, `running_motions()`, and `stop_all_motions()`.
- Consumes: validated app/dataset/move values supplied by later services; this client still constructs only known endpoint shapes.

- [ ] **Step 1: Write failing client route tests**

```python
@pytest.mark.asyncio
async def test_daemon_client_uses_fixed_app_and_recorded_move_routes() -> None:
    requests: list[httpx.Request] = []
    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "list-available" in request.url.path:
            return httpx.Response(200, json=[])
        if "recorded-move-datasets/list" in request.url.path:
            return httpx.Response(200, json=["happy1"])
        if "play/recorded-move" in request.url.path:
            return httpx.Response(200, json={"uuid": "12345678-1234-5678-1234-567812345678"})
        return httpx.Response(204)
    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        await client.list_installed_apps()
        await client.start_app("coding_lab")
        await client.stop_current_app()
        await client.list_recorded_moves("pollen-robotics/reachy-mini-emotions-library")
        await client.play_recorded_move("pollen-robotics/reachy-mini-emotions-library", "happy1")
    finally:
        await client.close()
    assert [(r.method, r.url.path) for r in requests] == [
        ("GET", "/api/apps/list-available/installed"),
        ("POST", "/api/apps/start-app/coding_lab"),
        ("POST", "/api/apps/stop-current-app"),
        ("GET", "/api/move/recorded-move-datasets/list/pollen-robotics/reachy-mini-emotions-library"),
        ("POST", "/api/move/play/recorded-move-dataset/pollen-robotics/reachy-mini-emotions-library/happy1"),
    ]
```

```python
@pytest.mark.asyncio
async def test_stop_all_motions_stops_every_running_uuid() -> None:
    first = "12345678-1234-5678-1234-567812345678"
    second = "87654321-4321-8765-4321-876543218765"
    stopped: list[str] = []
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=[{"uuid": first}, {"uuid": second}])
        stopped.append(str(json.loads(request.content)["uuid"]))
        return httpx.Response(200, json={"message": "stopped"})
    client = DaemonClient(transport=httpx.MockTransport(handler))
    try:
        assert await client.stop_all_motions() == [first, second]
    finally:
        await client.close()
    assert stopped == [first, second]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest -q tests/test_local_control_daemon_client.py -k 'app_and_recorded or stop_all'`

Expected: `AttributeError` for the new methods.

- [ ] **Step 3: Implement strict response parsing**

```python
async def list_installed_apps(self) -> list[dict[str, object]]:
    payload = await self._request("GET", "/api/apps/list-available/installed", "app_catalog")
    if not isinstance(payload, list):
        raise LocalControlError("app_catalog_invalid_response")
    return [self._mapping(item, "app_catalog") for item in payload]


async def running_motions(self) -> list[str]:
    payload = await self._request("GET", "/api/move/running", "motion_status")
    if not isinstance(payload, list):
        raise LocalControlError("motion_status_invalid_response")
    return [str(item["uuid"]) for item in payload if isinstance(item, dict) and "uuid" in item]
```

Use `urllib.parse.quote(value, safe="")` only after higher layers validate names; keep dataset slashes explicitly encoded or assembled through the fixed dataset definition.

- [ ] **Step 4: Run all Daemon-client tests, Ruff, and Mypy**

Run: `uv run pytest -q tests/test_local_control_daemon_client.py && uv run ruff check src/reachy_mini_conversation_app/local_control/daemon_client.py tests/test_local_control_daemon_client.py && uv run mypy src/reachy_mini_conversation_app/local_control/daemon_client.py`

Expected: all pass.

- [ ] **Step 5: Commit the Daemon client extension**

```text
Intent: Reach installed apps and recorded moves without a general proxy
Constraint: Every dynamic segment is validated by a catalog service
Tested: complete Daemon-client test module, Ruff, Mypy
```

---

### Task 3: Implement Installed-App Switch and Rollback

**Files:**
- Create: `src/reachy_mini_conversation_app/local_control/app_catalog.py`
- Create: `tests/test_local_control_app_catalog.py`
- Modify: `src/reachy_mini_conversation_app/local_control/app.py`
- Modify: `tests/test_local_control_api.py`

**Interfaces:**
- Consumes: `DaemonClient.list_installed_apps/start_app/stop_current_app/app_status` and `sanitize_installed_app`.
- Produces: `InstalledAppService.list_apps()`, `switch_app(name)`, `stop_app(name)`, `AppSwitchError(reason, rollback_restored)`; authenticated `/api/apps` routes.

- [ ] **Step 1: Write failing switch-order and rollback tests**

```python
@pytest.mark.asyncio
async def test_switch_stops_current_then_starts_target() -> None:
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [
        {"name": "reachy_mini_qwen_realtime_app", "source_kind": "installed", "extra": {}},
        {"name": "coding_lab", "source_kind": "installed", "extra": {}},
    ]
    daemon.app_status.side_effect = [
        {"state": "running", "error": None, "info": {"name": "reachy_mini_qwen_realtime_app"}},
        None,
        {"state": "running", "error": None, "info": {"name": "coding_lab"}},
    ]
    service = InstalledAppService(daemon, poll_interval_s=0)
    result = await service.switch_app("coding_lab")
    assert result["active"] == "coding_lab"
    daemon.stop_current_app.assert_awaited_once_with()
    daemon.start_app.assert_awaited_once_with("coding_lab")


@pytest.mark.asyncio
async def test_failed_target_restores_previous_app() -> None:
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [
        {"name": "reachy_mini_qwen_realtime_app", "source_kind": "installed", "extra": {}},
        {"name": "coding_lab", "source_kind": "installed", "extra": {}},
    ]
    daemon.app_status.side_effect = [
        {"state": "running", "error": None, "info": {"name": "reachy_mini_qwen_realtime_app"}},
        None,
        {"state": "running", "error": None, "info": {"name": "reachy_mini_qwen_realtime_app"}},
    ]
    daemon.start_app.side_effect = [LocalControlError("target_failed"), {"state": "starting"}]
    with pytest.raises(AppSwitchError) as error:
        await InstalledAppService(daemon, poll_interval_s=0).switch_app("coding_lab")
    assert error.value.reason == "target_start_failed"
    assert error.value.rollback_restored is True
```

```python
@pytest.mark.asyncio
async def test_unknown_and_non_current_apps_are_rejected() -> None:
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [{"name": "coding_lab", "source_kind": "installed", "extra": {}}]
    daemon.app_status.return_value = {"state": "running", "info": {"name": "coding_lab"}, "error": None}
    service = InstalledAppService(daemon, poll_interval_s=0)
    with pytest.raises(AppSwitchError, match="unknown_app"):
        await service.switch_app("run_shell")
    with pytest.raises(AppSwitchError, match="not_current_app"):
        await service.stop_app("marionette")


@pytest.mark.asyncio
async def test_same_app_is_idempotent() -> None:
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [{"name": "coding_lab", "source_kind": "installed", "extra": {}}]
    daemon.app_status.return_value = {"state": "running", "info": {"name": "coding_lab"}, "error": None}
    result = await InstalledAppService(daemon, poll_interval_s=0).switch_app("coding_lab")
    assert result == {"active": "coding_lab", "changed": False}
    daemon.stop_current_app.assert_not_awaited()
    daemon.start_app.assert_not_awaited()
```

```python
@pytest.mark.asyncio
async def test_concurrent_switches_serialize() -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    daemon = AsyncMock()
    daemon.list_installed_apps.return_value = [
        {"name": name, "source_kind": "installed", "extra": {}}
        for name in ("qwen", "coding_lab", "marionette")
    ]
    daemon.app_status.side_effect = [
        {"state": "running", "info": {"name": "qwen"}}, None,
        {"state": "running", "info": {"name": "coding_lab"}},
        {"state": "running", "info": {"name": "coding_lab"}}, None,
        {"state": "running", "info": {"name": "marionette"}},
    ]
    async def start(name: str) -> dict[str, str]:
        if name == "coding_lab":
            entered.set()
            await release.wait()
        return {"state": "starting"}
    daemon.start_app.side_effect = start
    service = InstalledAppService(daemon, poll_interval_s=0)
    first = asyncio.create_task(service.switch_app("coding_lab"))
    await entered.wait()
    second = asyncio.create_task(service.switch_app("marionette"))
    await asyncio.sleep(0)
    assert daemon.start_app.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    assert [call.args[0] for call in daemon.start_app.await_args_list] == ["coding_lab", "marionette"]
```

- [ ] **Step 2: Run service/API tests and verify RED**

Run: `uv run pytest -q tests/test_local_control_app_catalog.py tests/test_local_control_api.py -k 'app_catalog or switch_app or stop_app'`

Expected: import failure for `InstalledAppService` and 404 for new API routes.

- [ ] **Step 3: Implement service and authenticated routes**

```python
class AppSwitchError(RuntimeError):
    def __init__(self, reason: str, rollback_restored: bool) -> None:
        super().__init__(reason)
        self.reason = reason
        self.rollback_restored = rollback_restored


class InstalledAppService:
    def __init__(self, daemon: DaemonClient, *, timeout_s: float = 20.0, poll_interval_s: float = 0.2) -> None:
        self._daemon = daemon
        self._lock = asyncio.Lock()
        self._timeout_s = timeout_s
        self._poll_interval_s = poll_interval_s

    async def switch_app(self, name: str) -> dict[str, object]:
        async with self._lock:
            installed = await self._installed_names()
            if name not in installed:
                raise AppSwitchError("unknown_app", False)
            previous = await self._current_name()
            if previous == name:
                return {"active": name, "changed": False}
            if previous is not None:
                await self._daemon.stop_current_app()
                await self._wait_current(None)
            try:
                await self._daemon.start_app(name)
                await self._wait_current(name)
            except LocalControlError as target_error:
                restored = await self._restore(previous)
                raise AppSwitchError("target_start_failed", restored) from target_error
            return {"active": name, "changed": True}
```

Map stable service reasons to 404/409/502 JSON without leaking Daemon detail.

- [ ] **Step 4: Run app-service and API suites**

Run: `uv run pytest -q tests/test_local_control_app_catalog.py tests/test_local_control_api.py && uv run ruff check src/reachy_mini_conversation_app/local_control/app_catalog.py src/reachy_mini_conversation_app/local_control/app.py tests/test_local_control_app_catalog.py tests/test_local_control_api.py && uv run mypy src/reachy_mini_conversation_app/local_control/app_catalog.py src/reachy_mini_conversation_app/local_control/app.py`

Expected: all pass.

- [ ] **Step 5: Commit installed-app management**

```text
Intent: Switch installed apps without stranding the robot on startup failure
Constraint: Only Daemon-reported installed names may be selected
Tested: service concurrency/rollback tests and authenticated API tests
```

---

### Task 4: Implement Motion Catalog, Ownership, and Emergency Stop

**Files:**
- Create: `src/reachy_mini_conversation_app/local_control/motion_control.py`
- Create: `tests/test_local_control_motion.py`
- Modify: `src/reachy_mini_conversation_app/local_control/app.py`
- Modify: `tests/test_local_control_api.py`

**Interfaces:**
- Consumes: `MOTION_SOURCES`, `DaemonClient` motion methods, `QwenRpcClient.suspend_motion/resume_motion/stop_actions`.
- Produces: `MotionCoordinator.catalog(refresh: bool = False)`, `play(source, name)`, `status()`, `wait_for_idle()`, `stop(resume_qwen=True)`, `emergency_stop()` and `/api/motions*` plus `/api/robot/emergency-stop` routes.

- [ ] **Step 1: Write failing dynamic-catalog and arbitration tests**

```python
@pytest.mark.asyncio
async def test_catalog_reports_live_counts_and_unavailable_music(tmp_path: Path) -> None:
    daemon = AsyncMock()
    daemon.list_recorded_moves.side_effect = lambda dataset: ["happy1", "sad1"] if "emotions" in dataset else ["dance1"]
    catalog = await MotionCoordinator(daemon, AsyncMock(), hf_cache_root=tmp_path).catalog()
    assert catalog["emotion"]["count"] == 2
    assert catalog["pollen_dance"]["moves"][0]["name"] == "dance1"
    assert catalog["music_dance"] == {
        "label": "音乐舞蹈",
        "category": "dance",
        "available": False,
        "count": 0,
        "expected_count": 14,
        "moves": [],
    }


@pytest.mark.asyncio
async def test_play_suspends_qwen_until_daemon_move_finishes(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1"]
    daemon.motor_status.return_value = {"mode": "enabled"}
    daemon.app_status.return_value = {
        "state": "running", "error": None, "info": {"name": "reachy_mini_qwen_realtime_app"}
    }
    daemon.play_recorded_move.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)
    result = await coordinator.play("emotion", "happy1")
    await coordinator.wait_for_idle()
    assert result["status"] == "started"
    daemon.play_recorded_move.assert_awaited_once_with(
        "pollen-robotics/reachy-mini-emotions-library", "happy1"
    )
    qwen.suspend_motion.assert_awaited_once_with()
    qwen.resume_motion.assert_awaited_once_with()
```

```python
@pytest.mark.asyncio
async def test_music_source_queries_daemon_only_when_cache_exists(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)
    assert (await coordinator.catalog())["music_dance"]["available"] is False
    daemon.list_recorded_moves.assert_not_awaited()
    (tmp_path / "datasets--Anne-Charlotte--music").mkdir()
    daemon.list_recorded_moves.return_value = list(MUSIC_DANCE_NAMES)
    assert (await coordinator.catalog(refresh=True))["music_dance"]["count"] == 14


@pytest.mark.asyncio
async def test_unknown_move_and_disabled_motors_fail_closed(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1"]
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)
    with pytest.raises(MotionControlError, match="unknown_move"):
        await coordinator.play("emotion", "run_shell")
    daemon.motor_status.return_value = {"mode": "disabled"}
    with pytest.raises(MotionControlError, match="motors_disabled"):
        await coordinator.play("emotion", "happy1")
    daemon.play_recorded_move.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_and_emergency_have_distinct_motor_semantics(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)
    await coordinator.stop(resume_qwen=True)
    daemon.set_motor_mode.assert_not_awaited()
    await coordinator.emergency_stop()
    daemon.stop_all_motions.assert_awaited()
    daemon.set_motor_mode.assert_awaited_once_with("disabled")
```

```python
@pytest.mark.asyncio
async def test_unknown_source_and_busy_motion_are_rejected(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)
    with pytest.raises(MotionControlError, match="unknown_source"):
        await coordinator.play("shell", "whoami")
    await coordinator._lock.acquire()
    with pytest.raises(MotionControlError, match="motion_busy"):
        await coordinator.play("emotion", "happy1")
    coordinator._lock.release()


@pytest.mark.asyncio
async def test_timeout_keeps_qwen_suspended(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.list_recorded_moves.return_value = ["happy1"]
    daemon.motor_status.return_value = {"mode": "enabled"}
    daemon.app_status.return_value = {"state": "running", "info": {"name": QWEN_APP_NAME}}
    daemon.play_recorded_move.return_value = {"uuid": "12345678-1234-5678-1234-567812345678"}
    daemon.wait_for_motion.side_effect = LocalControlError("motion_timeout")
    coordinator = MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path)
    await coordinator.play("emotion", "happy1")
    await coordinator.wait_for_idle()
    assert (await coordinator.status())["error"] == "motion_timeout"
    qwen.resume_motion.assert_not_awaited()


@pytest.mark.asyncio
async def test_emergency_disables_motors_after_cleanup_failures(tmp_path: Path) -> None:
    daemon, qwen = AsyncMock(), AsyncMock()
    daemon.stop_all_motions.side_effect = LocalControlError("motion_stop_failed")
    qwen.stop_actions.side_effect = QwenUnavailableError("qwen_rpc_unavailable")
    await MotionCoordinator(daemon, qwen, hf_cache_root=tmp_path).emergency_stop()
    daemon.set_motor_mode.assert_awaited_once_with("disabled")
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest -q tests/test_local_control_motion.py tests/test_local_control_api.py -k 'motion or emergency'`

Expected: import failure and missing routes.

- [ ] **Step 3: Implement one-active-motion coordinator**

```python
class MotionControlError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class MotionStatus:
    source: str
    name: str
    uuid: str
    state: Literal["running", "idle", "error"]
    error: str | None = None


async def play(self, source_id: str, name: str) -> dict[str, object]:
    if self._lock.locked():
        raise MotionControlError("motion_busy")
    await self._lock.acquire()
    qwen_suspended = False
    move_started = False
    try:
        definition, available = await self._validated_move(source_id, name)
        if (await self._daemon.motor_status()).get("mode") != "enabled":
            raise MotionControlError("motors_disabled")
        qwen_suspended = await self._suspend_qwen_if_active()
        started = await self._daemon.play_recorded_move(definition.dataset, name)
        move_uuid = started.get("uuid")
        if not isinstance(move_uuid, str):
            raise MotionControlError("motion_invalid_response")
        move_started = True
        self._active = MotionStatus(source_id, name, move_uuid, "running")
        self._monitor = asyncio.create_task(self._monitor_move(move_uuid, qwen_suspended))
        return {"status": "started", "uuid": move_uuid, "source": source_id, "name": name}
    except Exception:
        if qwen_suspended and not move_started:
            await self._qwen.resume_motion()
        self._lock.release()
        raise
```

The monitor releases the lock and resumes Qwen only after normal completion or ordinary cancellation. `emergency_stop()` marks resume forbidden, stops all Daemon UUIDs, clears Qwen actions, and executes motor disable in a final independent attempt.

- [ ] **Step 4: Run complete motion/API checks**

Run: `uv run pytest -q tests/test_local_control_motion.py tests/test_local_control_api.py tests/test_local_control_qwen_client.py && uv run ruff check src/reachy_mini_conversation_app/local_control/motion_control.py src/reachy_mini_conversation_app/local_control/app.py tests/test_local_control_motion.py tests/test_local_control_api.py && uv run mypy src/reachy_mini_conversation_app/local_control/motion_control.py src/reachy_mini_conversation_app/local_control/app.py`

Expected: all pass.

- [ ] **Step 5: Commit motion ownership and emergency stop**

```text
Intent: Expose every cached expression without allowing stacked or competing motor output
Constraint: Qwen audio stays connected while Daemon owns a recorded move
Tested: catalog, arbitration, cancellation, timeout, and emergency-stop suites
```

---

### Task 5: Add Saved-Network Switching

**Files:**
- Modify: `src/reachy_mini_conversation_app/local_control/app.py`
- Modify: `tests/test_local_control_api.py`

**Interfaces:**
- Consumes: existing `DaemonClient.wifi_status()` and sealed `connect_wifi(ssid, "")`.
- Produces: `POST /api/wifi/switch` with `SavedWifiPayload(ssid: str)` and a `202 {"status": "switching", "ssid": ...}` response.

- [ ] **Step 1: Write failing saved-network tests**

```python
def test_saved_network_switch_requires_live_known_ssid() -> None:
    client, daemon, _qwen = _logged_in_client()
    with client:
        switched = client.post("/api/wifi/switch", json={"ssid": "BackupNet"})
        rejected = client.post("/api/wifi/switch", json={"ssid": "InjectedNet"})
    assert switched.status_code == 202
    assert switched.json() == {"status": "switching", "ssid": "BackupNet"}
    assert rejected.status_code == 404
    daemon.connect_wifi.assert_awaited_once_with("BackupNet", "")


def test_current_saved_network_is_idempotent_and_bad_ssid_is_rejected() -> None:
    client, daemon, _qwen = _logged_in_client()
    with client:
        current = client.post("/api/wifi/switch", json={"ssid": "EventNet"})
        malformed = client.post("/api/wifi/switch", json={"ssid": "bad\nssid"})
    assert current.json() == {"status": "already_connected", "ssid": "EventNet"}
    assert malformed.status_code == 422
    daemon.connect_wifi.assert_not_awaited()
```

Update `_clients()` with this exact fixture value:

```python
daemon.wifi_status.return_value = {
    "mode": "wlan",
    "known_networks": ["EventNet", "BackupNet"],
    "connected_network": "EventNet",
}
```

- [ ] **Step 2: Run the API test and verify RED**

Run: `uv run pytest -q tests/test_local_control_api.py -k saved_network`

Expected: 404 because `/api/wifi/switch` is missing.

- [ ] **Step 3: Implement revalidation and sealed activation**

```python
@app.post("/api/wifi/switch", status_code=202)
async def switch_saved_wifi(payload: SavedWifiPayload, _session: str = Depends(require_session)) -> dict[str, str]:
    status = await daemon_client.wifi_status()
    known = status.get("known_networks")
    if not isinstance(known, list) or payload.ssid not in known:
        raise HTTPException(status_code=404, detail="unknown_saved_network")
    if status.get("connected_network") == payload.ssid:
        return {"status": "already_connected", "ssid": payload.ssid}
    await daemon_client.connect_wifi(payload.ssid, "")
    return {"status": "switching", "ssid": payload.ssid}
```

- [ ] **Step 4: Run API, Ruff, and Mypy checks**

Run: `uv run pytest -q tests/test_local_control_api.py && uv run ruff check src/reachy_mini_conversation_app/local_control/app.py tests/test_local_control_api.py && uv run mypy src/reachy_mini_conversation_app/local_control/app.py`

Expected: all pass.

- [ ] **Step 5: Commit saved-network switching**

```text
Intent: Reuse saved Wi-Fi credentials without exposing or re-entering passwords
Constraint: Switching normally disconnects the requesting phone before confirmation
Tested: known/unknown/current-network API cases and secret-free response checks
```

---

### Task 6: Build the Mobile Secondary Pages

**Files:**
- Modify: `src/reachy_mini_conversation_app/local_control/static/index.html`
- Create: `src/reachy_mini_conversation_app/local_control/static/apps.html`
- Create: `src/reachy_mini_conversation_app/local_control/static/motions.html`
- Modify: `src/reachy_mini_conversation_app/local_control/static/setup.html`
- Modify: `src/reachy_mini_conversation_app/local_control/static/app.js`
- Modify: `src/reachy_mini_conversation_app/local_control/static/style.css`
- Modify: `src/reachy_mini_conversation_app/local_control/app.py`
- Modify: `tests/test_local_control_static.py`

**Interfaces:**
- Consumes: every authenticated API from Tasks 3–5.
- Produces: accessible `/apps` and `/motions` pages, dynamic cards/tabs/search, saved-network rows, confirmation dialogs, ordinary motion stop, and true emergency stop.

- [ ] **Step 1: Write failing static contracts**

```python
def test_catalog_pages_have_mobile_navigation_and_no_external_assets() -> None:
    apps = _read("apps.html")
    motions = _read("motions.html")
    combined = apps + motions + _read("app.js")
    assert 'data-page="apps"' in apps
    assert 'data-page="motions"' in motions
    assert 'id="motion-search"' in motions
    assert 'data-motion-tab="emotion"' in motions
    assert 'data-motion-tab="dance"' in motions
    assert not re.search(r"https?://", combined)


def test_emergency_footer_uses_motor_disabling_route() -> None:
    assert '/api/robot/emergency-stop' in _read("app.js")
    assert 'data-action="motion-stop"' in _read("motions.html")


def test_catalog_pages_include_confirmations_saved_networks_and_mobile_safety() -> None:
    apps, setup = _read("apps.html"), _read("setup.html")
    css, script = _read("style.css"), _read("app.js")
    assert "停止当前应用并启动" in apps
    assert 'id="saved-network-list"' in setup
    assert "已连接" in script
    assert "min-height: 48px" in css
    assert "env(safe-area-inset-bottom)" in css
    assert not re.search(r"localStorage\.(setItem|getItem)\([^\n]*(password|pin)", script, re.IGNORECASE)
```

- [ ] **Step 2: Run static tests and verify RED**

Run: `uv run pytest -q tests/test_local_control_static.py`

Expected: missing `apps.html` and `motions.html`.

- [ ] **Step 3: Add page routes and semantic markup**

```python
@app.get("/apps", include_in_schema=False)
async def apps_page() -> FileResponse:
    return FileResponse(resolved_static_dir / "apps.html")


@app.get("/motions", include_in_schema=False)
async def motions_page() -> FileResponse:
    return FileResponse(resolved_static_dir / "motions.html")
```

Use this semantic structure rather than clickable divs:

```html
<dialog id="app-switch-dialog" aria-labelledby="app-switch-title">
  <h2 id="app-switch-title">切换应用</h2>
  <p>停止当前应用并启动所选应用？</p>
  <button value="cancel">取消</button>
  <button value="confirm" class="button button--primary">确认切换</button>
</dialog>
<p id="catalog-message" class="message" aria-live="polite"></p>
```

- [ ] **Step 4: Implement page-specific JavaScript**

```javascript
async function refreshApps() {
  const apps = await api("/api/apps");
  renderApps(document.querySelector("#app-list"), apps);
}

async function refreshMotions() {
  const catalog = await api("/api/motions/catalog");
  renderMotionCatalog(catalog, document.querySelector("#motion-search").value);
}

async function switchSavedNetwork(ssid) {
  if (!window.confirm(`切换到 ${ssid} 后，本页面会暂时断开。继续吗？`)) return;
  await api("/api/wifi/switch", {method: "POST", body: JSON.stringify({ssid})});
  message(document.querySelector("#wifi-message"), "请让手机加入目标网络，再打开 reachy-mini.local:7861。", "success");
}
```

The status poll applies these exact states:

```javascript
const running = motionStatus.state === "running";
document.querySelectorAll("[data-motion-name]").forEach((button) => {
  button.disabled = running || button.dataset.available !== "true";
});
document.querySelector("#active-motion").textContent = running
  ? `正在执行：${motionStatus.name}`
  : "当前没有动作";
```

Unavailable sources render `未安装此动作库` and no element with
`data-motion-name`. Both `index.html` and `motions.html` retain the fixed
emergency footer.

- [ ] **Step 5: Run static/API tests and browser-width smoke**

Run: `uv run pytest -q tests/test_local_control_static.py tests/test_local_control_api.py`

Launch the static files with:

```text
uv run python -m http.server 8761 --directory src/reachy_mini_conversation_app/local_control/static
```

Open `/apps.html` and `/motions.html`, unhide `#control-panel` in the browser test
context, and verify 390×844 plus 412×915 viewports: no horizontal overflow,
dialogs fit, tabs/search remain visible, and emergency stop clears the bottom
safe area.

Expected: tests pass and both viewport checks pass.

- [ ] **Step 6: Commit the mobile UI**

```text
Intent: Make large robot catalogs usable from a phone without crowding the dashboard
Constraint: Pages must work from an isolated LAN with no external assets
Tested: static contracts, API integration, iPhone/Android viewport smoke
```

---

### Task 7: Bump qwen.4, Document, and Run Host Release Gates

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`
- Modify: `tests/test_community_release.py`
- Modify: `tests/test_local_control_security.py` if the final API surface requires additional assertions.

**Interfaces:**
- Produces: immutable `1.0.1+qwen.4` wheel and public usage documentation.
- Consumes: all implementation tasks.

- [ ] **Step 1: Write the failing release-version assertion**

```python
def test_community_release_version_is_qwen_4() -> None:
    assert metadata.version("reachy_mini_qwen_realtime_app") == "1.0.1+qwen.4"
```

- [ ] **Step 2: Run the release test and verify RED**

Run: `uv run pytest -q tests/test_community_release.py -k qwen_4`

Expected: reports current `1.0.1+qwen.3`.

- [ ] **Step 3: Bump version and update README**

Set project version to `1.0.1+qwen.4`, run `uv lock`, and document:

```markdown
### Local mobile catalogs

- `http://reachy-mini.local:7861/apps` manages installed apps.
- `http://reachy-mini.local:7861/motions` searches cached emotions and dances.
- Saved Wi-Fi networks can be switched from `/setup` without re-entering passwords.
- Music dances appear only when the optional `Anne-Charlotte/music` cache is installed.
```

- [ ] **Step 4: Run every host gate**

Run, in order:

```text
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
git diff --check
uv build --wheel --out-dir dist_local_control_qwen4
```

Inspect the wheel file list/count/path budget, install it into a clean smoke venv, and run generic plus known-local-secret scans. Expected: all pass with no sensitive artifact.

- [ ] **Step 5: Commit the qwen.4 host candidate**

```text
Intent: Give the expanded local controller an unambiguous upgrade and rollback identity
Constraint: qwen.3 remains the immutable production rollback baseline
Tested: full test/static/build/install/privacy gate chain
```

---

### Task 8: Deploy, Seed Optional Music Cache, and Complete Hardware Acceptance

**Files:**
- Update local evidence only: `F:/Git/ReachyMini/.omx/ultragoal/evidence/local_mobile_control/host_acceptance.json`
- Update local evidence only: `F:/Git/ReachyMini/.omx/ultragoal/evidence/local_mobile_control/device_acceptance.json`
- Update local evidence only: `F:/Git/ReachyMini/.omx/ultragoal/evidence/local_mobile_control/CHECKPOINT.md`
- Update local evidence only: `F:/Git/ReachyMini/.omx/ultragoal/evidence/local_mobile_control/release_notes_v1.0.1-qwen.4.md`

**Interfaces:**
- Produces: deployed qwen.4 wheel, optional device-local music cache, immutable hashes, real-device proof, and synchronized GitHub branch.
- Consumes: qwen.4 wheel plus existing qwen.3 rollback bundle.

- [ ] **Step 1: Capture pre-deployment state and rollback proof**

Record Daemon/App versions, current app, motor mode, gateway service state, qwen.3 wheel hash, and qwen.3 backup path. Verify no secrets are copied into evidence.

- [ ] **Step 2: Stage optional music data outside Git**

Use the official Hugging Face dataset source to download `Anne-Charlotte/music`
with `hf download Anne-Charlotte/music --repo-type dataset --cache-dir <temporary-cache>`.
Verify the dataset file count/hash manifest and its license/readme. Transfer only
the generated `datasets--Anne-Charlotte--music` directory into:

```text
/home/pollen/.cache/huggingface/hub/datasets--Anne-Charlotte--music
```

Set owner `pollen`, directories `0755`, files `0644`. Do not place the cache under the repository, wheel, or evidence directory. If the official source is unreachable, leave music unavailable and do not block Pollen emotions/dances.

- [ ] **Step 3: Install qwen.4 with rollback preserved**

Stop the current app and local gateway, upload the standard wheel filename, force-reinstall into `/venvs/apps_venv`, restart the gateway, start Qwen, then verify package version and remote SHA-256 equal the host artifact.

- [ ] **Step 4: Run installed-app hardware tests**

From the authenticated mobile gateway:

1. Confirm four installed apps render.
2. Switch Qwen → Coding Lab after the confirmation dialog.
3. Switch Coding Lab → Qwen.
4. Verify Qwen reaches `running`, `error=null`, and backend connected.

- [ ] **Step 5: Run motion and emergency hardware tests**

1. Verify live catalog counts and availability flags.
2. Play one emotion and one Pollen recorded dance.
3. If cached, play `michael-jackson-thriller` from `music_dance`.
4. During a second dance press ordinary Stop; verify motors remain enabled.
5. During a third dance press Emergency Stop; verify all running UUIDs clear and motors become disabled.
6. Press Wake; verify motors enable and a safe left/right action moves again.
7. Verify Qwen stays connected through normal moves and reconnects to motion after wake.

- [ ] **Step 6: Complete phone/network and regression checks**

Have the user switch between saved networks from the phone and confirm the expected disconnect/rejoin flow. Recheck Tina voice, camera grounding, one safe action, Exa search, `seed_fungus`, app/gateway status, and logs for WebSocket 1007, process exit, traceback, or Daemon error.

- [ ] **Step 7: Record immutable evidence and push**

Write host/device JSON with exact commit, wheel hash/bytes/files, catalog counts, selected moves, switch sequence, motor states, and remaining physical-device gaps. Commit code/docs with Lore trailers, push `feat/local-mobile-control`, and verify local/remote commit plus tree SHA equality through GitHub.

Expected final state: Daemon 1.9.0, app `1.0.1+qwen.4` running with no error, local gateway active/enabled, motors enabled, Qwen connected, working voice/vision/Exa, and qwen.3 rollback intact.
