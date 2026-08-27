"use strict";

const page = document.body.dataset.page;
const loginPanel = document.querySelector("#login-panel");
const controlPanel = document.querySelector("#control-panel");
const emergencyBar = document.querySelector("#emergency-bar");
let reconnectDelay = 1000;
let pollTimer = null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 401) {
    showLogin();
    throw new Error("authentication_required");
  }
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) throw new Error(payload?.error || payload?.detail || `http_${response.status}`);
  return payload;
}

function showLogin() {
  loginPanel.hidden = false;
  controlPanel.hidden = true;
  if (emergencyBar) emergencyBar.hidden = true;
}

function showControls() {
  loginPanel.hidden = true;
  controlPanel.hidden = false;
  if (emergencyBar) emergencyBar.hidden = false;
}

function message(target, copy, kind = "") {
  if (!target) return;
  target.textContent = copy;
  target.className = `message ${kind ? `message--${kind}` : ""}`.trim();
}

async function login(event) {
  event.preventDefault();
  const pinInput = document.querySelector("#pin");
  const error = document.querySelector("#login-error");
  try {
    await api("/api/session", { method: "POST", body: JSON.stringify({ pin: pinInput.value }) });
    pinInput.value = "";
    error.hidden = true;
    showControls();
    startPage();
  } catch (failure) {
    error.hidden = false;
    message(error, failure.message === "invalid_pin" ? "PIN 不正确" : "无法登录", "error");
  }
}

document.querySelector("#login-form")?.addEventListener("submit", login);

function formatState(value, healthy = false) {
  if (!value) return "未知";
  return healthy ? `正常 · ${value}` : String(value);
}

async function refreshDashboard() {
  try {
    const status = await api("/api/status");
    showControls();
    document.querySelector('[data-status="daemon"]').textContent = formatState(
      status.daemon?.version,
      status.daemon?.state === "running" && !status.daemon?.error
    );
    document.querySelector('[data-status="motors"]').textContent = status.motors?.mode === "enabled" ? "已启用" : "已失能";
    document.querySelector('[data-status="qwen"]').textContent = status.qwen?.backend_connected ? "已连接" : "未连接";
    document.querySelector('[data-status="wifi"]').textContent = status.wifi?.connected_network || status.wifi?.mode || "未连接";
    document.querySelector("#connection-copy").textContent = "局域网已连接";
    document.querySelector("#advanced-qwen").href = `${location.protocol}//${location.hostname}:7860`;
    reconnectDelay = 1000;
  } catch (failure) {
    if (failure.message !== "authentication_required") {
      document.querySelector("#connection-copy").textContent = "连接中断，正在重试…";
      reconnectDelay = Math.min(reconnectDelay * 2, 10000);
    }
  } finally {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(refreshDashboard, reconnectDelay === 1000 ? 3000 : reconnectDelay);
  }
}

async function postAction(path, successCopy) {
  const target = document.querySelector("#operation-message");
  try {
    await api(path, { method: "POST" });
    message(target, successCopy, "success");
    setTimeout(refreshDashboard, 300);
  } catch (failure) {
    message(target, `操作失败：${failure.message}`, "error");
  }
}

function bindDashboard() {
  document.querySelector('[data-action="refresh-status"]')?.addEventListener("click", refreshDashboard);
  document.querySelector('[data-action="qwen-start"]')?.addEventListener("click", () => postAction("/api/qwen/start", "Qwen 正在启动"));
  document.querySelector('[data-action="qwen-stop"]')?.addEventListener("click", () => postAction("/api/qwen/stop", "Qwen 已停止"));
  document.querySelector('[data-action="qwen-restart"]')?.addEventListener("click", () => postAction("/api/qwen/restart", "Qwen 正在重启"));
  document.querySelector('[data-action="emergency-stop"]')?.addEventListener("click", () => postAction("/api/robot/stop", "动作已立即停止"));
  document.querySelectorAll("[data-endpoint]").forEach((button) => {
    button.addEventListener("click", () => postAction(button.dataset.endpoint, `${button.textContent.trim()}指令已发送`));
  });
  document.querySelectorAll("[data-robot-action]").forEach((button) => {
    button.addEventListener("click", () => postAction(`/api/actions/${button.dataset.robotAction}`, `${button.textContent.trim()}已执行`));
  });
}

async function refreshWifiStatus() {
  const [status, lastError] = await Promise.all([api("/api/wifi/status"), api("/api/wifi/error")]);
  showControls();
  document.querySelector('[data-wifi="connected"]').textContent = status.connected_network || status.mode || "未连接";
  if (lastError.error) {
    const copy =
      lastError.error === "authentication_failed"
        ? "密码错误，机器人已恢复配网热点"
        : lastError.error === "network_not_found"
          ? "没有找到目标网络，机器人已恢复配网热点"
          : "连接失败，机器人已恢复配网热点";
    message(document.querySelector("#wifi-message"), copy, "error");
  }
}

async function scanNetworks() {
  const list = document.querySelector("#network-list");
  list.replaceChildren(Object.assign(document.createElement("p"), { className: "message", textContent: "正在扫描…" }));
  try {
    const networks = await api("/api/wifi/scan", { method: "POST" });
    list.replaceChildren();
    if (!networks.length) {
      list.append(Object.assign(document.createElement("p"), { className: "message", textContent: "没有发现网络，可手工输入 SSID。" }));
      return;
    }
    networks.forEach((ssid) => {
      const button = Object.assign(document.createElement("button"), {
        className: "network-row",
        type: "button",
        textContent: ssid,
      });
      button.addEventListener("click", () => {
        document.querySelector("#ssid").value = ssid;
        document.querySelector("#wifi-password").focus();
      });
      list.append(button);
    });
  } catch (failure) {
    list.replaceChildren(Object.assign(document.createElement("p"), { className: "message message--error", textContent: `扫描失败：${failure.message}` }));
  }
}

async function connectWifi(event) {
  event.preventDefault();
  const ssidInput = document.querySelector("#ssid");
  const passwordInput = document.querySelector("#wifi-password");
  const target = document.querySelector("#wifi-message");
  try {
    await api("/api/wifi/connect", {
      method: "POST",
      body: JSON.stringify({ ssid: ssidInput.value, password: passwordInput.value }),
    });
    message(target, "机器人正在切换网络。请让手机加入相同网络，再访问 reachy-mini.local:7861。", "success");
  } catch (failure) {
    message(target, `连接失败：${failure.message}`, "error");
  } finally {
    passwordInput.value = "";
  }
}

function bindSetup() {
  document.querySelector("#scan-button")?.addEventListener("click", scanNetworks);
  document.querySelector("#wifi-form")?.addEventListener("submit", connectWifi);
}

async function startPage() {
  if (page === "dashboard") await refreshDashboard();
  if (page === "setup") {
    try {
      await refreshWifiStatus();
    } catch (failure) {
      if (failure.message !== "authentication_required") {
        message(document.querySelector("#wifi-message"), "无法读取网络状态", "error");
      }
    }
  }
}

if (page === "dashboard") bindDashboard();
if (page === "setup") bindSetup();
startPage();
