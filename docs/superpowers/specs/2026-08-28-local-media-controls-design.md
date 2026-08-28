# Local Media Controls Design

## Outcome

Extend the existing PIN-protected LAN controller with an HF-free media page that:

- renders the Reachy Mini camera as a low-latency, silent WebRTC video;
- reads and updates speaker output volume from 0 to 100;
- reads and updates microphone input volume from 0 to 100;
- never requests access to the phone camera or microphone;
- remains usable while Qwen or another installed local application is running;
- works from iPhone Safari and Android Chrome on the same LAN.

The release version is `1.0.1+qwen.5` and the user-facing tag is `v1.0.1-qwen.5`.

## Selected Architecture

The browser connects directly to the Daemon's existing GStreamer `webrtcsink` signalling server at
`ws://<current-host>:8443`. It registers as a listener, lists the `reachymini` producer, starts one
session, answers the producer's SDP offer, and exchanges ICE candidates. Daemon 1.9 requires the bundled
audio m-line to remain `recvonly`; the browser therefore negotiates it but immediately disables and discards
every remote audio track. It never calls `getUserMedia` and closes every data channel without sending robot
commands.

Volume operations remain same-origin and PIN-protected. The local gateway exposes a narrow API and
forwards only the four fixed Daemon 1.9 operations:

- `GET /api/volume/current`
- `POST /api/volume/set`
- `GET /api/volume/microphone/current`
- `POST /api/volume/microphone/set`

The gateway validates values as integers in the inclusive range `0..100` and returns only `volume`,
`platform`, and `device`. It does not expose a general Daemon proxy.

## User Experience

The dashboard adds a fourth feature card labelled “音视频控制”. `/media` contains:

- a 16:9 `<video muted playsinline autoplay>` viewport;
- explicit “连接画面/断开画面” and “全屏” controls;
- connection states for connecting, live, reconnecting, unavailable, and stopped;
- separate speaker and microphone range inputs with numeric values;
- mute/restore controls that remember the last non-zero value for the current page session;
- a clear note that the phone does not play the robot microphone and requests no phone media permission.

Speaker changes are sent only on `change` (finger release), because Daemon 1.9 plays a short test sound
after setting output volume. Microphone changes also use `change` for consistent mobile behaviour.

## Connection and Recovery

The WebRTC client derives the signalling hostname from `window.location.hostname`, uses port `8443`,
and never hard-codes a deployment IP. A user gesture starts the first connection for Safari compatibility.
Unexpected WebSocket or ICE failure retries with capped exponential backoff while the page is visible and
authenticated. Deliberate disconnect, page hide, logout, and navigation cancel the retry timer, end the
GStreamer session, stop received tracks, and close the peer connection.

The client treats an audio track as a protocol violation for playback purposes: it disables the track and
does not attach it to a media element. The WebRTC flow does not gate page login; volume controls still work
when video signalling is unavailable.

## Security and Privacy

- All `/api/media/*` requests require the existing HttpOnly PIN session cookie.
- No API key, Wi-Fi password, PIN, SDP, or ICE candidate is persisted or logged by the page.
- The page is self-contained and loads no CDN assets, STUN service, analytics, or cloud signalling.
- The browser sends no audio/video upstream and no robot-control data-channel messages.
- Existing Daemon port `8443` remains a LAN service; this feature does not change firewall or Daemon binding.
- Errors shown to the phone use stable local error codes instead of raw upstream response bodies.

## Compatibility

- iPhone Safari: user-initiated connection, `playsinline`, muted autoplay, H.264 WebRTC answer.
- Android Chrome: the same standards-only WebSocket/WebRTC path.
- Desktop Chromium is used for automated rendering verification; physical iPhone Safari remains a required
  device acceptance gate.
- Daemon 1.9.0 is retained; no firmware upgrade is part of this release.

## Acceptance Criteria

1. An unauthenticated browser receives `401` for every volume route and cannot open the media controls.
2. Authenticated reads return the current speaker and microphone volumes.
3. Values below 0, above 100, non-integers, and malformed JSON never reach Daemon.
4. Speaker and microphone writes call only their fixed Daemon routes and return the applied value.
5. The WebRTC client speaks the GStreamer listener/list/startSession/peer/endSession protocol.
6. The page never calls `navigator.mediaDevices.getUserMedia` and never attaches an audio track.
7. Video disconnect/reconnect leaves Qwen and motor state unchanged.
8. The page is usable at 390x844 and 412x915 without clipped controls or horizontal scrolling.
9. The complete Python test suite, Ruff, strict Mypy, Node syntax checks, package build, secret scan, and wheel
   content inspection pass.
10. On `192.168.50.78`, qwen.5 starts, Qwen remains connected, live video renders silently, both volume
    controls apply, a safe motion still executes, and logs contain no new Traceback, process exit, WebSocket
    1007, or Daemon error.

## Rollback

Keep the current qwen.4 wheel and service files before deployment. Rollback reinstalls that exact wheel,
restarts only `reachy-mini-local-control.service` and the managed Qwen app, then verifies Daemon 1.9.0,
motor mode, Qwen backend state, and the original dashboard.
