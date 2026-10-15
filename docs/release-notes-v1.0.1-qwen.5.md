# Reachy Mini Qwen Realtime v1.0.1-qwen.5

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

---

## English release notes

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
