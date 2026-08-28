# Reachy Mini Qwen Realtime v1.0.1-qwen.5

This community release extends the qwen.4 HF-free local mobile controller with silent live camera viewing and
PIN-protected speaker/microphone volume controls. Reachy Mini Wireless remains on stable Daemon 1.9.0.

## Added

- A MakerSeed-branded `/media` page for iPhone Safari, Android Chrome, and desktop browsers on the same LAN.
- Direct connection to the existing GStreamer `reachymini` producer through local WebRTC signalling on port 8443.
- Receive-only video: no phone camera/microphone permission, no phone audio playback, no cloud signalling, no STUN,
  and no robot command data-channel traffic.
- Daemon 1.9's bundled audio m-line remains `recvonly` so GStreamer keeps the WebRTC session alive; the received
  audio track is disabled and never attached to a phone media element.
- Explicit connect, disconnect, fullscreen, connection-state, and capped automatic-reconnect controls.
- Speaker output and microphone input sliders from 0 to 100 with mute/restore and current-value display.
- Four fixed, authenticated gateway operations that validate values and proxy only Daemon 1.9 volume endpoints.
- Node protocol tests for GStreamer signalling, SDP/ICE, audio rejection, session cleanup, and reconnect behaviour.

## Preserved

- Qwen Omni Realtime Tina voice, camera analysis, personalities, tools, motion suspension, and conversation flow.
- Exa MCP search, cached expressions/dances, installed-app switching, network provisioning, and emergency stop.
- Device-PIN session cookies, strict Wi-Fi credential handling, MakerSeed branding, and systemd auto-start.
- Daemon 1.9.0 and its automatic shared-venv SDK synchronization.

## Operator Notes

- Open `http://reachy-mini.local:7861/media` after joining the same LAN and signing in with the robot PIN.
- Tap **连接画面** once; muted inline playback makes the gesture valid on iPhone Safari.
- The speaker slider submits only after release because Daemon 1.9 plays one short test sound after a successful
  output-volume change. The microphone slider changes robot input volume and is not an audio monitor.
- Video and both volume controls are independent: volume control remains usable if local WebRTC port 8443 is blocked.
- The page intentionally does not expose advanced XVF3800 hardware gain parameters.

## Network and Security Boundary

- Port 7861 serves the PIN-protected controller; volume API calls are same-origin and HttpOnly-cookie authenticated.
- Port 8443 is the existing Daemon LAN GStreamer signalling service. qwen.5 does not modify its bind address,
  firewall rules, or Daemon source.
- No API key, workspace ID, PIN, Wi-Fi password, SDP, ICE candidate, audio, or camera frame is persisted by the page.

## Rollback

Keep the exact qwen.4 wheel and SHA-256 before installing. If any device gate fails, reinstall it into
`/venvs/apps_venv` with `--no-deps --force-reinstall`, restore the packaged local-control service file, restart
`reachy-mini-local-control.service`, restart the managed Qwen app, and verify Daemon 1.9.0 plus motor mode.

The `v1.0.1-qwen.5` Git tag and release artifact are created only after host checks and true-device media, Qwen,
volume, motion, and log gates pass.
