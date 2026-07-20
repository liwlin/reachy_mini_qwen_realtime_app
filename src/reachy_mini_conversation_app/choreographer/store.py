"""On-disk repertoire of generated moves (trajectory + source + provenance).

Layout mirrors the memory feature's storage convention: one directory per move
under ``<instance>/generated_moves/`` (or the XDG data dir when the app runs
without an instance path), containing ``move.json`` (baked RecordedMove data),
``source.py`` (the generated code, kept for inspection/retiming) and
``meta.json`` (provenance).
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from reachy_mini_conversation_app.choreographer.composer import ComposedMove

logger = logging.getLogger(__name__)

GENERATED_MOVES_DIRNAME = "generated_moves"


def moves_dir_for_instance(instance_path: str | Path | None = None) -> Path:
    """Return the generated-moves root for this app instance."""
    if instance_path is not None:
        return Path(instance_path).expanduser() / GENERATED_MOVES_DIRNAME

    data_home = os.getenv("XDG_DATA_HOME")
    data_root = Path(data_home).expanduser() if data_home else Path.home() / ".local" / "share"
    return data_root / "reachy_mini_conversation_app" / GENERATED_MOVES_DIRNAME


def _unique_slug(root: Path, name: str) -> str:
    """Return `name`, or `name_2`, `name_3`, ... if already taken."""
    if not (root / name).exists():
        return name
    suffix = 2
    while (root / f"{name}_{suffix}").exists():
        suffix += 1
    return f"{name}_{suffix}"


def save_move(instance_path: str | Path | None, composed: ComposedMove, brief: str) -> tuple[str, Path]:
    """Persist a composed move; returns its (possibly suffixed) name and directory."""
    root = moves_dir_for_instance(instance_path)
    root.mkdir(parents=True, exist_ok=True)
    name = _unique_slug(root, composed.name)
    move_dir = root / name
    move_dir.mkdir()

    meta = {
        "name": name,
        "description": composed.description,
        "brief": brief,
        "bpm": composed.bpm,
        "duration_beats": composed.duration_beats,
        "model": composed.model,
        "attempts": composed.attempts,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (move_dir / "move.json").write_text(json.dumps(composed.move), encoding="utf-8")
    (move_dir / "source.py").write_text(composed.source, encoding="utf-8")
    (move_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.info("Saved generated move '%s' to %s", name, move_dir)
    return name, move_dir


def load_move(instance_path: str | Path | None, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load a saved move's trajectory and metadata by name.

    Raises FileNotFoundError when the move does not exist.
    """
    move_dir = moves_dir_for_instance(instance_path) / name
    move: dict[str, Any] = json.loads((move_dir / "move.json").read_text(encoding="utf-8"))
    meta: dict[str, Any] = json.loads((move_dir / "meta.json").read_text(encoding="utf-8"))
    return move, meta


def list_moves(instance_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return saved moves' metadata, most recent first."""
    root = moves_dir_for_instance(instance_path)
    if not root.is_dir():
        return []
    metas: list[dict[str, Any]] = []
    for meta_file in root.glob("*/meta.json"):
        try:
            metas.append(json.loads(meta_file.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Skipping unreadable move metadata %s: %s", meta_file, error)
    metas.sort(key=lambda meta: str(meta.get("created_at", "")), reverse=True)
    return metas
