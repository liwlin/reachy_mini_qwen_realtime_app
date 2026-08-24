# Reachy Mini Qwen v1 Upgrade Closure Design

## Objective

Upgrade the Reachy Mini Wireless robot from the currently retained
`reachy-mini-qwen-realtime-app==0.5.0+qwen.1` deployment to the immutable public
`v1.0.1-qwen.1` release, diagnose every reproduced regression, and finish with a
repeatable release artifact plus real-device acceptance evidence.

The Reachy Mini Daemon remains on stable `1.9.0`. The upgrade must not modify the
system version, reintroduce the removed loopback proxy, disclose credentials, or
replace the user's private personality content.

## Current Baseline

- Target: Reachy Mini Wireless on the task's existing LAN connection.
- Daemon: `1.9.0`, running without daemon or backend errors.
- Application: stopped at the design checkpoint.
- Motor mode: `enabled` at the design checkpoint.
- Stable rollback application: `0.5.0+qwen.1`.
- Candidate application: public `v1.0.1-qwen.1` wheel with SHA-256
  `3F4037AE2F6F478140EE2EDDB2105E83A3D2EE14770754D52E958928E7C4D535`.
- Private runtime state that must survive: Qwen credentials and endpoint, Exa
  configuration, the `seed_fungus` personality, its voice and tool selection,
  app metadata, and startup selection.

## Delivery Strategy

### Stage 1: Reversible deployment

Before changing the Apps environment, collect a timestamped robot backup that
contains the installed application version, dependency freeze, private runtime
environment, external profiles, instance/startup settings, app metadata, and the
rollback wheel. Keep credential-bearing files only on the robot with restrictive
permissions. Record hashes and redacted manifests on the host.

Stop any running application, temporarily disable motors only during deployment
if motion safety requires it, install the exact public candidate wheel, restore
the private runtime state through the candidate's supported migration path, and
start the application through the Daemon API.

### Stage 2: Reproduce before repairing

Test the published candidate unchanged. Capture the exact state, response, and
logs for each previously observed failure:

1. app start returning HTTP 400 or a stale `stopping` state;
2. no secondary UI after the Daemon uses `python -m`;
3. `personalities.apply` timeout or failure to persist `seed_fungus`;
4. unexpected voice selection or unsupported Qwen voice;
5. visual answers produced without a fresh camera call;
6. camera manual-VAD commit errors;
7. motion tools accepted while motors are disabled or motion does not occur;
8. internal Python modules exposed as user-selectable tools;
9. Exa MCP failures caused by inherited proxy configuration;
10. idle Qwen WebSocket 1007 response-stream timeouts.

No candidate code is changed until evidence identifies a reproducible root
cause. Environmental or stale-state failures are repaired at their owning layer
instead of being hidden with application changes.

### Stage 3: Patch only when required

If the immutable `v1.0.1-qwen.1` candidate passes, it remains the installed
version. If a production-code defect is reproduced, add a regression test and
observe the expected failure before implementing the smallest fix. Build and
publish a new `v1.0.1-qwen.2` artifact; never retag or replace
`v1.0.1-qwen.1`.

Robot-only hot patches are prohibited because they make the deployed code differ
from the reviewed GitHub artifact. New dependencies are prohibited unless the
reproduced defect cannot be corrected with the existing stack and the user
explicitly approves the dependency.

## Configuration and Privacy

- Never print or copy API keys, tokens, full private environment files, or
  private identity content into host evidence, commits, logs, issues, or release
  notes.
- Preserve the existing Qwen region, workspace or full official WebSocket URL,
  and `DASHSCOPE_API_KEY` without re-entry.
- Preserve the active and startup `seed_fungus` personality.
- Preserve `Tina` unless live capability discovery proves it unsupported.
- Preserve the intended user-facing tools: camera, web search, head movement,
  emotion play/stop, dance/stop, and idle behavior. System task-management tools
  may remain implicit. Internal implementation modules must not appear as
  selectable capabilities.
- Exa must continue to bypass inherited proxy variables and send only bounded
  text query fields.

## Error Handling and Rollback

The deployment is successful only when the application is `running`, the app
error is empty, the secondary UI returns HTTP 200, Qwen is ready, and the private
profile resolves. If installation, configuration migration, launch, or a
mandatory acceptance gate cannot be repaired within the controlled upgrade
window, stop the candidate and restore the timestamped `0.5.0+qwen.1` backup.

After rollback, verify Daemon `1.9.0`, application running/error state, UI 200,
Qwen readiness, profile and voice persistence, tool registry, and the original
motor mode. A failed candidate must not leave the Daemon in `stopping`, retain a
partial environment, or leave motors in a different mode.

## Acceptance Gates

### Host and artifact

- Release wheel hash matches the public release.
- Dependency lock/check, formatting, lint, type checking, full tests, wheel
  metadata, module execution, privacy scan, and installed-entry-point smoke pass.
- Any new bug fix demonstrates a recorded RED then GREEN regression test.

### Real device

- Daemon remains `1.9.0` with empty daemon/backend errors.
- App stop/start and Daemon restart both return the candidate to `running` with
  empty error and UI HTTP 200.
- `seed_fungus` remains current and startup; applying/reloading it completes
  without timeout.
- Qwen uses `Tina`; a spoken Chinese prompt produces correct ASR, assistant text,
  and audible playback.
- Every visual question causes a fresh `camera` tool call, submits a real frame,
  and produces a grounded description without commit/VAD errors.
- `move_head` produces a measured small pose delta and returns to neutral;
  emotion and stop actions execute. Motion is performed only during an announced
  safety window.
- Exa returns bounded results with at least one reachable source while camera and
  motion tools remain registered in the same Qwen session.
- The tool UI exposes only callable user capabilities.
- A minimum 35-minute idle soak crosses the 300-second Qwen timeout boundary and
  contains no WebSocket 1007, process exit, traceback, Qwen/backend error,
  commit/VAD error, or Daemon error.

## Final State

Restore the motor mode observed before deployment (`enabled`) after all movement
tests. Remove only temporary non-backup artifacts from the robot. Retain the
timestamped rollback backup and a redacted acceptance report. The handoff must
state the installed application version, artifact hash, Daemon version, test
results, backup path, and every remaining limitation.
