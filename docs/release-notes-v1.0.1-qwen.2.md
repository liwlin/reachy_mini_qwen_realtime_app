# Reachy Mini Qwen Realtime v1.0.1-qwen.2

Compatibility patch for upgrading a Reachy Mini Wireless installation from the
v0.5 Qwen community build to the v1 application architecture. This release does
not change the Reachy Mini Daemon requirement: stable Daemon and Apps SDK 1.9.0
remain the supported target.

## Fixed

- Bound Qwen WebSocket close handshakes to two seconds so personality reloads
  return before the UI's RPC timeout and can persist the startup choice.
- Migrate a voice-only v0.5 startup settings file together with its inherited
  `REACHY_MINI_CUSTOM_PROFILE` selector.
- Map the retired v0.5 `do_nothing` tool ID to v1's `idle_do_nothing` tool.
- Retry bounded transient `None` frames from the Wireless one-shot camera path.
- Fit oversized 1280x720 Wireless JPEGs to 854x480 through the existing
  GStreamer runtime before sending them to Qwen. The post-fit Base64 limit is
  still enforced.
- Lazily export the branded Wireless app class so Daemon `python -m` execution
  does not preload and execute the runner module ambiguously.

## Preserved

- Qwen Omni Realtime voice and Tina profile voice.
- Camera, motion, dance, emotion, memory, profile tools, and Exa MCP search.
- Direct Qwen and Exa proxy isolation.
- Serialized camera/manual-VAD commits and the 240-second Qwen idle keepalive.
- Private credentials and external profile content remain robot-local.

## Upgrade and rollback

Back up the existing application environment, external profiles, startup
settings, and rollback wheel before installation. Never overwrite the
`v1.0.1-qwen.1` release artifact or tag. The retained v0.5 wheel remains the
rollback target when any mandatory real-device gate fails.

## Verification

- Ruff format/lint, Mypy and 362 tests passed.
- Wheel privacy and installed-entry-point smoke passed.
- Release candidate Wheel SHA-256:
  `9B0389E71DC89A6ADAEE4C005785DF01CFA87D1405298AC568F24D1C80ADF65A`.
- Reachy Mini Wireless voice, camera, Exa MCP, motion, personality persistence,
  app stop/start and Daemon restart gates passed with Daemon/Apps SDK 1.9.0.
- A 2100.2-second final soak produced 19 healthy samples and zero WebSocket
  1007, response-stream timeout, process exit, traceback, Qwen/VAD/commit or
  Daemon error.

The test robot has a separate pre-existing motor serial/power warning: several
reads recovered after one retry while the application and Qwen stayed healthy.
Inspect the motor power and internal serial connectors independently of this
application release.
