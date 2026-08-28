# Local Media Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PIN-protected, HF-free silent live video plus speaker and microphone volume controls to the Reachy Mini LAN mobile controller.

**Architecture:** A dependency-free browser client consumes the existing local GStreamer WebRTC producer on port 8443 and deliberately rejects audio/control capabilities. The FastAPI gateway exposes four fixed, authenticated volume operations through the existing loopback-only `DaemonClient`; it never becomes a general proxy.

**Tech Stack:** Python 3.11+, FastAPI, httpx, vanilla JavaScript, WebSocket, WebRTC, HTML/CSS, pytest, Node `node:test`.

**Spec:** `docs/superpowers/specs/2026-08-28-local-media-controls-design.md`

## Global Constraints

- Keep Reachy Mini Daemon at `1.9.0`.
- Release package version is `1.0.1+qwen.5`; Git tag is `v1.0.1-qwen.5` only after true-device acceptance.
- Add no runtime or development dependency.
- Do not use Hugging Face, cloud signalling, STUN, CDN assets, `getUserMedia`, or phone microphone/camera permissions.
- Video is silent: discard remote audio tracks and send no media or robot commands upstream.
- Every control API requires the existing PIN session and validates values before loopback I/O.
- Preserve Qwen, motor, Wi-Fi, app-switching, motion-catalog, and emergency-stop behaviour.

---

### Task 1: Authenticated Volume Boundary

**Files:**
- Modify: `tests/test_local_control_daemon_client.py`
- Modify: `tests/test_local_control_api.py`
- Modify: `src/reachy_mini_conversation_app/local_control/daemon_client.py`
- Modify: `src/reachy_mini_conversation_app/local_control/app.py`

**Interfaces:**
- Produces: `DaemonClient.speaker_volume() -> dict[str, object]`
- Produces: `DaemonClient.set_speaker_volume(volume: int) -> dict[str, object]`
- Produces: `DaemonClient.microphone_volume() -> dict[str, object]`
- Produces: `DaemonClient.set_microphone_volume(volume: int) -> dict[str, object]`
- Produces: authenticated `/api/media/volume` and `/api/media/microphone` GET/POST routes.

- [ ] **Step 1: Write failing Daemon-client tests**

  Add table-driven tests that assert exact method/path/body tuples and literal sanitized responses:

  ```python
  assert await client.speaker_volume() == {"volume": 42, "platform": "Linux", "device": "Reachy Mini Audio"}
  assert await client.set_speaker_volume(55) == {"volume": 55, "platform": "Linux", "device": "Reachy Mini Audio"}
  assert await client.microphone_volume() == {"volume": 61, "platform": "Linux", "device": "Reachy Mini Audio"}
  assert await client.set_microphone_volume(73) == {"volume": 73, "platform": "Linux", "device": "Reachy Mini Audio"}
  assert seen == [
      ("GET", "/api/volume/current", None),
      ("POST", "/api/volume/set", {"volume": 55}),
      ("GET", "/api/volume/microphone/current", None),
      ("POST", "/api/volume/microphone/set", {"volume": 73}),
  ]
  ```

- [ ] **Step 2: Verify the focused tests fail for missing methods**

  Run: `uv run pytest tests/test_local_control_daemon_client.py -k volume -q`

  Expected: FAIL because the four `DaemonClient` methods do not exist.

- [ ] **Step 3: Implement the smallest fixed-path client surface**

  Add a private `_volume_response(payload, operation)` validator that accepts only a mapping with integer
  `volume` in `0..100` and string `platform`/`device`; otherwise raise `<operation>_invalid_response`. Validate
  writes with a shared `_validate_volume` that rejects `bool`, floats, strings, and out-of-range integers.

- [ ] **Step 4: Verify client tests pass**

  Run: `uv run pytest tests/test_local_control_daemon_client.py -k volume -q`

  Expected: all volume-focused tests PASS.

- [ ] **Step 5: Write failing authenticated API tests**

  Assert unauthenticated GET/POST requests return 401, authenticated reads return literal values, valid writes
  await the exact client methods, and `-1`, `101`, `1.5`, `true`, and `"50"` return 422 without awaiting a write.

- [ ] **Step 6: Verify the API tests fail for missing routes**

  Run: `uv run pytest tests/test_local_control_api.py -k media_volume -q`

  Expected: FAIL with 404 responses.

- [ ] **Step 7: Add Pydantic payload and four authenticated routes**

  Use `StrictInt` plus `Field(ge=0, le=100)` and return the client response directly. Do not accept path values,
  arbitrary Daemon URLs, device names, or test-sound commands.

- [ ] **Step 8: Verify backend focused and regression tests**

  Run: `uv run pytest tests/test_local_control_daemon_client.py tests/test_local_control_api.py -q`

  Expected: PASS with zero failures.

### Task 2: Dependency-Free Local WebRTC State Machine

**Files:**
- Create: `src/reachy_mini_conversation_app/local_control/static/local-webrtc.js`
- Create: `tests/js/test_local_webrtc.mjs`

**Interfaces:**
- Produces: `window.ReachyLocalVideo` class with `connect()`, `disconnect()`, and `state`.
- Constructor consumes `{ hostname, video, status, WebSocketCtor, RTCPeerConnectionCtor, timers }` for real browser use and deterministic tests.

- [ ] **Step 1: Write failing Node protocol tests**

  Test with small in-memory fake WebSocket/peer classes and hand-authored messages. Assert:

  ```javascript
  assert.deepEqual(sent[0], { type: "setPeerStatus", roles: ["listener"], meta: { name: "local-mobile-control" } });
  assert.deepEqual(sent[1], { type: "list" });
  assert.deepEqual(sent[2], { type: "startSession", peerId: "producer-1" });
  assert.equal(video.srcObject.getVideoTracks()[0], videoTrack);
  assert.equal(audioTrack.enabled, false);
  assert.equal(getUserMediaCalls, 0);
  ```

  Separate tests cover SDP answer/ICE forwarding, explicit disconnect/endSession, ignored malformed messages,
  capped reconnect scheduling, and no reconnect after deliberate disconnect.

- [ ] **Step 2: Verify the Node tests fail because the module is absent**

  Run: `node --test tests/js/test_local_webrtc.mjs`

  Expected: FAIL with module/file not found.

- [ ] **Step 3: Implement the minimal signalling state machine**

  Use `ws://${hostname}:8443`. On welcome send listener status and list; choose a producer whose metadata name
  is `reachymini`; start one session; answer SDP offers; exchange ICE; bind video only; disable audio; close data
  channels; send `endSession` on teardown. Do not create an `AudioContext`, media sender, STUN server, or command
  channel.

- [ ] **Step 4: Verify Node protocol tests pass**

  Run: `node --test tests/js/test_local_webrtc.mjs`

  Expected: PASS with zero failures and zero unhandled rejections.

- [ ] **Step 5: Refactor repeated cleanup without changing behaviour**

  Keep retry timer, WebSocket, peer, remote stream, and session ID lifecycle in focused private methods. Re-run
  the Node test after the refactor.

### Task 3: Responsive Media Page

**Files:**
- Create: `src/reachy_mini_conversation_app/local_control/static/media.html`
- Modify: `src/reachy_mini_conversation_app/local_control/static/index.html`
- Modify: `src/reachy_mini_conversation_app/local_control/static/app.js`
- Modify: `src/reachy_mini_conversation_app/local_control/static/style.css`
- Modify: `src/reachy_mini_conversation_app/local_control/app.py`
- Modify: `tests/test_local_control_static.py`

**Interfaces:**
- Consumes: `window.ReachyLocalVideo` from Task 2.
- Consumes: `/api/media/volume` and `/api/media/microphone` from Task 1.
- Produces: `/media` page and dashboard feature-card link.

- [ ] **Step 1: Write failing static-contract tests**

  Assert `/media` is served, every page remains self-contained, dashboard links to `/media`, media markup contains
  `muted`, `playsinline`, connection/disconnect/fullscreen controls, two labelled range inputs (`min=0`, `max=100`,
  `step=1`), numeric outputs, mute/restore buttons, and the privacy sentence. Assert script source has no
  `getUserMedia`, `AudioContext`, `https://`, or cloud hostname.

- [ ] **Step 2: Verify static and route tests fail**

  Run: `uv run pytest tests/test_local_control_static.py tests/test_local_control_api.py -k 'media or self_contained' -q`

  Expected: FAIL because `media.html` and `/media` do not exist.

- [ ] **Step 3: Add the media page and dashboard card**

  Match the existing MakerSeed logo, warm background, raised controls, safe-area footer, and Chinese copy. Keep
  the first viewport focused on video and volume rather than adding unrelated settings.

- [ ] **Step 4: Bind controls in `app.js`**

  Read both volume values after PIN authentication; submit on `change`; set `aria-valuetext` and visible numeric
  output; mute stores the last non-zero value in a module variable only; restore uses that value or 50. Start the
  video only after the user taps “连接画面”; stop it on page hide.

- [ ] **Step 5: Add responsive media CSS**

  Use a 16:9 black viewport, contained video, high-contrast state overlay, touch targets >=48px, a two-column
  volume grid above 620px and one column below it, and no horizontal overflow at 390px.

- [ ] **Step 6: Verify focused frontend contracts and syntax**

  Run: `uv run pytest tests/test_local_control_static.py tests/test_local_control_api.py -k 'media or self_contained' -q`

  Run: `node --check src/reachy_mini_conversation_app/local_control/static/app.js`

  Run: `node --check src/reachy_mini_conversation_app/local_control/static/local-webrtc.js`

  Expected: all commands PASS.

### Task 4: Release Metadata, Documentation, and Full Host Verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `docs/release-notes-v1.0.1-qwen.5.md`
- Modify: `tests/test_community_release.py`

**Interfaces:**
- Produces: buildable `1.0.1+qwen.5` wheel with packaged local media assets and documented rollback.

- [ ] **Step 1: Write a failing release metadata test**

  Assert project version `1.0.1+qwen.5`, release notes exist, and built package-data includes `media.html` plus
  `local-webrtc.js` without any credential-like files.

- [ ] **Step 2: Verify release test fails on qwen.4**

  Run: `uv run pytest tests/test_community_release.py -q`

  Expected: FAIL on the old version/release note.

- [ ] **Step 3: Update metadata and operator documentation**

  Document same-LAN requirements, PIN login, silent video, speaker test-sound behaviour, microphone input control,
  iPhone/Android steps, HF-free operation, port 7861/8443, limitations, diagnostics, and qwen.4 rollback.

- [ ] **Step 4: Run the complete host verification matrix**

  Run: `uv run pytest -q`

  Run: `uv run ruff format --check .`

  Run: `uv run ruff check .`

  Run: `uv run mypy`

  Run: `node --test tests/js/test_local_webrtc.mjs`

  Run: `node --check src/reachy_mini_conversation_app/local_control/static/app.js`

  Run: `node --check src/reachy_mini_conversation_app/local_control/static/local-webrtc.js`

  Run: `uv lock --check`

  Run: `uv build`

  Expected: zero failures/errors, and wheel creation succeeds.

- [ ] **Step 5: Inspect the wheel and scan tracked files**

  List wheel entries and confirm all media assets are present. Scan tracked files and the wheel for DashScope,
  Exa, HF, PIN, private-key, CSV, `.env`, and local IP secrets; false positives from documented variable names
  must be reviewed rather than silently ignored.

### Task 5: Rendered and True-Device Acceptance, Git Release

**Files:**
- Update acceptance evidence under: `F:/Git/ReachyMini/.omx/ultragoal/evidence/local_mobile_control/`
- No browser screenshots or temporary scripts are committed.

**Interfaces:**
- Consumes: qwen.5 wheel from Task 4.
- Produces: verified robot deployment and Git commit/push; tag only after physical phone acceptance.

- [ ] **Step 1: Run rendered browser QA before deployment**

  Flow: `/` -> PIN login -> “音视频控制” -> connect -> volume changes -> disconnect. Verify page identity,
  non-blank DOM, no framework overlay, console health, interaction state, and screenshots at desktop plus 390x844.

- [ ] **Step 2: Back up and deploy qwen.5 to `192.168.50.78`**

  Record current wheel hash, service files, app status, motor mode, and Qwen status. Copy the new wheel, verify its
  SHA-256 on both hosts, install it, restart the local-control service, and restart the managed Qwen app without
  upgrading Daemon.

- [ ] **Step 3: Run read-only and controlled device checks**

  Verify Daemon `1.9.0`, app version `1.0.1+qwen.5`, gateway health, Qwen backend connected, motor enabled, local
  8443 reachable, camera specs available, and both volume reads. Exercise one safe volume change and restore the
  original value; verify one safe head motion and Qwen status afterwards.

- [ ] **Step 4: Perform physical phone acceptance**

  On iPhone Safari and Android Chrome where available: open `http://reachy-mini.local:7861`, log in, connect silent
  video, enter/exit fullscreen, change and restore both volumes, navigate away/back, confirm reconnect, speak to
  Qwen, and execute one safe motion. Confirm no robot audio is played by the phone.

- [ ] **Step 5: Inspect fresh logs and rollback if any release gate fails**

  Reject the release on Traceback, `Process exited`, WebSocket 1007, Daemon error, persistent ICE failure, Qwen
  disconnect, motor mode regression, audible phone playback, or volume not restoring. Reinstall the backed-up
  qwen.4 wheel and re-run its baseline if rejected.

- [ ] **Step 6: Commit and push with Lore trailers**

  Use reviewable commits whose intent lines explain why the boundary exists. Every final feature commit records
  Daemon 1.9, HF-free, no-phone-audio constraints, tested commands, physical-device evidence, and any untested
  browser. Push `feat/local-mobile-control`. Create/push `v1.0.1-qwen.5` only when the true-device gates pass.
