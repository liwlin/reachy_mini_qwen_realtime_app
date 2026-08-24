---
title: Reachy Mini Qwen Realtime
emoji: 🎤
colorFrom: red
colorTo: blue
sdk: static
pinned: false
short_description: Qwen voice, vision, robot tools, and Exa MCP search for Reachy Mini
suggested_storage: large
tags:
 - reachy_mini
 - reachy_mini_python_app
---

# Reachy Mini Qwen Realtime

[![Release](https://img.shields.io/github/v/release/liwlin/reachy_mini_qwen_realtime_app?include_prereleases&label=community%20release)](https://github.com/liwlin/reachy_mini_qwen_realtime_app/releases)
[![Upstream proposal](https://img.shields.io/badge/upstream-issue%20%23539-blue)](https://github.com/pollen-robotics/reachy_mini_conversation_app/issues/539)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

Community build of Pollen Robotics' Reachy Mini Conversation App, adding direct Qwen Omni Realtime voice and camera vision, robot Function Tools, and optional Exa MCP search while retaining the upstream Hugging Face path.

> Based exactly on [`pollen-robotics/reachy_mini_conversation_app`](https://github.com/pollen-robotics/reachy_mini_conversation_app) v1.0.1. This is a community release, not an official Pollen Robotics build.

![Reachy Mini Dance](docs/assets/reachy_mini_dance.gif)

## Table of contents

- [Overview](#overview)
- [Community release](#community-release)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [LLM tools](#llm-tools-exposed-to-the-assistant)
- [Creating and adding tools](#creating-and-adding-tools)
- [Advanced features](#advanced-features)
- [Regional connectivity and rollback](#regional-connectivity-and-rollback)
- [Upstream coordination](#upstream-coordination)
- [Contributing](#contributing)
- [License](#license)

## Overview

- Low-latency audio conversation through either the Hugging Face realtime backend or direct DashScope/Qwen Omni Realtime.
- Vision is handled by the selected realtime backend when the `camera` tool is used.
- Layered motion system queues primary moves (dances, emotions, goto poses, breathing) while blending speech-reactive wobble.
- Async tools integrate motion, camera capture, Exa Streamable HTTP MCP search, and upstream MCP Tool Spaces. The optional web UI (`--ui`) manages conversations, personalities, tools, and settings.

## Community release

Version `v1.0.1-qwen.2` keeps upstream v1's `ConversationHandler`, profile store, UI, memory, and generic Tool Space architecture, then adds provider-local Qwen wire handling and a direct Exa search Tool. It is a compatibility patch over `v1.0.1-qwen.1` for real Wireless upgrades:

- 16 kHz PCM microphone input and 24 kHz PCM Qwen speech output.
- Camera frames committed through Qwen's image buffer, serialized against microphone frames, with server VAD restored even after image-send failure.
- Camera, motion, dance, emotion, memory, Exa search, and installed remote MCP tools exposed through one Qwen function schema.
- Official Alibaba Cloud endpoint allowlist and explicit proxy bypass for credential-bearing Qwen WebSockets.
- Wireless-visible `reachy_mini_qwen_realtime_app` package and entry point, so Daemon 1.9 can discover the secondary UI without a manual metadata file.
- Stable Wireless Daemon 1.9 compatibility: the Daemon intentionally synchronizes the shared Apps venv back to SDK 1.9 at restart, so this build carries its v1 JSON-RPC UI boundary inside the app and supports `reachy-mini>=1.9.0`. Do not disable the Daemon's SDK synchronization or pin the shared venv to a release candidate.
- Idle Qwen sessions send a serialized minimal `session.update` every 240 seconds. This elicits a server event before the 300-second response-stream timeout; WebSocket ping frames and silent microphone audio alone do not keep that service stream alive.
- Automatic migration of v0.5 `BACKEND_PROVIDER=qwen` and Qwen `MODEL_NAME` settings when `REALTIME_BACKEND` is absent.
- Bounded Qwen close handshakes keep personality reloads inside the UI RPC timeout.
- v0.5 startup personality and the renamed `do_nothing` idle capability survive migration.
- Transient camera warmup misses are retried, and oversized Wireless JPEGs are fitted to Qwen's image limit through the existing GStreamer stack.
- The branded `python -m` runner is imported lazily, eliminating duplicate-execution warnings.
- Qwen's 24 kHz PCM output is resampled to the robot speaker rate, preserving the Tina speed and pitch used by the v0.5 build.

<details>
<summary>中文快速说明</summary>

本社区版以官方 `v1.0.1` 为基线，直接支持 Qwen Omni Realtime 中文语音、真实摄像头视觉、动作/表情/舞蹈和 Exa MCP 网络搜索。升级自 v0.5 时，原有 Qwen Key、workspace、region、model、外部角色和工具配置可以继续使用。

1. 从 [Releases](https://github.com/liwlin/reachy_mini_qwen_realtime_app/releases) 下载 `v1.0.1-qwen.2` wheel。
2. 复制 `.env.example` 为 `.env`，配置 `REALTIME_BACKEND=qwen`、`DASHSCOPE_API_KEY` 以及 workspace ID 或完整官方 WebSocket URL。
3. 启动 `reachy-mini-qwen-realtime-app`；Wireless Control App 会通过 7860 二级页面显示角色、工具和设置。
4. `web_search` 默认使用 Exa MCP，可匿名限量使用；高频使用时配置 `EXA_API_KEY`。

Exa 只接收模型生成的文字查询，不接收麦克风音频、摄像头图片、机器人标识或本地文件。

Wireless 稳定版 Daemon 1.9 在重启时会把共享 Apps 虚拟环境中的 SDK 同步回 1.9.0；这是正常的系统行为。本社区版已在应用内部补齐 v1 二级页面所需的 JSON-RPC 协议，因此无需修改 Daemon、关闭同步或反复安装 1.10 RC SDK。

</details>

## Architecture

The app connects the user, AI services, and robot hardware:

<p align="center">
  <img src="docs/assets/conversation_app_arch.svg" alt="Architecture Diagram" width="600"/>
</p>

## Installation

> [!IMPORTANT]
> Install [Reachy Mini's SDK](https://github.com/pollen-robotics/reachy_mini/) before using this app.<br>
> Windows support is currently experimental and has not been extensively tested. Use with caution.

On Reachy Mini Wireless with stable Daemon 1.9, install the release wheel into `/venvs/apps_venv` and leave the Daemon on 1.9.0. The wheel is tested against the synchronized SDK 1.9.0 environment, including app/Daemon restarts; a manual `.app_metadata` file is not required.

<details open>
<summary>Using uv (recommended)</summary>

Set up with [uv](https://docs.astral.sh/uv/):

```bash
# macOS (Homebrew)
uv venv --python /opt/homebrew/bin/python3.12 .venv

# Linux / Windows (Python in PATH)
uv venv --python python3.12 .venv

source .venv/bin/activate
uv sync
```

Include dev dependencies:
```bash
uv sync --group dev
```

</details>

> [!NOTE]
> Run `uv sync --frozen` to install the exact dependency set from `uv.lock` without re-resolving versions.

<details>
<summary>Using pip</summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Install dev dependencies:
```bash
pip install -e .[dev]                   # Development tools
```

</details>

## Configuration

### Optional Qwen Realtime backend

Hugging Face remains the default backend. To opt into Alibaba Cloud Qwen Omni Realtime, configure:

```env
REALTIME_BACKEND=qwen
DASHSCOPE_API_KEY=your-key
QWEN_WORKSPACE_ID=your-workspace-id
QWEN_REGION=cn-beijing
QWEN_MODEL_NAME=qwen3.5-omni-flash-realtime
```

Use `QWEN_REALTIME_URL` instead of `QWEN_WORKSPACE_ID` when the Alibaba Cloud console provides a complete endpoint. Only official `wss://*.maas.aliyuncs.com/api-ws/v1/realtime` endpoints in the supported Beijing or Singapore regions are accepted.

Existing v0.5 installations using `BACKEND_PROVIDER=qwen` and a Qwen `MODEL_NAME` are migrated automatically when `REALTIME_BACKEND` is not set. New configurations should use the v1 names above.

The Qwen handler reuses the existing local and remote MCP Tool registry, accepts 16 kHz PCM microphone input,
returns 24 kHz PCM audio, and supports image-buffer camera turns. API keys and workspace identifiers must not be
committed. The settings UI remains Hugging Face-oriented in this initial provider port; Qwen is configured through
the app environment.

The default setup uses the Hugging Face backend and does not require an API key.

Copy `.env.example` to `.env` when you want to point Hugging Face at your own local endpoint.

| Variable | Description |
|----------|-------------|
| `REALTIME_BACKEND` | Realtime provider: `huggingface` (default) or `qwen`. |
| `DASHSCOPE_API_KEY` | Required for direct Qwen mode. `QWEN_API_KEY` remains an accepted alias. |
| `QWEN_WORKSPACE_ID` | Alibaba Cloud workspace used to build the official regional WebSocket URL. |
| `QWEN_REALTIME_URL` | Optional complete official Qwen Realtime WebSocket endpoint. |
| `QWEN_REGION` | `cn-beijing` (default) or `ap-southeast-1`; must match the key and workspace. |
| `QWEN_MODEL_NAME` | Qwen Realtime model; defaults to `qwen3.5-omni-flash-realtime`. |
| `REALTIME_TRANSCRIPTION_LANGUAGE` | Optional input transcription language for the realtime backend. Defaults to `en`; set to a backend-supported code such as `zh` for Chinese. |
| `HF_REALTIME_CONNECTION_MODE` | Hugging Face connection selector: `deployed` uses the built-in Hugging Face server; `local` uses `HF_REALTIME_WS_URL`. Defaults to `deployed`. |
| `HF_REALTIME_WS_URL` | Direct websocket endpoint for your own Hugging Face backend. Accepts either a base URL like `ws://127.0.0.1:8765/v1` or the full websocket URL `ws://127.0.0.1:8765/v1/realtime`. Used when `HF_REALTIME_CONNECTION_MODE=local`. |
| `HF_TOKEN` | Optional token for Hugging Face access. Local endpoints receive only this explicitly configured token. |
| `REACHY_MINI_APP_TIMEOUT_MINUTES` | Minutes of inactivity before Reachy goes to sleep and the app stops. Defaults to `1440` (one day); set to `0` to disable. |

### Optional Exa MCP web search

Qwen's built-in `enable_search` cannot be combined with Function Tools. This community build instead exposes a normal `web_search` Tool, so search, camera, motion, emotion, and dance remain available together:

```env
MCP_WEB_SEARCH_URL=https://mcp.exa.ai/mcp
MCP_WEB_SEARCH_TOOL=web_search_exa
MCP_WEB_SEARCH_TIMEOUT_SECONDS=8
# EXA_API_KEY=optional-key
```

The default endpoint supports limited keyless use. The MCP client uses short-lived Streamable HTTP sessions, retries one isolated MCP failure, bounds returned text to 6,000 characters, treats it as untrusted external evidence, and never forwards audio, images, robot identifiers, or local files.

### Hugging Face Connection Modes

Use the built-in Hugging Face server through the app-managed Space proxy. This is the default for a new install; set it explicitly only when you want to switch back from a saved local endpoint:

```env
HF_REALTIME_CONNECTION_MODE=deployed
```

Deployed session allocation falls back to cached `hf auth login` credentials and reports the daemon-provided hardware ID when available. Cached credentials and the hardware ID are not sent to local endpoints.

Run your own realtime voice backend using [speech-to-speech](https://github.com/huggingface/speech-to-speech) on the same machine as the conversation app:

```env
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://127.0.0.1:8765/v1/realtime
```

Run your own Hugging Face backend on your laptop and connect to it from Reachy Mini Wireless over the same Wi-Fi network:

```env
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://<your-laptop-lan-ip>:8765/v1/realtime
```

For that LAN setup, make sure the backend listens on an address reachable from the robot, not only on `127.0.0.1`.

If the backend stays bound to loopback on your laptop, you can forward it into the robot over SSH instead:

```bash
ssh -N -R 8765:127.0.0.1:8765 <robot-user>@<robot-host>
```

Then set this on the robot:

```env
HF_REALTIME_CONNECTION_MODE=local
HF_REALTIME_WS_URL=ws://127.0.0.1:8765/v1/realtime
```

In the web UI's Settings view, the Connection section lets you choose either the built-in server or a local `host:port` target. The UI writes `HF_REALTIME_CONNECTION_MODE` for you, and the local path writes `HF_REALTIME_WS_URL` with a default of `localhost:8765`.

## Running the app

Activate your virtual environment, then launch:

```bash
reachy-mini-qwen-realtime-app
```

> [!TIP]
> Make sure the Reachy Mini daemon is running before launching the app. If you see a `TimeoutError`, it means the daemon isn't started. See [Reachy Mini's SDK](https://github.com/pollen-robotics/reachy_mini/) for setup instructions.

The app runs in console mode. Add `--ui` to serve the web interface at http://127.0.0.1:7860/.

### CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `--no-camera` | `False` | Run without camera capture. |
| `--ui` | `False` | Serve the web UI at http://127.0.0.1:7860/, in addition to console mode. |
| `--robot-name` | `None` | Optional. Connect to a specific robot by name when running multiple daemons on the same subnet. See [Multiple robots on the same subnet](#advanced-features). |
| `--debug` | `False` | Enable verbose logging for troubleshooting. |

### Examples

```bash
# Audio-only conversation (no camera)
reachy-mini-qwen-realtime-app --no-camera

# Launch with the minimal web UI for personality/mic/settings control
reachy-mini-qwen-realtime-app --ui
```

## LLM tools exposed to the assistant

The default profile exposes these tools. Use Tools → Tool access to customize any profile.
Every bundled profile enables `head_tracking` by default; users can still disable it per personality.

| Tool | Action | Dependencies |
|------|--------|--------------|
| `dance` | Queue a dance from `reachy_mini_dances_library`. | Core install only. |
| `stop_dance` | Clear queued dances. | Core install only. |
| `play_emotion` | Play a recorded emotion clip via Hugging Face datasets. | Core install only. Uses the default open emotions dataset: [`pollen-robotics/reachy-mini-emotions-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-emotions-library). |
| `stop_emotion` | Clear queued emotions. | Core install only. |
| `camera` | Capture the latest camera frame and analyze it with the selected realtime backend. | Core install only. Requires the camera (disable with `--no-camera`). |
| `idle_do_nothing` | Explicitly remain idle during an idle turn. Not intended for normal conversation turns. | Core install only. |
| `move_head` | Queue a head pose change (left/right/up/down/front). | Core install only. |
| `head_tracking` | Follow the user's face with the head, or stop following. | Core install only. Requires a daemon with the `vision` extra and a camera. |
| `go_to_sleep` | Run Reachy's sleep movement and stop the current app after an explicit user request. | Core install only. |
| `sweep_look` | Sweep Reachy's head left, right, and back to center. | Shared tool, enabled by default in the default profile. |
| `remember` | Save one short, stable fact about the user for future sessions. | Core install only. Stored in the app instance data directory. |
| `forget` | Remove a saved memory fact by matching a short query. | Core install only. |
| `web_search` | Search the current web through Exa Streamable HTTP MCP and return bounded sourced results. | Limited keyless use or optional `EXA_API_KEY`. |
| `pollen_robotics_reachy_mini_weather_tool__get_weather` | Report today's weather for a place: current conditions, high and low temperature, and rain chance. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-weather-tool`. |
| `pollen_robotics_reachy_mini_time_tool__get_time` | Report the current time for a timezone or the user's local time, or the difference between two timezones. | Preinstalled MCP Space: `pollen-robotics/reachy-mini-time-tool`. |

> [!NOTE]
> `remember`/`forget` facts are stored in `memory.v1.json` inside the app's instance data directory (`~/.local/share/reachy_mini_conversation_app/` by default, or the instance path used by the desktop launcher). `forget` only removes facts matched by query. To reset all remembered facts, delete this file.

## Creating and adding tools

Tools can run locally as Python code or remotely in an MCP-compatible Hugging Face Space. Keep robot, camera, and local-data operations in local tools. A Space is a better fit for shareable, stateless services such as search and external API lookups.

### Local tools

Create one Python module per tool, with the file name matching the tool's unique `name`. See [`idle_do_nothing.py`](src/reachy_mini_conversation_app/tools/idle_do_nothing.py) for a minimal implementation.

Each tool subclasses `Tool` and defines `name`, a model-facing `description`, an object-shaped JSON Schema in `parameters_schema`, and an async `__call__` method. Use `ToolDependencies` for runtime services, and set `needs_response = False` for actions that should not trigger a spoken follow-up. Catch expected operational failures, log them with the module logger, and return `{"error": "..."}` so the conversation can continue.

Restart the app after adding the module. Use Tools → Tool access to enable it for a personality, or add its name to that profile's `default_tools` in `profile.md`. See [External profiles and tools](#external-profiles-and-tools) for external directories and autoload behavior.

### Hugging Face Space tools

To publish a remote tool, create a Gradio Space, expose its API as MCP with `mcp_server=True`, and give each function clear type hints and docstrings. Verify that `https://<space-subdomain>.hf.space/gradio_api/mcp/schema` lists the expected tools before installing the Space.

Use the maintained [weather](https://huggingface.co/spaces/pollen-robotics/reachy-mini-weather-tool), [time](https://huggingface.co/spaces/pollen-robotics/reachy-mini-time-tool), and [search](https://huggingface.co/spaces/pollen-robotics/reachy-mini-search-tool) Spaces as examples. See Gradio's [MCP server guide](https://www.gradio.app/guides/building-mcp-server-with-gradio) for additional publishing guidance and [Installing Hugging Face Space tools](#installing-hugging-face-space-tools) for this app's installation steps.

## Advanced features

Built-in motion content is published as open Hugging Face datasets:

- Emotions: [`pollen-robotics/reachy-mini-emotions-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-emotions-library)
- Dances: [`pollen-robotics/reachy-mini-dances-library`](https://huggingface.co/datasets/pollen-robotics/reachy-mini-dances-library)

<details>
<summary>Custom profiles</summary>

Create custom profiles with dedicated instructions and per-profile tool access.

Select and save a startup profile in the UI. The choice is stored in `startup_settings.json`. Before one is saved, `REACHY_MINI_CUSTOM_PROFILE=<name>` can select `profiles/<name>/`; otherwise the app uses `default`.

Every profile directory contains one strict schema-version-1 `profile.md`. TOML metadata is enclosed by `+++`; the remaining Markdown body is the realtime assistant prompt:

```markdown
+++
schema_version = 1
voice = "Aiden"
greeting = "Greet me warmly in one sentence, in character, and vary the wording each time."
hidden = false
default_tools = [
  "dance",
  "camera",
  "sweep_look",
]
+++

## Identity

You are a concise, friendly robot guide.
```

`schema_version`, `default_tools`, and a non-empty Markdown body are required. `voice`, `greeting`, and `hidden` are optional. Set `hidden = true` to omit a profile from the UI. An empty `default_tools` list is valid and inherits nothing.

`default_tools` is the authored baseline. Tools → Tool access stores overrides in instance-local `profile_toolsets.json` without changing bundled profiles. Restoring defaults removes the override. Active-profile changes reconnect the conversation; other changes apply when selected.

Profile directories are data-only. Python tool implementations belong in `src/reachy_mini_conversation_app/tools/`, or in `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY` for external tools. Each enabled tool ID must resolve to a shared tool, an external tool, or a tool from an installed Hugging Face Space.

See [Creating and adding tools](#creating-and-adding-tools) for the local tool interface and a maintained example.

To manage personalities in the UI:

With `--ui`, Home lists the available profiles and the built-in default:

- Tap a card to apply that personality and start talking.
- Tap "Manage tools" on a saved personality to open its tool access directly.
- Tap "Custom" to create a personality with a name, instructions, and optional greeting. It inherits the default tools, which can be changed under "Manage tools". Managed instances store it at `user_personalities/<name>/profile.md`; standalone runs use `external_content/user_personalities/<name>/profile.md`.

Switching a personality reloads its prompt and effective tools through a quick backend reconnect. Editing `profile.md` directly requires re-selecting the profile or restarting the app.

</details>

<details>
<summary>Locked profile mode</summary>

To create a locked variant of the app that cannot switch profiles, edit `src/reachy_mini_conversation_app/config.py` and set the `LOCKED_PROFILE` constant to the desired profile name:
```python
LOCKED_PROFILE: str | None = "mars_rover"  # Lock to this profile
```
When set, the app ignores saved startup settings, `REACHY_MINI_CUSTOM_PROFILE`, and UI selection. The UI marks the profile as locked and disables editing.

</details>

<a id="external-profiles-and-tools"></a>

<details>
<summary>External profiles and tools</summary>

You can extend the app with profiles/tools stored outside the repository defaults.

- Core profiles are under `profiles/`.
- Core tools are under `src/reachy_mini_conversation_app/tools/`.

Recommended layout:

```text
external_content/
├── external_profiles/
│   └── my_profile/
│       └── profile.md
├── external_tools/
│   └── my_custom_tool.py
├── user_personalities/
│   └── my_custom_profile/
│       └── profile.md
├── installed_tool_spaces.json
└── profile_toolsets.json
```

Environment variables:

Set these values in your `.env` when you want env-driven external profile/tool selection:

```env
# Optional fallback/manual profile selector:
REACHY_MINI_CUSTOM_PROFILE=my_profile
REACHY_MINI_EXTERNAL_PROFILES_DIRECTORY=./external_content/external_profiles
REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY=./external_content/external_tools
# Optional convenience mode:
# AUTOLOAD_EXTERNAL_TOOLS=1
```

Loading rules:

- Profiles: each directory requires a schema-version-1 `profile.md` with explicit `default_tools`; there is no cross-profile fallback.
- Default mode: enabled IDs must resolve to a shared, external, or installed Tool Space tool.
- Autoload: `AUTOLOAD_EXTERNAL_TOOLS=1` adds every valid `*.py` module from `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`.
- Web UI: Tools → Tool access enables external modules per profile; it does not upload or edit Python.
- Separation: profile directories contain data only; external Python belongs in `REACHY_MINI_EXTERNAL_TOOLS_DIRECTORY`.
- Tool names: every loaded class needs a unique `Tool.name`; duplicates fail fast.

</details>

<a id="installing-hugging-face-space-tools"></a>

<details>
<summary>Installing Hugging Face Space tools</summary>

You can install MCP-compatible Hugging Face Spaces as remote tool sources for this app. Private Spaces work too, as long as `HF_TOKEN` is set (or you have run `hf auth login`) for an account that can access them. To publish a new Space, follow [Creating and adding tools](#hugging-face-space-tools).

Tools → Tool Spaces installs or refreshes a global source. Its tools then appear under Tools → Tool access for per-profile selection. Removing a Space removes its tools from every profile. Active-profile changes reconnect the conversation; other changes apply when selected.

The app accepts Hugging Face Spaces exposing the standard `/gradio_api/mcp/` endpoint, not arbitrary MCP URLs. Installation discovers the Space's tools and assigns namespaced local IDs, so do not guess or hard-code those IDs beforehand.

```bash
# install + enable in active profile
reachy-mini-qwen-realtime-app tool-spaces add <owner/space-name>

# enable in a specific profile
reachy-mini-qwen-realtime-app tool-spaces add <owner/space-name> --profile NAME

# install without enabling
reachy-mini-qwen-realtime-app tool-spaces add <owner/space-name> --install-only

# list installed spaces
reachy-mini-qwen-realtime-app tool-spaces list

# remove an installed space
reachy-mini-qwen-realtime-app tool-spaces remove owner/space-name
```

Bundled Pollen Spaces use static specs and are enabled by the default profile. Custom Spaces are validated through the Hugging Face Hub; HF tokens are sent only to private Spaces. Tool metadata is cached in:

- `installed_tool_spaces.json` in the managed app instance directory
- `external_content/installed_tool_spaces.json` in terminal mode

Startup and profile switching read this cache without discovery or MCP probing. Network access occurs only during install, refresh, or remote tool calls. Per-profile access is stored in `profile_toolsets.json` beside the manifest, or under `external_content/` in terminal mode.

Recommended tags for discoverability on Hugging Face:

- `reachy-mini-tool`
- `mcp`

Tags are advisory; installation still requires successful MCP validation.

> [!NOTE]
> Preinstalled Pollen Spaces can be removed like any other (`tool-spaces remove pollen-robotics/reachy-mini-weather-tool`). To restore access, reinstall the Space and restore or update the relevant profile under "Tool access".

</details>

<details>
<summary>Multiple robots on the same subnet</summary>

If you run multiple Reachy Mini daemons on the same network, use:

```bash
reachy-mini-qwen-realtime-app --robot-name <name>
```

`<name>` must match the daemon's `--robot-name` value so the app connects to the correct robot.

</details>

## Regional connectivity and rollback

The direct Qwen and Exa clients deliberately ignore inherited system proxies. This avoids stale loopback proxy settings such as `127.0.0.1:<port>` breaking Alibaba Cloud, Exa, PyPI, or GitHub when no local proxy process is listening. Do not configure a loopback proxy on Reachy Mini unless that proxy is actually running on the robot.

This path can keep core Qwen conversation, camera, robot tools, and Exa search available where `huggingface.co` login or app discovery is unreliable. It does not repair Reachy Mini Control's Hugging Face OAuth/App Store, and Hugging Face-hosted models, datasets, emotions, or Tool Spaces may still require direct access, a configured mirror, or a populated cache. The upstream regional issue is tracked in [conversation app #456](https://github.com/pollen-robotics/reachy_mini_conversation_app/issues/456) and [desktop app #293](https://github.com/pollen-robotics/reachy-mini-desktop-app/issues/293).

Before upgrading a Wireless robot, back up the current app `.env`, external profiles, app package list, and the installed wheel. Verify the downloaded release wheel's SHA-256 before installation. To roll back, stop the app, disable motors, reinstall the previously saved wheel without changing dependencies, restore the private `.env` and profile directories, then restart the Daemon and app. Never copy credentials into issue reports or public logs.

Security boundaries:

- Qwen credentials are sent only as an Authorization header to allowlisted official Alibaba Cloud WSS endpoints.
- Exa receives only the text query; it does not receive camera images, audio, robot identifiers, or local files.
- Search output is untrusted and bounded before it returns to the model.
- Public source, wheel, release notes, commit metadata, and test evidence must remain free of credentials and deployment-specific identifiers.

## Upstream coordination

- [Issue #539](https://github.com/pollen-robotics/reachy_mini_conversation_app/issues/539) proposes direct Qwen Omni Realtime support.
- [Draft PR #540](https://github.com/pollen-robotics/reachy_mini_conversation_app/pull/540) contains the provider-only v1 port and intentionally excludes Exa-specific community packaging.
- Upstream v1 retains its generic MCP Tool Space architecture and maintained Pollen tools. This community release adds direct Exa search for networks where Hugging Face-hosted MCP Spaces are not the preferred path.
- Pollen Robotics deliberately consolidated the official app around Hugging Face in [PR #444](https://github.com/pollen-robotics/reachy_mini_conversation_app/pull/444); this fork keeps Hugging Face available while making Qwen opt-in.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and [`AGENTS.md`](AGENTS.md) for coding-agent standards.

## License

Apache 2.0
