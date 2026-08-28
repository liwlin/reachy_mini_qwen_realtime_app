# Reachy Mini Qwen Realtime qwen.4 Local-Control Catalogs Design

## Status

Approved in conversation on 2026-08-28. This specification extends the existing
HF-independent LAN controller while keeping Reachy Mini Wireless on Daemon and
Apps SDK 1.9.0.

## Context

The deployed `1.0.1+qwen.3` controller already provides PIN-authenticated LAN
control, Qwen lifecycle operations, ten safe actions, sleep/wake motor ownership,
emergency action stopping, and Wi-Fi provisioning. Physical iPhone Chrome tests
have passed for the dashboard, motion, and provisioning flows.

Fresh runtime discovery on the target robot found:

- four installed apps: Marionette, Red Light Green Light, Coding Lab, and Reachy
  Mini Qwen Realtime;
- 81 moves in the official emotions dataset;
- 19 moves in the robot's currently cached Pollen recorded-dances dataset;
- 20 symbolic moves in the installed Python dances package;
- 14 optional music dances in the official desktop app's additional
  `Anne-Charlotte/music` source;
- two saved Wi-Fi networks, one of them active.

Counts must remain dynamic. The UI must not claim 34 dances when a particular
robot currently exposes fewer. A refreshed Pollen dataset with 20 moves plus the
14 music moves naturally produces 34 without a code change.

## Goals

1. Manage every currently installed Reachy Mini app from the LAN controller.
2. Expose every available emotion and recorded dance through a searchable mobile
   catalog without allowing arbitrary dataset playback.
3. Switch to any already-saved Wi-Fi network without asking for its password
   again.
4. Preserve Qwen voice connectivity while Daemon owns scripted movement.
5. Prevent move stacking and provide a true motor-disabling emergency stop.
6. Keep the UI self-contained, responsive, PIN protected, and usable without
   Hugging Face OAuth or signaling.
7. Release the feature as `1.0.1+qwen.4`, retaining the validated qwen.3 wheel as
   the rollback artifact.

## Non-goals

- Installing, updating, or removing apps from the mobile page.
- Exposing arbitrary Daemon routes, Hugging Face repository names, or shell
  commands.
- Bundling third-party motion/audio datasets inside the GitHub repository or
  application wheel.
- Automatically waking the robot when a motion is selected.
- Automatically forgetting Wi-Fi networks.
- Changing Daemon 1.9.0, the Qwen model, voice, personality, camera, Exa, or MCP
  configuration.

## Architecture

The always-on local gateway remains the only browser-facing authority. It calls
a narrow `DaemonClient` for platform operations and `QwenRpcClient` only for
Qwen-owned motion arbitration. The browser never receives a general proxy.

Two secondary pages are added and the existing setup page is expanded:

- `/apps` for installed-app lifecycle management;
- `/motions` for emotions and dances;
- `/setup` for saved-network switching, scanning, and new-network provisioning.

All pages reuse the existing PIN session, local Makerseed assets, status polling,
48-pixel touch targets, and fixed safe-area layout. The dashboard keeps common
controls and links to the secondary pages.

## Installed-App Management

### Catalog

`GET /api/apps` calls Daemon's installed-app catalog and returns only:

- stable app name;
- display title and emoji when present;
- active/running/error state;
- a sanitized local custom-UI URL when one exists.

The gateway discards remote URLs and internal filesystem/venv metadata. Every
subsequent app name must match a fresh installed-app catalog entry.

### Automatic switching

`POST /api/apps/{name}/switch` is serialized by an application lock:

1. Re-read installed apps and reject unknown names.
2. Read the current app. If it is already the target and healthy, return an
   idempotent success.
3. If another app is running, stop it and poll until its slot is released.
4. Start the target and poll until it is running or has a concrete error.
5. If target startup fails after the previous app stopped, attempt once to
   restore the previous app and return whether rollback succeeded.

The browser must show a confirmation dialog before switching away from an active
app. The server revalidates state after confirmation so stale browser state
cannot bypass the sequence.

`POST /api/apps/{name}/stop` succeeds only when `{name}` is the current app.
Stopping Qwen does not stop the separate always-on local gateway.

## Motion Catalog and Playback

### Fixed sources

The browser uses opaque source IDs. The server owns the mapping:

| Source ID | Fixed dataset | Purpose |
| --- | --- | --- |
| `emotion` | `pollen-robotics/reachy-mini-emotions-library` | Official emotions |
| `pollen_dance` | `pollen-robotics/reachy-mini-dances-library` | Official recorded dances |
| `music_dance` | `Anne-Charlotte/music` | Optional community music dances |

The Python symbolic dances package is not merged into the recorded-dance list:
it has different execution semantics and would create confusing duplicates.
Qwen may continue using that package internally for conversational dance tool
calls.

### Catalog response

`GET /api/motions/catalog` returns source status plus live move names. Default
Pollen datasets are read through Daemon because the Wireless image preloads them.
Music-dance metadata follows the official desktop-app catalog, but the source is
reported unavailable unless the dataset is locally cached and playable.

Move labels are derived from stable IDs for display only. Playback always uses
the exact server-returned ID. The page provides Emotions and Dances tabs, search,
source grouping, live counts, and availability messages. It renders the actual
catalog rather than hardcoding 81 or 34.

### Playback ownership

`POST /api/motions/{source}/{name}/play` is serialized by a motion lock:

1. Validate the source ID and refresh its catalog.
2. Reject any move not present in that catalog.
3. Require motors to be enabled; never wake implicitly.
4. If Qwen is the active app, require `robot.motion.suspend` to acknowledge that
   its 100 Hz output has stopped.
5. Start the fixed Daemon recorded-move route and track its UUID.
6. Wait for completion, cancellation, or a bounded timeout.
7. Resume Qwen motion from neutral only after Daemon releases ownership.

Only one phone-triggered move may run at a time. While one runs, the page disables
other play buttons and shows the active move. This prevents unsafe stacking.

`POST /api/motions/stop` clears Qwen's motion queue and stops every currently
running Daemon move, but leaves motor mode unchanged.

## Emergency Stop

`POST /api/robot/emergency-stop` is deliberately stronger than ordinary motion
stop:

1. Clear Qwen actions when reachable.
2. Query and stop every running Daemon move UUID, including moves that started
   before a gateway restart.
3. Set motor mode to `disabled` even if earlier cleanup partially failed.
4. Return a sanitized summary of completed steps.

The fixed red footer uses this route on the dashboard and motion page. Re-enabling
motors remains a separate explicit user action.

## Saved Wi-Fi Switching

`GET /api/wifi/status` already exposes `known_networks` and the active network.
The setup page adds a Saved Networks section above scanning:

- active SSID: green Connected badge, no switch button;
- saved inactive SSID: Switch button;
- nearby saved SSIDs: marked Saved in scan results rather than duplicated.

`POST /api/wifi/switch` accepts only an SSID currently present in
`known_networks`. It reuses the existing sealed loopback provisioning call with
an empty password; NetworkManager activates the saved connection and retains the
stored secret. The response is `202 Accepted` because the successful operation
usually disconnects the current phone session before a final HTTP result can be
observed.

The browser confirms that control will disconnect, sends the request, then shows
instructions to join the same target network and reopen
`reachy-mini.local:7861`. New-network passwords remain ephemeral and are cleared
from the form immediately after submission.

## Offline and Regional-Network Behavior

The core application catalog, Pollen emotions, Pollen dances, and saved-network
switching must work from robot-local state. A missing optional music dataset must
not trigger an unbounded Hugging Face request from a dashboard refresh.

For the project robot, deployment may separately pre-cache the official
`Anne-Charlotte/music` dataset. That cache is device state, not a Git artifact.
Community installations without it display Music dances not installed and keep
all other controls operational.

## Error Handling and Concurrency

- App switches and motion playback use independent async locks.
- Unknown app, source, move, or saved SSID values fail before a Daemon request.
- A running Qwen app whose motion RPC cannot acknowledge suspension blocks
  playback rather than risking competing motor output.
- A Daemon motion timeout leaves Qwen output suspended until explicit recovery.
- App-switch rollback reports both target failure and rollback outcome.
- Network switching treats loss of the old connection as expected, not proof of
  failure.
- Browser messages use stable reason codes and never display upstream secrets,
  filesystem paths, command lines, or credentials.

## Testing

### Automated host gates

- TDD coverage for catalog sanitization and path/name validation.
- App switch ordering, idempotency, failure rollback, and lock behavior.
- Dynamic catalog counts, unavailable music source, and move allowlisting.
- Qwen suspend/Daemon playback/wait/Qwen resume ordering.
- Move stacking rejection, ordinary stop, and motor-disabling emergency stop.
- Saved-network switching restricted to `known_networks`.
- Static mobile-page contracts, search/filter rendering, confirmation dialogs,
  safe-area footer, and password/PIN non-persistence.
- Full pytest suite, Ruff format/lint, strict Mypy, `uv lock --check`, wheel
  inspection, install smoke, and privacy scans.

### Reachy Mini Wireless gates

- Daemon and Apps SDK remain 1.9.0; local gateway remains enabled on port 7861.
- Qwen to Coding Lab to Qwen automatic app switching.
- One official emotion, one Pollen dance, and one cached music dance.
- Qwen remains connected through recorded moves and regains motor ownership.
- Ordinary stop leaves motors enabled.
- Emergency stop during a dance stops all moves and disables motors; explicit
  wake restores motion.
- User-confirmed saved-network switch from the physical phone.
- Regression checks for Qwen voice, camera grounding, safe action, and Exa.
- Final app state `running`, error empty, motors enabled, and no WebSocket 1007,
  process exit, traceback, or Daemon error in the acceptance window.

## Versioning, Rollback, and Publication

- New version: `1.0.1+qwen.4`; community label: `v1.0.1-qwen.4`.
- qwen.3 commit, wheel, hash, and device backup remain immutable rollback inputs.
- The qwen.4 wheel receives a new SHA-256 and device-side installation record.
- No API key, device PIN, Wi-Fi password, personality-private state, user path,
  or local evidence image is committed to the public release.
- The feature branch is pushed only after host and hardware gates pass. A tag or
  GitHub Release remains gated on the agreed physical-browser/network evidence.
