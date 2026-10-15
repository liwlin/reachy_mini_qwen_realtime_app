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
- [中文快速使用说明](#中文快速使用说明)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the app](#running-the-app)
- [LLM tools](#llm-tools-exposed-to-the-assistant)
- [Creating and adding tools](#creating-and-adding-tools)
- [Advanced features](#advanced-features)
- [Local mobile control](#local-mobile-control)
- [Regional connectivity and rollback](#regional-connectivity-and-rollback)
- [Upstream coordination](#upstream-coordination)
- [Contributing](#contributing)
- [License](#license)

## Overview

- Low-latency audio conversation through either the Hugging Face realtime backend or direct DashScope/Qwen Omni Realtime.
- Vision is handled by the selected realtime backend when the `camera` tool is used.
- Layered motion system queues primary moves (dances, emotions, goto poses, breathing) while blending speech-reactive wobble.
- Async tools integrate motion, camera capture, Exa Streamable HTTP MCP search, and upstream MCP Tool Spaces. The optional web UI (`--ui`) manages conversations, personalities, tools, and settings.
- An independent LAN gateway keeps Qwen lifecycle, safe robot actions, emergency stop, and Wi-Fi recovery available from iPhone Safari or Android Chrome even while the conversation process is stopped.

## Community release

Version `v1.0.1-qwen.5` keeps upstream v1's `ConversationHandler`, profile store, UI, memory, and generic Tool Space architecture, then adds provider-local Qwen wire handling, direct Exa search, and an HF-independent LAN mobile controller. It includes all qwen.4 local-control and Wireless audio fixes:

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
- `reachy-mini-local-control` runs independently on port 7861, proxies only fixed loopback operations, and remains available while Qwen is stopped.
- The branded mobile UI uses the official Makerseed workshop logo and palette, a device-PIN session, a strict action allowlist, and an always-visible emergency stop.
- Saved hotspot/router profiles and the existing `reachy-mini-ap` fallback are manageable without Hugging Face OAuth or signaling.
- Installed apps can be listed, stopped, and switched with confirmation and automatic rollback; cached emotions and dances are searchable through live Daemon catalogs without move stacking.
- Saved Wi-Fi profiles can be activated without re-entering their passwords, and the red emergency stop now stops every Daemon move before disabling motors.
- The PIN-protected media page consumes the robot's existing LAN WebRTC producer directly on port 8443, renders silent video without HF signalling, and never requests phone camera or microphone access.
- Speaker output and microphone input volumes are readable and adjustable from the phone through four fixed Daemon 1.9 loopback operations; the browser receives no general REST proxy.

## 中文快速使用说明

适用于 **Reachy Mini Wireless + 社区应用 v1.0.1-qwen.5**。本版本真机验收基线为 **Daemon 1.9.0**；应用版本和系统版本分别管理，使用这些功能不需要先升级 Daemon。已完成安装和 Qwen 配置的机器人，可以直接从下面第 1 步开始。

### 1. 手机连接机器人

1. 给机器人开机，等待它连接已保存的 Wi-Fi。手机与机器人接入同一便携路由器、移动 Wi-Fi 或家庭网络。
2. 手机浏览器输入 `http://reachy-mini.local:7861`。如果打不开，改用 `http://<机器人当前IP>:7861`；IP 可在 Reachy Mini Control 或路由器的设备列表中查看。
3. 输入**这台机器人的 PIN**，点击“进入控制”。PIN 不是 Wi-Fi 密码，也不是 Qwen API Key；请向设备管理员获取，保留可能存在的前导零。
4. 确认首页 Daemon 状态正常。需要动作时先点击“唤醒”，等待动作结束，再确认电机“已启用”。

本地控制页面不需要 Hugging Face 登录。Qwen 对话仍需机器人能连接阿里云服务，Exa 搜索仍需联网。

### 2. 启动 Qwen 对话

- 在首页点击“启动 Qwen”，等待 Qwen 状态变为“已连接”，然后**对着机器人的麦克风讲话**。
- 语音问答：“你好，介绍一下你自己。”
- 视觉识别：“帮我看看你前面有什么东西。”当前人格需要启用 `camera` 工具。
- 网络搜索：“请联网搜索一下今天的科技新闻，并告诉我来源。”当前人格需要启用 `web_search` 工具。
- 点击“高级 Qwen 设置”打开应用设置页（`7860` 端口），选择人格、音色和工具；应用须先运行。
- 结束对话时点击“停止 Qwen”；遇到对话连接异常可点击“重启 Qwen”。这两个快捷按钮应在当前运行应用为 Qwen 时使用；管理其他应用请进入“应用管理”。

本地控制服务可以随开机启动，**不代表 Qwen 一定自动启动**；以首页“已连接”状态为准。只有明确配置了应用自启动，才会在开机后自动运行 Qwen。

### 3. 动作、表情、舞蹈与应用切换

| 入口 | 使用方法 |
| --- | --- |
| 首页“动作控制” | Qwen 运行且电机已启用时，可点向左看、向右看、回正、点头等快捷动作。 |
| “表情与舞蹈” | 切换分类，按中文或英文名称搜索，点击“emoji + 中文名称”按钮执行；图标和文字属于同一个按钮。 |
| 动作页的普通“停止” | 停止当前动作，保留电机启用状态。 |
| 底部红色“立即停止” | 停止动作并使电机失能；需要继续动作时，先点击“唤醒”。它不等于停止 Qwen 或退出当前 App。 |
| “应用管理” | 查看机器人上已安装的 App；切换前会弹窗确认，确认后自动停止当前 App，再启动目标 App。 |

动作目录按机器人实际已安装或缓存的动作库显示，数量可能不同；“未安装此动作库”表示该库当前不可用。

**本版本的“休眠”不会自动退出当前 App。** Qwen 运行时会暂停其动作控制，再执行机器人休眠动作；语音对话可能继续。如需结束对话，还要单独停止 Qwen。再次“唤醒”会启用电机并执行唤醒动作，但不会自动重启已停止的 App。

### 4. 实时画面和声音调节

在首页进入“音视频控制”，或打开 `http://reachy-mini.local:7861/media`：

- 点“连接画面”开始查看机器人摄像头；支持“断开画面”和“全屏”。
- 手机只显示**静音实时画面**，不会播放机器人麦克风的声音，也不需要手机摄像头或麦克风权限。
- “扬声器”调节机器人说话的音量；“麦克风输入”调节机器人接收现场声音的输入音量。范围均为 `0–100`。
- 拖动滑块并松开后应用；每路都可以“静音/恢复”。扬声器调节后可能播放一次短提示音。
- 该版本此前真机测得画面为 `1280×720`。快速动作时可能出现模糊，现场应保证照明充足。
- 关闭或离开媒体页面后，再次进入时需要重新点击“连接画面”。本页断开视频不会主动停止 Qwen。

### 5. 外出活动与网络配网

- **移动 Wi-Fi / 便携路由器：**让手机和机器人都连接它，按第 1 步打开控制页面。
- **同一手机开热点：**提前把热点名称和密码保存到机器人；现场打开热点后等待机器人连接，再用该手机访问机器人当前 IP。热点宿主访问客户端的能力依手机系统而异，出发前先在实际手机上试通；不通时改用便携路由器。
- **切换已保存网络：**进入“网络配网” → “已保存网络” → 点目标网络的“切换”并确认，无需重新输入密码。
- **连接新网络：**点“扫描附近网络”，选择名称，输入密码后点“连接此网络”。
- 换网时页面短暂断开属正常现象。让手机加入目标网络，再打开 `reachy-mini.local:7861` 或机器人的新 IP。
- **连接失败或没有可用网络：**当机器人提供 `reachy-mini-ap` 恢复热点时，用手机加入它，再打开 `http://10.42.0.1:7861/setup` 配网。
- 配网需要手机加入机器人恢复热点；如果这台手机还承担上网热点，请准备另一台手机/电脑或便携路由器协助，避免切换 Wi-Fi 时中断供网。

### 6. 常见问题

| 现象 | 先检查 |
| --- | --- |
| 页面打不开 | 手机与机器人是否同网段；尝试当前 IP；确认本地控制服务已启动，网络没有设备隔离。 |
| 升级后画面一直“连接中断，正在重试” | 关闭旧标签页重新打开或强制刷新，再点“连接画面”。若仍失败，检查机器人 `8443` 信令端口和局域网媒体连接；不要反复改 API Key。 |
| Qwen 未连接 | 确认已启动 Qwen、机器人可联网，Key、地域、workspace/Realtime WebSocket 地址与模型配置匹配。 |
| 能聊天但不动 | 查看电机状态，先“唤醒”；如果运行的是其他 App，先在“应用管理”切回 Qwen，再使用首页快捷动作。 |
| 听不见或听不清 | 检查机器人扬声器/麦克风输入是否被静音；手机本来就不播放实时麦克风声音。 |

### 首次安装与配置（设备管理员）

在 [v1.0.1-qwen.5 Release](https://github.com/liwlin/reachy_mini_qwen_realtime_app/releases/tag/v1.0.1-qwen.5) 的 **Assets** 中下载以下文件（安装此版本请使用 Wheel 附件，仓库 `main` 不一定与该 Release 对应）：

`reachy_mini_qwen_realtime_app-1.0.1+qwen.5-py3-none-any.whl`

SHA-256：`917e9687f5a8f526bde61e955612f477ccc6b49e0edff69a2b30d7f530ae324f`。

将应用安装到 Wireless 的 `/venvs/apps_venv`，保留已有私密配置并启用 `reachy-mini-local-control.service`。首次配置需要设置 `REALTIME_BACKEND=qwen`、`DASHSCOPE_API_KEY`，以及 `QWEN_WORKSPACE_ID` 或完整官方 `QWEN_REALTIME_URL`；地域和模型须与所用服务匹配，普通 HTTPS 聊天接口地址不能直接当作 Realtime WebSocket 地址。

详细步骤见 [安装说明](https://github.com/liwlin/reachy_mini_qwen_realtime_app/blob/feat/local-mobile-control/README.md#installation)、[Qwen 配置](https://github.com/liwlin/reachy_mini_qwen_realtime_app/blob/feat/local-mobile-control/README.md#optional-qwen-realtime-backend) 和 [常驻本地控制服务](https://github.com/liwlin/reachy_mini_qwen_realtime_app/blob/feat/local-mobile-control/README.md#install-the-persistent-system-service-on-wireless)。已经配置完成的设备无需每天重新填写。

设备管理员可在机器人 SSH 终端执行以下只读命令查询本机 PIN；不要把输出或真实 API Key、Wi-Fi 密码提交到公共仓库：

```bash
/venvs/apps_venv/bin/python -c 'from reachy_mini.utils.hardware_id import get_pin; print(get_pin())'
```

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

## Local mobile control

The qwen.5 wheel adds a second process that is deliberately independent from the conversation app. It runs on the Wireless robot, talks to Daemon 1.9 and Qwen only over loopback, and serves a same-origin phone UI on port 7861. It does not relax Daemon CORS, expose arbitrary REST paths, accept arbitrary joint targets, or proxy arbitrary URLs.

### Install the persistent system service on Wireless

After installing the qwen.5 wheel into `/venvs/apps_venv`, copy the packaged system unit. Systemd starts it after the Daemon while the controller process itself runs as the unprivileged `pollen` user:

```bash
unit=$(/venvs/apps_venv/bin/python -c "from importlib.resources import files; print(files('reachy_mini_conversation_app.local_control').joinpath('local.service'))")
sudo install -m 0644 "$unit" /etc/systemd/system/reachy-mini-local-control.service
sudo systemctl daemon-reload
sudo systemctl enable --now reachy-mini-local-control.service
sudo systemctl status reachy-mini-local-control.service --no-pager
```

Open one of these addresses from a phone on the same LAN:

- `http://reachy-mini.local:7861`
- `http://<robot-ip>:7861`
- Recovery AP: `http://10.42.0.1:7861/setup`

After login, the focused secondary pages are:

- `http://reachy-mini.local:7861/apps` — list, stop, and switch installed apps.
- `http://reachy-mini.local:7861/motions` — search live cached emotions and dances, with separate ordinary and emergency stop controls.
- `http://reachy-mini.local:7861/media` — connect silent live video, enter fullscreen, and adjust speaker/microphone volume.
- `http://reachy-mini.local:7861/setup` — switch saved networks, scan nearby SSIDs, or provision a new network.

Sign in with the robot's device PIN. Sessions stay in memory, repeated wrong PIN attempts are temporarily throttled, and neither the PIN nor Wi-Fi passwords are stored in the browser. The media page starts video only after a tap, uses `muted`/`playsinline` for iPhone Safari, discards the robot audio track, and does not ask the phone for media permissions. Speaker changes are applied when the slider is released because Daemon 1.9 plays one short test sound after an output-volume change.

### Network workflow

1. Save the phone hotspot and portable-router profiles before an event. Reachy Mini reconnects through NetworkManager on later boots.
2. If no saved network is available, join the robot's existing `reachy-mini-ap` recovery network and open the setup URL above.
3. For an already-saved SSID, tap **Switch**; no password is read or returned. For a new SSID, scan or enter it and submit its password.
4. After the expected disconnect, manually join the same target network on the phone and reopen `reachy-mini.local:7861` or the new robot IP.

The hotspot hosted by the same phone used for control must be saved in advance: that phone cannot host its hotspot and join `reachy-mini-ap` at the same time. Use a second device or portable router for recovery if those hotspot credentials change.

### Offline and HF-free boundary

LAN status, installed-app switching, Qwen start/stop/restart, motor enable/disable, wake/sleep, saved-network switching, cached expressions, emergency stop, volume control, and local camera viewing do not use Hugging Face OAuth or signalling. The browser negotiates video with the existing GStreamer service at `ws://<robot-host>:8443`; it sends no audio or robot commands. Qwen conversation still needs outbound DashScope access, and Exa search still needs internet. The Pollen emotion/dance datasets are preloaded by Wireless Daemon; optional music dances appear only when the device has a local `Anne-Charlotte/music` cache.

### Disable or roll back

```bash
sudo systemctl disable --now reachy-mini-local-control.service
sudo rm /etc/systemd/system/reachy-mini-local-control.service
sudo systemctl daemon-reload
```

Disabling the companion service does not change Daemon 1.9, Qwen credentials, profiles, startup selection, or motor configuration. To roll back the application, reinstall the previously saved qwen.4 wheel with `--no-deps --force-reinstall`, then restart the local-control service and the Qwen app.

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
