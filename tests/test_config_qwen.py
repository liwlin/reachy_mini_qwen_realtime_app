"""Configuration tests for Qwen backend selection."""

import pytest

from reachy_mini_conversation_app import config as config_mod


def test_qwen_model_name_selects_qwen_backend() -> None:
    """Qwen model names should select the Qwen realtime backend for old configs."""
    assert config_mod._normalize_backend_provider(model_name="qwen3.5-omni-flash-realtime") == "qwen"


def test_qwen_backend_uses_qwen_default_model() -> None:
    """Qwen backend should resolve to the Qwen realtime default model."""
    assert config_mod._resolve_model_name("qwen", None) == "qwen3.5-omni-flash-realtime"


def test_qwen_backend_uses_tina_as_default_voice() -> None:
    """Qwen 3.5 realtime models default to the Tina voice."""
    assert config_mod.DEFAULT_VOICE_BY_BACKEND[config_mod.QWEN_BACKEND] == "Tina"


@pytest.mark.parametrize(
    ("configured_url", "expected"),
    [
        (
            "wss://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime",
            "wss://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen3.5-omni-flash-realtime",
        ),
        (
            "wss://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=custom-model",
            "wss://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=custom-model",
        ),
    ],
)
def test_qwen_realtime_url_adds_model_query_when_needed(
    monkeypatch: pytest.MonkeyPatch,
    configured_url: str,
    expected: str,
) -> None:
    """A configured base endpoint should receive the selected model query."""
    monkeypatch.setattr(config_mod.config, "QWEN_REALTIME_URL", configured_url)
    monkeypatch.setattr(config_mod.config, "MODEL_NAME", "qwen3.5-omni-flash-realtime")

    assert config_mod.get_qwen_realtime_url() == expected


@pytest.mark.parametrize(
    "url",
    [
        "wss://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen",
        "wss://workspace.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen",
    ],
)
def test_qwen_realtime_url_allows_official_regions(url: str) -> None:
    """Official Beijing and Singapore endpoints should be accepted."""
    assert config_mod.is_qwen_realtime_url_allowed(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "ws://workspace.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime",
        "wss://attacker.example/api-ws/v1/realtime",
        "wss://workspace.cn-beijing.maas.aliyuncs.com/other",
    ],
)
def test_qwen_realtime_url_rejects_non_official_targets(url: str) -> None:
    """Non-TLS, off-domain, and wrong-path endpoints should be rejected."""
    assert config_mod.is_qwen_realtime_url_allowed(url) is False


@pytest.mark.parametrize("workspace_id", ["workspace-123", "A1", "abc123"])
def test_qwen_workspace_id_accepts_hostname_labels(workspace_id: str) -> None:
    """Workspace IDs that are valid hostname labels should be accepted."""
    assert config_mod.is_qwen_workspace_id_valid(workspace_id) is True


@pytest.mark.parametrize(
    "workspace_id",
    ["", "https://example.com", "bad/value", "-starts-with-dash", "ends-with-dash-"],
)
def test_qwen_workspace_id_rejects_unsafe_values(workspace_id: str) -> None:
    """URL-like or malformed workspace IDs should be rejected."""
    assert config_mod.is_qwen_workspace_id_valid(workspace_id) is False
