"""Static mobile-controller contract tests."""

import re
from pathlib import Path


STATIC_ROOT = Path(__file__).parents[1] / "src" / "reachy_mini_conversation_app" / "local_control" / "static"


def _read(name: str) -> str:
    return (STATIC_ROOT / name).read_text(encoding="utf-8")


def test_mobile_pages_are_self_contained_and_touch_friendly() -> None:
    """The controller works on an isolated LAN without external assets."""
    index = _read("index.html")
    setup = _read("setup.html")
    apps = _read("apps.html")
    motions = _read("motions.html")
    media = _read("media.html")
    css = _read("style.css")
    combined = "\n".join((index, setup, apps, motions, media, css, _read("app.js"), _read("local-webrtc.js")))

    assert 'name="viewport"' in index
    assert 'name="viewport"' in setup
    assert 'name="viewport"' in apps
    assert 'name="viewport"' in motions
    assert 'name="viewport"' in media
    assert not re.search(r"https?://", combined)
    assert "min-height: 48px" in css
    assert "@media (max-width: 620px)" in css
    assert "env(safe-area-inset-bottom)" in css


def test_mobile_dashboard_keeps_emergency_stop_and_qwen_controls_visible() -> None:
    """Primary event controls are explicit and discoverable in static markup."""
    index = _read("index.html")

    assert 'data-action="qwen-start"' in index
    assert 'data-action="qwen-stop"' in index
    assert 'data-action="qwen-restart"' in index
    assert 'data-action="emergency-stop"' in index
    assert "立即停止" in index
    assert 'href="/setup"' in index
    assert 'href="/apps"' in index
    assert 'href="/motions"' in index
    assert 'href="/media"' in index


def test_media_page_is_silent_permission_free_and_touch_friendly() -> None:
    """The phone receives video and volume controls without becoming a media source."""
    media = _read("media.html")
    script = _read("app.js")
    webrtc = _read("local-webrtc.js")

    assert 'data-page="media"' in media
    assert '<video id="camera-video"' in media
    assert "muted" in media
    assert "playsinline" in media
    assert 'data-action="video-connect"' in media
    assert 'data-action="video-disconnect"' in media
    assert 'data-action="video-fullscreen"' in media
    assert 'id="speaker-volume"' in media
    assert 'id="microphone-volume"' in media
    assert media.count('type="range"') == 2
    assert media.count('min="0"') == 2
    assert media.count('max="100"') == 2
    assert media.count('step="1"') == 2
    assert "不会在手机播放机器人麦克风声音" in media
    assert 'api("/api/media/volume"' in script
    assert 'api("/api/media/microphone"' in script
    assert "getUserMedia" not in webrtc
    assert "AudioContext" not in webrtc


def test_installed_app_page_has_confirmed_switch_and_local_ui_controls() -> None:
    """App switching is explicit and can expose only rewritten local settings links."""
    apps = _read("apps.html")
    script = _read("app.js")

    assert 'data-page="apps"' in apps
    assert 'id="app-list"' in apps
    assert 'id="app-switch-dialog"' in apps
    assert "停止当前应用并启动" in apps
    assert 'api("/api/apps")' in script
    assert "/switch`" in script
    assert "custom_ui_port" in script


def test_motion_page_is_searchable_grouped_and_keeps_both_stop_levels() -> None:
    """Large live catalogs remain usable without weakening emergency semantics."""
    motions = _read("motions.html")
    script = _read("app.js")

    assert 'data-page="motions"' in motions
    assert 'id="motion-search"' in motions
    assert 'data-motion-tab="emotion"' in motions
    assert 'data-motion-tab="dance"' in motions
    assert 'data-action="motion-stop"' in motions
    assert 'data-action="emergency-stop"' in motions
    assert 'api("/api/motions/catalog")' in script
    assert 'api("/api/motions/status")' in script
    assert "/api/robot/emergency-stop" in script
    assert "未安装此动作库" in script
    assert "motion-button__emoji" in script


def test_setup_page_lists_saved_networks_before_new_credentials() -> None:
    """Saved credentials are reused through explicit rows, not copied into the browser."""
    setup = _read("setup.html")
    script = _read("app.js")

    assert setup.index('id="saved-network-list"') < setup.index('id="network-list"')
    assert 'api("/api/wifi/switch"' in script
    assert "本页面会暂时断开" in script
    assert "已连接" in script


def test_setup_page_handles_passwords_without_browser_storage() -> None:
    """Wi-Fi credentials exist only in the active form submission."""
    setup = _read("setup.html")
    script = _read("app.js")

    assert 'type="password"' in setup
    assert 'autocomplete="current-password"' in setup
    assert 'passwordInput.value = ""' in script
    assert not re.search(r"localStorage\.(setItem|getItem)\([^\n]*(password|pin)", script, re.IGNORECASE)


def test_mobile_script_caps_reconnect_and_documents_both_recovery_hosts() -> None:
    """Connection recovery covers mDNS and the robot AP without rapid polling."""
    script = _read("app.js")
    setup = _read("setup.html")

    assert "Math.min(reconnectDelay * 2, 10000)" in script
    assert "reachy-mini.local:7861" in setup
    assert "10.42.0.1:7861" in setup
    assert 'api("/api/wifi/error")' in script
    assert "密码错误，机器人已恢复配网热点" in script


def test_mobile_pages_use_official_makerseed_brand_assets_and_colors() -> None:
    """The local controller reflects the workshop brand without weakening safety colors."""
    index = _read("index.html")
    setup = _read("setup.html")
    apps = _read("apps.html")
    motions = _read("motions.html")
    css = _read("style.css").lower()

    assert (STATIC_ROOT / "makerseed-logo.png").is_file()
    assert 'src="/assets/makerseed-logo.png"' in index
    assert 'src="/assets/makerseed-logo.png"' in setup
    assert 'src="/assets/makerseed-logo.png"' in apps
    assert 'src="/assets/makerseed-logo.png"' in motions
    assert 'alt="种子创客工坊"' in index
    assert "--brand-orange: #ff5a36" in css
    assert "--brand-blue: #0079c8" in css
    assert "--brand-purple: #6144d8" in css
    assert "--brand-yellow: #ffb020" in css
    assert "--brand-green: #3aaa4a" in css
    assert "--brand-ink: #16121f" in css
    assert "--brand-warm: #fff7f2" in css
    assert "--danger: #d92d20" in css
    assert "--button-shadow:" in css
    assert "box-shadow: var(--button-shadow)" in css
