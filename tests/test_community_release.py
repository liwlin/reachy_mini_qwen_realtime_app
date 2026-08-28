"""Community release compatibility tests."""

import re
import sys
import runpy
import tomllib
import importlib
import subprocess
import importlib.util
from pathlib import Path

import pytest

from reachy_mini import ReachyMiniApp
from reachy_mini_conversation_app.profile_store import read_packaged_default_profile


def test_wireless_entrypoint_source_exposes_discoverable_custom_url() -> None:
    """Daemon 1.9 can discover the secondary UI from the entry-point package."""
    package_spec = importlib.util.find_spec("reachy_mini_qwen_realtime_app")
    assert package_spec is not None
    spec = importlib.util.find_spec("reachy_mini_qwen_realtime_app.main")
    assert spec is not None and spec.origin is not None

    source = Path(spec.origin).read_text(encoding="utf-8")
    match = re.search(r'custom_app_url\s*(?::\s*[^=]+)?\s*=\s*["\']([^"\']+)["\']', source)
    assert match is not None
    assert match.group(1) == "http://0.0.0.0:7860/"


def test_wireless_entrypoint_loads_qwen_app_class() -> None:
    """The branded entry point loads a real Reachy Mini application class."""
    package_spec = importlib.util.find_spec("reachy_mini_qwen_realtime_app")
    assert package_spec is not None
    spec = importlib.util.find_spec("reachy_mini_qwen_realtime_app.main")
    assert spec is not None

    module = importlib.import_module("reachy_mini_qwen_realtime_app.main")
    app_class = module.ReachyMiniQwenRealtimeApp
    assert issubclass(app_class, ReachyMiniApp)
    assert app_class.custom_app_url == "http://0.0.0.0:7860/"


def test_wireless_package_import_does_not_preload_module_runner() -> None:
    """Package discovery must not import main before Daemon executes it with python -m."""
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, reachy_mini_qwen_realtime_app; "
                "assert 'reachy_mini_qwen_realtime_app.main' not in sys.modules"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_wireless_module_execution_starts_branded_app(monkeypatch: pytest.MonkeyPatch) -> None:
    """Daemon 1.9 executes the entry-point module with ``python -m``."""
    launched: list[str] = []

    def record_run(app: ReachyMiniApp) -> None:
        launched.append(type(app).__name__)

    monkeypatch.setattr(ReachyMiniApp, "wrapped_run", record_run)
    spec = importlib.util.find_spec("reachy_mini_qwen_realtime_app.main")
    assert spec is not None and spec.origin is not None

    runpy.run_path(spec.origin, run_name="__main__")

    assert launched == ["ReachyMiniQwenRealtimeApp"]


def test_wireless_wrapper_keeps_shared_instance_and_static_directory() -> None:
    """Branding must not move private config or the secondary UI assets."""
    module = importlib.import_module("reachy_mini_qwen_realtime_app.main")
    app = module.ReachyMiniQwenRealtimeApp()

    instance_file = app._get_instance_path()

    assert instance_file.parent.name == "reachy_mini_conversation_app"
    assert (instance_file.parent / "static" / "index.html").is_file()
    assert (instance_file.parent / ".env.example").is_file()


def test_community_default_enables_exa_web_search() -> None:
    """Fresh community installs expose the direct Exa tool by default."""
    profile = read_packaged_default_profile()
    assert "web_search" in profile.default_tools


def test_local_control_release_contract() -> None:
    """The release ships an independent local-control command and mobile assets."""
    project_root = Path(__file__).parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["scripts"]["reachy-mini-local-control"] == (
        "reachy_mini_conversation_app.local_control.main:main"
    )

    package_spec = importlib.util.find_spec("reachy_mini_conversation_app")
    assert package_spec is not None and package_spec.origin is not None
    package_root = Path(package_spec.origin).parent
    static_root = package_root / "local_control" / "static"
    assert (static_root / "index.html").is_file()
    assert (static_root / "apps.html").is_file()
    assert (static_root / "motions.html").is_file()
    assert (static_root / "setup.html").is_file()
    assert (static_root / "app.js").is_file()
    assert (static_root / "style.css").is_file()
    assert (static_root / "makerseed-logo.png").is_file()

    service = package_root / "local_control" / "local.service"
    assert service.is_file()
    service_text = service.read_text(encoding="utf-8")
    assert "After=reachy-mini-daemon.service" in service_text
    assert "ExecStart=/venvs/apps_venv/bin/reachy-mini-local-control" in service_text
    assert "Restart=always" in service_text
    assert "User=pollen" in service_text
    assert "Group=pollen" in service_text
    assert "WantedBy=multi-user.target" in service_text
    assert "DASHSCOPE" not in service_text
    assert "API_KEY" not in service_text


def test_community_project_metadata_and_entry_points() -> None:
    """The release metadata installs the branded CLI and Wireless entry point."""
    project_root = Path(__file__).parents[1]
    metadata = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))

    assert metadata["project"]["name"] == "reachy_mini_qwen_realtime_app"
    assert metadata["project"]["version"] == "1.0.1+qwen.4"
    assert metadata["project"]["scripts"] == {
        "reachy-mini-qwen-realtime-app": "reachy_mini_conversation_app.main:main",
        "reachy-mini-local-control": "reachy_mini_conversation_app.local_control.main:main",
    }
    assert metadata["project"]["entry-points"]["reachy_mini_apps"] == {
        "reachy_mini_qwen_realtime_app": ("reachy_mini_qwen_realtime_app.main:ReachyMiniQwenRealtimeApp")
    }
