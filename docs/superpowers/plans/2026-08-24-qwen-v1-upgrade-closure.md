# Reachy Mini Qwen v1 Upgrade Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the immutable `v1.0.1-qwen.1` release to the Reachy Mini Wireless robot, repair only reproduced defects through TDD, and close the upgrade with complete real-device evidence and a verified rollback path.

**Architecture:** Treat the public wheel as an immutable candidate and the robot as a reversible deployment target. Back up the working v0.5 state, deploy and test qwen.1 unchanged, then create qwen.2 only if a production defect is reproduced. Keep Daemon 1.9.0, private configuration, the `seed_fungus` profile, and the pre-upgrade motor policy outside the application version change.

**Tech Stack:** Python 3.12, uv, pytest, Ruff, Mypy, setuptools wheels, Reachy Mini Daemon REST/JSON-RPC, Paramiko/SFTP, Qwen Realtime WebSocket, Exa Streamable HTTP MCP.

**Spec:** `docs/superpowers/specs/2026-08-24-qwen-v1-upgrade-closure-design.md`

## Global Constraints

- Keep Reachy Mini Daemon and the synchronized Apps SDK at stable `1.9.0`.
- Candidate SHA-256 must equal `3F4037AE2F6F478140EE2EDDB2105E83A3D2EE14770754D52E958928E7C4D535`.
- Never print, commit, upload, or copy private keys, Qwen credentials, Exa credentials, or private profile content into host evidence.
- Preserve active/startup profile `seed_fungus`, Qwen region/workspace/URL, and voice `Tina`.
- Never overwrite or retag `v1.0.1-qwen.1`; reproduced code fixes produce `1.0.1+qwen.2`.
- Motion is allowed only inside an announced safety window and must be small-amplitude.
- Restore the pre-upgrade motor mode, `enabled`, at final handoff or after rollback.
- Use the isolated worktree `F:\Git\ReachyMini\.worktrees\community_v1_release`; do not modify unrelated repositories or the non-repository workspace root.

---

### Task 1: Freeze host and device baselines

**Files:**
- Read: `.omx/ultragoal/evidence/published_v1_0_1_qwen_1_keepalive_final/reachy_mini_qwen_realtime_app-1.0.1+qwen.1-py3-none-any.whl`
- Read: `docs/superpowers/specs/2026-08-24-qwen-v1-upgrade-closure-design.md`
- Create after execution: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\baseline.json`

**Interfaces:**
- Consumes: Daemon REST at `http://192.168.50.78:8000` and the published wheel.
- Produces: redacted baseline values and the exact candidate hash used by every later task.

- [ ] **Step 1: Verify the isolated worktree and public artifact**

Run:

```powershell
git -C F:\Git\ReachyMini\.worktrees\community_v1_release status --short
git -C F:\Git\ReachyMini\.worktrees\community_v1_release branch --show-current
Get-FileHash F:\Git\ReachyMini\.omx\ultragoal\evidence\published_v1_0_1_qwen_1_keepalive_final\reachy_mini_qwen_realtime_app-1.0.1+qwen.1-py3-none-any.whl -Algorithm SHA256
```

Expected: clean worktree except committed planning files; branch `release/community-qwen-v1.0.1-qwen.1`; exact required SHA-256.

- [ ] **Step 2: Capture the read-only robot baseline**

Run Daemon requests for `/api/daemon/status`, `/api/apps/current-app-status`, and `/api/motors/status`. Record only version, states, error fields, motor mode, and timestamp. Do not serialize hardware ID, WLAN credentials, or environment variables.

Expected: Daemon `1.9.0`, daemon/backend errors empty, no running app at the checkpoint, motors `enabled`.

- [ ] **Step 3: Confirm SSH access without changing the robot**

Use Paramiko with host `192.168.50.78`, user `pollen`, and the credential supplied through process environment `REACHY_DEPLOY_PASSWORD`. Run only:

```bash
id -un
uname -m
/venvs/apps_venv/bin/python -V
/venvs/apps_venv/bin/python -m pip show reachy-mini-qwen-realtime-app
```

Expected: user `pollen`, architecture `aarch64`, Python available, current distribution `0.5.0+qwen.1`.

---

### Task 2: Create and verify the robot rollback bundle

**Files:**
- Create on robot: `/home/pollen/reachy-backups/pre-qwen-v1-upgrade-$stamp/`, where the preceding command sets `$stamp` from the robot clock.
- Create on host: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\backup_manifest_redacted.json`

**Interfaces:**
- Consumes: the v0.5 Apps environment and private instance files.
- Produces: a self-contained rollback directory and redacted manifest.

- [ ] **Step 1: Create a timestamped directory with restrictive permissions**

Run remotely:

```bash
stamp=$(date +%Y%m%d%H%M%S)
backup=/home/pollen/reachy-backups/pre-qwen-v1-upgrade-$stamp
install -d -m 700 "$backup"
printf '%s\n' "$backup"
```

Validate the resolved path begins with `/home/pollen/reachy-backups/pre-qwen-v1-upgrade-` before any copies.

- [ ] **Step 2: Back up application state**

Copy the installed v0.5 rollback wheel, `pip freeze`, application metadata, private `.env`, external profile tree, instance/startup settings, and service snapshot into the backup. Preserve source file modes; force credential-bearing copies to mode `0600`. Do not download their contents to the host.

- [ ] **Step 3: Verify rollback contents without exposing secrets**

Record only relative filename, byte size, mode, and SHA-256. Confirm the v0.5 wheel hash is `905E91850062614C25A3BAB41D6397810AEC43A4EDB026F7E4C4CFC0DBE7C4A7`.

- [ ] **Step 4: Exercise a non-destructive rollback preflight**

Use `/venvs/apps_venv/bin/python -m pip install --dry-run "$backup/reachy_mini_qwen_realtime_app-0.5.0+qwen.1-py3-none-any.whl"` when supported; otherwise inspect the same wheel with `unzip -p`. Confirm distribution version `0.5.0+qwen.1` and the `reachy_mini_apps` entry point before continuing.

---

### Task 3: Deploy the immutable qwen.1 candidate

**Files:**
- Upload temporarily: `/tmp/reachy_mini_qwen_realtime_app-1.0.1+qwen.1-py3-none-any.whl`
- Read on robot: private environment/profile/instance paths discovered in Task 2.

**Interfaces:**
- Consumes: exact public candidate wheel and Task 2 backup.
- Produces: installed `1.0.1+qwen.1` with preserved private state.

- [ ] **Step 1: Transfer and verify the candidate**

Upload with SFTP, set mode `0600`, calculate SHA-256 on the robot, and stop if it differs from the required candidate hash.

- [ ] **Step 2: Stop the app and wait for an empty app slot**

If `/api/apps/current-app-status` is non-null, POST `/api/apps/stop-current-app`. Poll until the result is null. A `400` from a redundant stop is accepted only when the following status is null; a persistent `stopping` state is evidence and requires a controlled Daemon restart before installation.

- [ ] **Step 3: Install the candidate without changing Daemon dependencies**

Run remotely:

```bash
/venvs/apps_venv/bin/python -m pip install --no-deps --force-reinstall /tmp/reachy_mini_qwen_realtime_app-1.0.1+qwen.1-py3-none-any.whl
/venvs/apps_venv/bin/python -m pip show reachy-mini-qwen-realtime-app
/venvs/apps_venv/bin/python -c "import importlib.metadata as m; print(m.version('reachy-mini-qwen-realtime-app'))"
/venvs/apps_venv/bin/python -c "import reachy_mini; print(reachy_mini.__version__)"
```

Expected: application `1.0.1+qwen.1`; Reachy Mini SDK still `1.9.0`.

- [ ] **Step 4: Start through the Daemon and verify the new UI**

POST `/api/apps/start-app/reachy_mini_qwen_realtime_app`, poll until `running`, then require empty app error, UI HTTP 200, Qwen preflight ready, and JSON-RPC `/rpc` availability. Capture logs for `python -m`, migration, profile selection, tool registry, Qwen session initialization, and any traceback.

---

### Task 4: Reproduce the complete known-defect matrix unchanged

**Files:**
- Reuse: `F:\Git\ReachyMini\.omx\ultragoal\evidence\device_rpc_status_probe.py`
- Reuse: `F:\Git\ReachyMini\.omx\ultragoal\evidence\device_voice_control.py`
- Reuse: `F:\Git\ReachyMini\.omx\ultragoal\evidence\device_camera_frame_stats.py`
- Reuse: `F:\Git\ReachyMini\.omx\ultragoal\evidence\device_exa_probe.py`
- Create: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\candidate_matrix.json`

**Interfaces:**
- Consumes: running immutable qwen.1 candidate.
- Produces: one pass/fail result and exact evidence for every known defect class.

- [ ] **Step 1: Exercise lifecycle and RPC**

Perform app stop/start twice, then one Daemon restart. After each transition require Daemon `1.9.0`, app `running`, error empty, UI 200, Qwen ready, and no state remaining in `stopping`. Probe `apps.status`, `personalities.get`, `tools.catalog`, and `voices.current` over the Daemon relay.

- [ ] **Step 2: Exercise personality and voice persistence**

Apply `seed_fungus`, persist it, reload it, and measure elapsed time. Require completion below 10 seconds, current/startup both `seed_fungus`, voice `Tina`, and no unsupported-voice fallback or timeout. Restart the app and repeat the reads.

- [ ] **Step 3: Exercise tool catalog correctness**

Require user capabilities for camera, web search, head movement, emotion, dance, and their stop/idle companions. Reject `background_tool_manager` and `tool_constants` as selectable tools. System task-status/cancel helpers may be implicit.

- [ ] **Step 4: Exercise grounded camera flow**

Ask Qwen explicitly to call the camera and describe the current scene. Require a new camera tool call, a fresh 1280x720 frame, image submission, grounded text, and no `input_audio_buffer.commit`, VAD, Base64-size, or WebSocket error.

- [ ] **Step 5: Exercise Exa in the same session**

Call `web_search` for a current fact, require bounded results and at least one HTTP-200 source, then confirm camera and motion tools remain registered. Record only queries, provider, character count, and source URLs.

- [ ] **Step 6: Exercise small physical motion**

Announce the motion window, confirm motors enabled, invoke `move_head` left then front, and measure a bounded yaw delta followed by neutral return. Invoke one emotion and stop it. Abort on backend/control-loop error or unexpected amplitude.

---

### Task 5: Repair only reproduced production defects through TDD

**Files:**
- Conditional modify: `src/reachy_mini_conversation_app/qwen_realtime.py`
- Conditional modify: `src/reachy_mini_conversation_app/personality_routes.py`
- Conditional modify: `src/reachy_mini_conversation_app/profile_toolsets.py`
- Conditional modify: `src/reachy_mini_conversation_app/profile_tool_routes.py`
- Conditional modify: `src/reachy_mini_conversation_app/startup_settings.py`
- Conditional modify: `src/reachy_mini_conversation_app/main.py`
- Conditional test: `tests/test_qwen_realtime.py`
- Conditional test: `tests/test_personality_routes.py`
- Conditional test: `tests/test_profile_toolsets.py`
- Conditional test: `tests/test_startup_settings.py`
- Conditional test: `tests/test_main.py`
- Modify only if a code patch is required: `pyproject.toml`
- Modify only if a code patch is required: `tests/test_community_release.py`

**Interfaces:**
- Consumes: one precise candidate failure from Task 4.
- Produces: minimal regression-tested fix or a documented environmental repair with no production diff.

- [ ] **Step 1: State one root-cause hypothesis**

For the first failed matrix item, identify the failing component boundary and record one hypothesis. Do not combine lifecycle, RPC, Qwen protocol, motion, and profile changes in one attempt.

- [ ] **Step 2: Write and run one failing regression test**

Place the test in the matching file above and use the corresponding fixed test name:

- Qwen protocol: `test_qwen_session_update_is_serialized_with_camera_commit`
- personality RPC: `test_personality_apply_returns_before_rpc_timeout`
- tool catalog: `test_tool_catalog_excludes_internal_modules`
- startup persistence: `test_startup_settings_preserve_seed_fungus_and_tina`
- module launch: `test_module_runner_starts_branded_app_under_sdk_1_9`

Run the selected test with one of these concrete commands:

```powershell
uv run pytest tests/test_qwen_realtime.py::test_qwen_session_update_is_serialized_with_camera_commit -vv
uv run pytest tests/test_personality_routes.py::test_personality_apply_returns_before_rpc_timeout -vv
uv run pytest tests/test_profile_toolsets.py::test_tool_catalog_excludes_internal_modules -vv
uv run pytest tests/test_startup_settings.py::test_startup_settings_preserve_seed_fungus_and_tina -vv
uv run pytest tests/test_community_release.py::test_module_runner_starts_branded_app_under_sdk_1_9 -vv
```

Execute only the command belonging to the reproduced component. Require a behavioral failure for the reproduced defect, not an import/setup error. If the test passes, revise that named test until it isolates the live failure.

- [ ] **Step 3: Implement the smallest fix and verify GREEN**

Change only the owning production file, rerun the focused test, then its full test module. Keep protocol locks, privacy boundaries, SDK 1.9 compatibility, and existing tool schemas intact.

- [ ] **Step 4: Repeat one defect at a time**

Return to Step 1 for each remaining reproduced failure. Environmental state repairs, such as clearing a stale Daemon app slot or restoring motor mode, must not create application code changes.

- [ ] **Step 5: Version a patched artifact only when production code changed**

Change `pyproject.toml` to `version = "1.0.1+qwen.2"`, update the exact version assertion in `tests/test_community_release.py`, update README/release notes with only verified fixes, and commit each defect with Lore trailers including RED/GREEN evidence. If no production code changed, leave qwen.1 untouched.

---

### Task 6: Run host gates and build the deployable artifact

**Files:**
- Build output: `dist/reachy_mini_qwen_realtime_app-1.0.1+qwen.2-py3-none-any.whl` only when Task 5 changed production code.
- Create/update: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\host_gates.json`

**Interfaces:**
- Consumes: unchanged qwen.1 or the reviewed qwen.2 patch tree.
- Produces: exact install candidate plus host verification evidence.

- [ ] **Step 1: Run the complete host gate**

Run from the isolated worktree:

```powershell
uv lock --check
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -q
```

Require zero failures and zero lint/type errors.

- [ ] **Step 2: Build and inspect when qwen.2 exists**

Run:

```powershell
Remove-Item -Recurse -Force -LiteralPath dist -ErrorAction SilentlyContinue
uv build --wheel
python F:\Git\ReachyMini\.omx\ultragoal\evidence\v1_privacy_scan.py dist\*.whl
python F:\Git\ReachyMini\.omx\ultragoal\evidence\v1_wheel_smoke.py dist\*.whl
```

Before the recursive removal, resolve `dist` and confirm it is exactly the worktree's `dist` directory. Record wheel SHA-256 and size. If qwen.1 required no code patch, re-use the already verified public wheel and skip deletion/build.

- [ ] **Step 3: Deploy the final candidate**

For qwen.2, repeat Task 3 transfer/hash/install/start. For unchanged qwen.1, retain the existing installation. In both cases require Apps SDK `1.9.0` after any Daemon restart.

---

### Task 7: Complete real-device acceptance, rollback proof, and handoff

**Files:**
- Create: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\real_device_acceptance.json`
- Create: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\soak_journal.jsonl`
- Create: `F:\Git\ReachyMini\.omx\ultragoal\evidence\qwen_v1_upgrade_20260824\FINAL_HANDOFF.md`

**Interfaces:**
- Consumes: final installed candidate and rollback bundle.
- Produces: completion evidence and recoverable final robot state.

- [ ] **Step 1: Repeat all functional gates on the final artifact**

Repeat lifecycle/RPC, profile/Tina, tool catalog, physical Chinese voice, grounded camera, Exa, and small motion tests. Record tool calls, transcript summaries, audio byte/duration evidence, objective frame statistics, pose deltas, errors, and timings without secrets or retained camera images.

- [ ] **Step 2: Run restart persistence**

Stop/start the app, restart Daemon once, wait for Apps SDK synchronization, and require automatic discovery, application `running`, UI 200, Qwen ready, `seed_fungus` current/startup, Tina, correct tools, and Daemon/backend errors empty.

- [ ] **Step 3: Run a 35-minute idle soak**

Sample Daemon/app/Qwen state every two minutes for at least 2,100 seconds. Scan the complete journal for `1007`, `Process exited`, `Traceback`, `Daemon error`, Qwen/backend error, commit/VAD error, and repeated reconnection. Any match invalidates the soak until explained and repaired.

- [ ] **Step 4: Verify rollback readiness without changing the passing final state**

Recheck the rollback wheel hash, backup file modes, required private-state entries, and rollback commands. Do not reinstall v0.5 after a passing final acceptance. If final acceptance fails irrecoverably, perform the actual rollback and verify the complete v0.5 baseline instead.

- [ ] **Step 5: Restore final motor and cleanup state**

Set motors to the pre-upgrade `enabled` mode, confirm app running and all error fields empty, and remove only `/tmp` candidate files. Retain the timestamped backup. Record every removed path.

- [ ] **Step 6: Commit and hand off**

Commit only repository code/docs/tests that were required by reproduced defects. Keep robot evidence outside public commits until privacy scanning passes. The handoff must list installed version/hash, Daemon/SDK versions, backup path, host gates, real-device gates, soak interval, motor mode, and remaining limitations.
