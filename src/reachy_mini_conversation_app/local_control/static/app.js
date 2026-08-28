"use strict";

const page = document.body.dataset.page;
const loginPanel = document.querySelector("#login-panel");
const controlPanel = document.querySelector("#control-panel");
const emergencyBar = document.querySelector("#emergency-bar");
let reconnectDelay = 1000;
let pollTimer = null;
let currentWifiStatus = null;
let pendingApp = null;
let motionCatalog = {};
let motionTab = "emotion";
let motionStatusTimer = null;

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
    if (page === "dashboard") setTimeout(refreshDashboard, 300);
    if (page === "apps") setTimeout(refreshApps, 300);
    if (page === "motions") setTimeout(refreshMotionStatus, 300);
  } catch (failure) {
    message(target, `操作失败：${failure.message}`, "error");
  }
}

function bindDashboard() {
  document.querySelector('[data-action="refresh-status"]')?.addEventListener("click", refreshDashboard);
  document.querySelector('[data-action="qwen-start"]')?.addEventListener("click", () => postAction("/api/qwen/start", "Qwen 正在启动"));
  document.querySelector('[data-action="qwen-stop"]')?.addEventListener("click", () => postAction("/api/qwen/stop", "Qwen 已停止"));
  document.querySelector('[data-action="qwen-restart"]')?.addEventListener("click", () => postAction("/api/qwen/restart", "Qwen 正在重启"));
  document.querySelector('[data-action="emergency-stop"]')?.addEventListener("click", () =>
    postAction("/api/robot/emergency-stop", "动作已停止，电机已失能")
  );
  document.querySelectorAll("[data-endpoint]").forEach((button) => {
    button.addEventListener("click", () => postAction(button.dataset.endpoint, `${button.textContent.trim()}指令已发送`));
  });
  document.querySelectorAll("[data-robot-action]").forEach((button) => {
    button.addEventListener("click", () => postAction(`/api/actions/${button.dataset.robotAction}`, `${button.textContent.trim()}已执行`));
  });
}

function appCard(app) {
  const card = Object.assign(document.createElement("article"), { className: "catalog-card app-card" });
  const heading = Object.assign(document.createElement("div"), { className: "catalog-card__heading" });
  const icon = Object.assign(document.createElement("span"), { className: "catalog-card__icon", textContent: app.emoji || "📦" });
  const copy = document.createElement("div");
  copy.append(
    Object.assign(document.createElement("strong"), { textContent: app.title || app.name }),
    Object.assign(document.createElement("small"), { textContent: app.name })
  );
  heading.append(icon, copy);
  if (app.active) heading.append(Object.assign(document.createElement("span"), { className: "status-badge status-badge--active", textContent: "运行中" }));

  const controls = Object.assign(document.createElement("div"), { className: "card-controls" });
  if (app.active) {
    const stop = Object.assign(document.createElement("button"), { className: "button", type: "button", textContent: "停止" });
    stop.addEventListener("click", () => stopInstalledApp(app));
    controls.append(stop);
  } else {
    const start = Object.assign(document.createElement("button"), {
      className: "button button--primary",
      type: "button",
      textContent: "启动",
    });
    start.addEventListener("click", () => requestAppSwitch(app));
    controls.append(start);
  }
  if (Number.isInteger(app.custom_ui_port)) {
    const settings = Object.assign(document.createElement("a"), {
      className: "button button--link",
      textContent: "打开设置",
      href: `${location.protocol}//${location.hostname}:${app.custom_ui_port}`,
    });
    controls.append(settings);
  }
  card.append(heading, controls);
  return card;
}

function renderApps(apps) {
  const list = document.querySelector("#app-list");
  if (!list) return;
  list.replaceChildren(...apps.map(appCard));
}

async function refreshApps() {
  try {
    const apps = await api("/api/apps");
    showControls();
    renderApps(apps);
    document.querySelector("#connection-copy").textContent = "应用目录已连接";
  } catch (failure) {
    if (failure.message !== "authentication_required") {
      message(document.querySelector("#operation-message"), `读取应用失败：${failure.message}`, "error");
    }
  }
}

function requestAppSwitch(app) {
  pendingApp = app;
  document.querySelector("#app-switch-target").textContent = `目标：${app.title || app.name}`;
  const dialog = document.querySelector("#app-switch-dialog");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else if (window.confirm(`停止当前应用并启动 ${app.title || app.name}？`)) executeAppSwitch();
}

async function executeAppSwitch() {
  if (!pendingApp) return;
  const target = document.querySelector("#operation-message");
  const app = pendingApp;
  pendingApp = null;
  try {
    const result = await api(`/api/apps/${encodeURIComponent(app.name)}/switch`, { method: "POST" });
    message(target, result.changed ? `${app.title || app.name} 已启动` : `${app.title || app.name} 已在运行`, "success");
  } catch (failure) {
    message(target, `切换失败：${failure.message}`, "error");
  }
  await refreshApps();
}

async function stopInstalledApp(app) {
  if (!window.confirm(`停止 ${app.title || app.name}？`)) return;
  try {
    await api(`/api/apps/${encodeURIComponent(app.name)}/stop`, { method: "POST" });
    message(document.querySelector("#operation-message"), `${app.title || app.name} 已停止`, "success");
  } catch (failure) {
    message(document.querySelector("#operation-message"), `停止失败：${failure.message}`, "error");
  }
  await refreshApps();
}

function bindApps() {
  document.querySelector('[data-action="refresh-apps"]')?.addEventListener("click", refreshApps);
  document.querySelector("#app-switch-dialog")?.addEventListener("close", (event) => {
    if (event.currentTarget.returnValue === "confirm") executeAppSwitch();
    else pendingApp = null;
  });
}

function visibleMotionSources() {
  const query = document.querySelector("#motion-search")?.value.trim().toLowerCase() || "";
  return Object.entries(motionCatalog)
    .filter(([, source]) => source.category === motionTab)
    .map(([sourceId, source]) => ({
      sourceId,
      source,
      moves: source.moves.filter((move) => `${move.name} ${move.label}`.toLowerCase().includes(query)),
    }));
}

function renderMotionCatalog() {
  const list = document.querySelector("#motion-list");
  if (!list) return;
  list.replaceChildren();
  visibleMotionSources().forEach(({ sourceId, source, moves }) => {
    const section = Object.assign(document.createElement("section"), { className: "motion-source" });
    const heading = Object.assign(document.createElement("div"), { className: "section-heading" });
    heading.append(
      Object.assign(document.createElement("h3"), { textContent: source.label }),
      Object.assign(document.createElement("span"), {
        className: "count-badge",
        textContent: source.available ? `${source.count} 个` : `预计 ${source.expected_count || 0} 个`,
      })
    );
    section.append(heading);
    if (!source.available) {
      section.append(Object.assign(document.createElement("p"), { className: "message", textContent: "未安装此动作库" }));
    } else if (!moves.length) {
      section.append(Object.assign(document.createElement("p"), { className: "message", textContent: "没有匹配动作" }));
    } else {
      const grid = Object.assign(document.createElement("div"), { className: "motion-grid" });
      moves.forEach((move) => {
        const button = Object.assign(document.createElement("button"), {
          className: "button motion-button",
          type: "button",
          textContent: move.label,
        });
        button.dataset.motionName = move.name;
        button.dataset.motionSource = sourceId;
        button.dataset.available = "true";
        button.addEventListener("click", () => playCatalogMotion(sourceId, move));
        grid.append(button);
      });
      section.append(grid);
    }
    list.append(section);
  });
}

async function refreshMotions() {
  try {
    motionCatalog = await api("/api/motions/catalog");
    showControls();
    renderMotionCatalog();
    document.querySelector("#connection-copy").textContent = "动作目录已连接";
    await refreshMotionStatus();
  } catch (failure) {
    if (failure.message !== "authentication_required") {
      message(document.querySelector("#operation-message"), `读取动作失败：${failure.message}`, "error");
    }
  }
}

async function playCatalogMotion(sourceId, move) {
  try {
    await api(`/api/motions/${encodeURIComponent(sourceId)}/${encodeURIComponent(move.name)}/play`, { method: "POST" });
    message(document.querySelector("#operation-message"), `${move.label} 已开始`, "success");
  } catch (failure) {
    const copy = failure.message === "motors_disabled" ? "请先唤醒机器人" : `动作失败：${failure.message}`;
    message(document.querySelector("#operation-message"), copy, "error");
  }
  await refreshMotionStatus();
}

async function refreshMotionStatus() {
  if (page !== "motions") return;
  try {
    const status = await api("/api/motions/status");
    const running = status.state === "running";
    document.querySelector("#active-motion").textContent = running ? `正在执行：${status.name}` : status.error ? `动作异常：${status.error}` : "当前没有动作";
    document.querySelectorAll("[data-motion-name]").forEach((button) => {
      button.disabled = running || button.dataset.available !== "true";
    });
  } catch (failure) {
    if (failure.message !== "authentication_required") {
      message(document.querySelector("#operation-message"), `状态读取失败：${failure.message}`, "error");
    }
  } finally {
    clearTimeout(motionStatusTimer);
    motionStatusTimer = setTimeout(refreshMotionStatus, 1000);
  }
}

function bindMotions() {
  document.querySelector('[data-action="refresh-motions"]')?.addEventListener("click", () => refreshMotions());
  document.querySelector("#motion-search")?.addEventListener("input", renderMotionCatalog);
  document.querySelectorAll("[data-motion-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      motionTab = button.dataset.motionTab;
      document.querySelectorAll("[data-motion-tab]").forEach((candidate) => {
        const selected = candidate === button;
        candidate.classList.toggle("is-active", selected);
        candidate.setAttribute("aria-selected", String(selected));
      });
      renderMotionCatalog();
    });
  });
  document.querySelector('[data-action="motion-stop"]')?.addEventListener("click", () =>
    postAction("/api/motions/stop", "当前动作已停止")
  );
  document.querySelector('[data-action="emergency-stop"]')?.addEventListener("click", () =>
    postAction("/api/robot/emergency-stop", "动作已停止，电机已失能")
  );
}

async function refreshWifiStatus() {
  const [status, lastError] = await Promise.all([api("/api/wifi/status"), api("/api/wifi/error")]);
  currentWifiStatus = status;
  showControls();
  document.querySelector('[data-wifi="connected"]').textContent = status.connected_network || status.mode || "未连接";
  renderSavedNetworks(status);
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

function renderSavedNetworks(status) {
  const list = document.querySelector("#saved-network-list");
  if (!list) return;
  const networks = Array.isArray(status.known_networks) ? status.known_networks : [];
  if (!networks.length) {
    list.replaceChildren(Object.assign(document.createElement("p"), { className: "message", textContent: "尚未保存网络" }));
    return;
  }
  list.replaceChildren();
  networks.forEach((ssid) => {
    const row = Object.assign(document.createElement("div"), { className: "saved-network-row" });
    const name = Object.assign(document.createElement("strong"), { textContent: ssid });
    row.append(name);
    if (ssid === status.connected_network) {
      row.append(Object.assign(document.createElement("span"), { className: "status-badge status-badge--active", textContent: "已连接" }));
    } else {
      const button = Object.assign(document.createElement("button"), {
        className: "button button--small button--outlined",
        type: "button",
        textContent: "切换",
      });
      button.addEventListener("click", () => switchSavedNetwork(ssid));
      row.append(button);
    }
    list.append(row);
  });
}

async function switchSavedNetwork(ssid) {
  if (!window.confirm(`切换到 ${ssid} 后，本页面会暂时断开。继续吗？`)) return;
  const target = document.querySelector("#wifi-message");
  message(target, `正在切换到 ${ssid}…`, "success");
  try {
    const result = await api("/api/wifi/switch", {
      method: "POST",
      body: JSON.stringify({ ssid }),
    });
    if (result.status === "already_connected") {
      message(target, `${ssid} 已连接`, "success");
      await refreshWifiStatus();
      return;
    }
    message(target, "请让手机加入目标网络，再打开 reachy-mini.local:7861。", "success");
  } catch (failure) {
    message(target, `切换失败：${failure.message}`, "error");
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
        textContent: currentWifiStatus?.known_networks?.includes(ssid) ? `${ssid} · 已保存` : ssid,
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
  if (page === "apps") await refreshApps();
  if (page === "motions") await refreshMotions();
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
if (page === "apps") bindApps();
if (page === "motions") bindMotions();
if (page === "setup") bindSetup();
startPage();
