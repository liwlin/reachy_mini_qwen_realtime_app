"""Tests for configuration helpers."""

import pytest

from reachy_mini_conversation_app import config


@pytest.mark.parametrize(
    "raw_value, expected",
    [
        ("45", 45.0),
        ("", config.DEFAULT_APP_TIMEOUT_MINUTES),  # unset/blank falls back to the default
        ("soon", config.DEFAULT_APP_TIMEOUT_MINUTES),  # unparseable falls back to the default
        ("0", None),  # non-positive disables the watchdog
        ("-1", None),
    ],
)
def test_resolve_app_timeout_minutes(monkeypatch, raw_value, expected) -> None:
    """The env timeout parses to minutes, falls back to the default, or disables on non-positive."""
    monkeypatch.setenv(config.APP_TIMEOUT_MINUTES_ENV, raw_value)

    assert config.resolve_app_timeout_minutes() == expected


def test_realtime_backend_defaults_to_huggingface(monkeypatch) -> None:
    """The existing Hugging Face backend remains the default."""
    monkeypatch.delenv(config.REALTIME_BACKEND_ENV, raising=False)
    config.refresh_runtime_config_from_env()

    assert config.get_realtime_backend() == config.HF_BACKEND


def test_qwen_backend_resolves_workspace_url_and_voices(monkeypatch) -> None:
    """Qwen settings resolve an authorized endpoint and provider voices."""
    monkeypatch.setenv(config.REALTIME_BACKEND_ENV, config.QWEN_BACKEND)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setenv("QWEN_WORKSPACE_ID", "workspace-test")
    monkeypatch.setenv("QWEN_REGION", "ap-southeast-1")
    monkeypatch.setenv("QWEN_MODEL_NAME", "qwen3.5-omni-flash-realtime")
    config.refresh_runtime_config_from_env()

    assert config.get_realtime_backend() == config.QWEN_BACKEND
    assert config.has_realtime_target() is True
    assert config.get_default_voice() == "Tina"
    assert "Tina" in config.get_available_voices()
    assert config.get_qwen_realtime_url() == (
        "wss://workspace-test.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime?model=qwen3.5-omni-flash-realtime"
    )


def test_qwen_backend_rejects_untrusted_full_url(monkeypatch) -> None:
    """Qwen readiness rejects endpoints outside the Alibaba allowlist."""
    monkeypatch.setattr(config.config, "REALTIME_BACKEND", config.QWEN_BACKEND)
    monkeypatch.setattr(config.config, "QWEN_API_KEY", "test-key")
    monkeypatch.setattr(config.config, "QWEN_REALTIME_URL", "wss://attacker.example/api-ws/v1/realtime")
    monkeypatch.setattr(config.config, "QWEN_WORKSPACE_ID", None)

    assert config.has_realtime_target() is False
