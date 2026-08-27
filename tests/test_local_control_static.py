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
    css = _read("style.css")
    combined = "\n".join((index, setup, css, _read("app.js")))

    assert 'name="viewport"' in index
    assert 'name="viewport"' in setup
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


def test_mobile_pages_use_official_makerseed_brand_assets_and_colors() -> None:
    """The local controller reflects the workshop brand without weakening safety colors."""
    index = _read("index.html")
    setup = _read("setup.html")
    css = _read("style.css").lower()

    assert (STATIC_ROOT / "makerseed-logo.png").is_file()
    assert 'src="/assets/makerseed-logo.png"' in index
    assert 'src="/assets/makerseed-logo.png"' in setup
    assert 'alt="种子创客工坊"' in index
    assert "--brand-orange: #ff5a36" in css
    assert "--brand-blue: #0079c8" in css
    assert "--brand-purple: #6144d8" in css
    assert "--brand-yellow: #ffb020" in css
    assert "--brand-green: #3aaa4a" in css
    assert "--brand-ink: #16121f" in css
    assert "--brand-warm: #fff7f2" in css
    assert "--danger: #d92d20" in css
