"""Browser-safe catalog definitions for local mobile control."""

import re
from typing import Literal
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SAFE_REPOSITORY_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_LOCAL_UI_HOSTS = frozenset({"0.0.0.0", "127.0.0.1", "localhost", "::"})


@dataclass(frozen=True)
class MotionSourceDefinition:
    """Describe one fixed recorded-move source exposed to the browser."""

    source_id: str
    dataset: str
    category: Literal["emotion", "dance"]
    label: str
    expected_names: tuple[str, ...] = ()


MUSIC_DANCE_NAMES: tuple[str, ...] = (
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


MOTION_SOURCES: dict[str, MotionSourceDefinition] = {
    "emotion": MotionSourceDefinition(
        source_id="emotion",
        dataset="pollen-robotics/reachy-mini-emotions-library",
        category="emotion",
        label="表情",
    ),
    "pollen_dance": MotionSourceDefinition(
        source_id="pollen_dance",
        dataset="pollen-robotics/reachy-mini-dances-library",
        category="dance",
        label="官方舞蹈",
    ),
    "music_dance": MotionSourceDefinition(
        source_id="music_dance",
        dataset="Anne-Charlotte/music",
        category="dance",
        label="音乐舞蹈",
        expected_names=MUSIC_DANCE_NAMES,
    ),
}


def humanize_move_name(name: str) -> str:
    """Create a readable label without altering the raw playback identifier."""
    separated = re.sub(r"[-_]+", " ", name).strip()
    return re.sub(r"(?<=\D)(\d+)$", r" \1", separated)


def hf_dataset_cache_path(repo_id: str, cache_root: Path) -> Path:
    """Return the standard Hugging Face cache directory for one dataset ID."""
    segments = repo_id.split("/")
    if len(segments) != 2 or any(
        segment in {"", ".", ".."} or _SAFE_REPOSITORY_SEGMENT.fullmatch(segment) is None for segment in segments
    ):
        raise ValueError("invalid_dataset_id")
    return cache_root / f"datasets--{segments[0]}--{segments[1]}"


def sanitize_installed_app(raw: dict[str, object], current_name: str | None) -> dict[str, object]:
    """Return only display and local-navigation metadata for an installed app."""
    name = raw.get("name")
    if not isinstance(name, str) or _SAFE_IDENTIFIER.fullmatch(name) is None:
        raise ValueError("invalid_app_catalog_entry")

    extra = raw.get("extra")
    extra_mapping = extra if isinstance(extra, dict) else {}
    card_data = extra_mapping.get("cardData")
    card_mapping = card_data if isinstance(card_data, dict) else {}

    title = card_mapping.get("title")
    if not isinstance(title, str) or not title.strip():
        title = humanize_move_name(name).title()
    emoji = card_mapping.get("emoji")
    if not isinstance(emoji, str) or not emoji.strip():
        emoji = "📦"

    result: dict[str, object] = {
        "name": name,
        "title": title.strip(),
        "emoji": emoji.strip(),
        "active": name == current_name,
    }
    custom_url = extra_mapping.get("custom_app_url")
    if isinstance(custom_url, str):
        parsed = urlsplit(custom_url)
        try:
            port = parsed.port
        except ValueError:
            port = None
        if parsed.scheme in {"http", "https"} and parsed.hostname in _LOCAL_UI_HOSTS and port is not None:
            result["custom_ui_port"] = port
    return result
