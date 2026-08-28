"""Behavioral tests for browser-safe app and motion catalogs."""

from pathlib import Path

import pytest

from reachy_mini_conversation_app.local_control.catalogs import (
    MOTION_SOURCES,
    MUSIC_DANCE_NAMES,
    humanize_move_name,
    hf_dataset_cache_path,
    sanitize_installed_app,
)


def test_motion_sources_keep_browser_ids_inside_fixed_datasets() -> None:
    """A browser source ID can never become an arbitrary repository path."""
    assert set(MOTION_SOURCES) == {"emotion", "pollen_dance", "music_dance"}
    assert MOTION_SOURCES["emotion"].dataset == "pollen-robotics/reachy-mini-emotions-library"
    assert MOTION_SOURCES["pollen_dance"].dataset == "pollen-robotics/reachy-mini-dances-library"
    assert MOTION_SOURCES["music_dance"].dataset == "Anne-Charlotte/music"
    with pytest.raises(KeyError):
        _ = MOTION_SOURCES["../../private"]


def test_music_dance_catalog_matches_the_official_fourteen_moves() -> None:
    """The optional source exposes the official desktop-app catalog exactly once."""
    assert MUSIC_DANCE_NAMES == (
        "beyonce-single-ladies",
        "demon-hunters-1",
        "eagles-hotel-california",
        "eminem-lose-yourself",
        "feel-the-magic-in-the-air",
        "katy-perry-fireworks",
        "las-ketchup",
        "michael-jackson-thriller",
        "paint-it-black",
        "pharrell-williams-happy",
        "queen-we-will-rock-you",
        "spice-girls",
        "the-fratellis-whistle-for-the-choir",
        "the-white-stripes-seven-nation-army",
    )


def test_installed_app_response_drops_private_and_remote_metadata() -> None:
    """The phone receives display data, not venv paths or remote URLs."""
    raw: dict[str, object] = {
        "name": "coding_lab",
        "source_kind": "installed",
        "description": "",
        "url": None,
        "extra": {
            "venv_path": "/private/apps_venv",
            "id": "private/repository",
            "custom_app_url": "http://0.0.0.0:8042",
            "cardData": {"title": "Reachy Mini Coding Lab", "emoji": "🧪"},
        },
    }

    assert sanitize_installed_app(raw, "coding_lab") == {
        "name": "coding_lab",
        "title": "Reachy Mini Coding Lab",
        "emoji": "🧪",
        "active": True,
        "custom_ui_port": 8042,
    }


def test_installed_app_rejects_nonlocal_custom_ui_and_malformed_entries() -> None:
    """A catalog entry cannot turn the local page into an external redirect."""
    remote = {
        "name": "remote_app",
        "source_kind": "installed",
        "extra": {
            "custom_app_url": "https://example.invalid:8042/private",
            "cardData": {"title": "Remote", "emoji": "🌐"},
        },
    }
    sanitized = sanitize_installed_app(remote, None)
    assert sanitized == {"name": "remote_app", "title": "Remote", "emoji": "🌐", "active": False}

    with pytest.raises(ValueError, match="invalid_app_catalog_entry"):
        sanitize_installed_app({"name": "../escape", "source_kind": "installed", "extra": {}}, None)


def test_hf_dataset_cache_path_matches_hub_layout_and_rejects_traversal(tmp_path: Path) -> None:
    """Cache probing stays below the configured Hugging Face Hub cache root."""
    assert hf_dataset_cache_path("Anne-Charlotte/music", tmp_path) == tmp_path / "datasets--Anne-Charlotte--music"
    with pytest.raises(ValueError, match="invalid_dataset_id"):
        hf_dataset_cache_path("Anne-Charlotte/../private", tmp_path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("head_tilt_roll", "head tilt roll"),
        ("michael-jackson-thriller", "michael jackson thriller"),
        ("loving1", "loving 1"),
    ],
)
def test_move_labels_are_readable_without_changing_playback_ids(raw: str, expected: str) -> None:
    """Phone labels normalize separators while playback retains the raw ID."""
    assert humanize_move_name(raw) == expected
