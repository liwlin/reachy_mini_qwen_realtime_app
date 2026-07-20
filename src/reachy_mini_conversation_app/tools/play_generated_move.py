"""Tool: replay (or list) moves previously invented with create_move."""

from __future__ import annotations
import logging
from typing import Any, Dict

from reachy_mini_conversation_app.generated_moves import GeneratedQueueMove
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.choreographer.store import load_move, list_moves


logger = logging.getLogger(__name__)


class PlayGeneratedMove(Tool):
    """Replay a move from the robot's self-made repertoire."""

    name = "play_generated_move"
    description = (
        "Replay a movement previously invented with create_move. "
        "Call without arguments to list the available generated moves and their descriptions."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the generated move to play; omit to list what exists.",
            },
        },
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Queue the named generated move, or list the repertoire."""
        name = str(kwargs.get("name") or "").strip()
        if not name:
            available = [
                {"name": meta.get("name"), "description": meta.get("description")}
                for meta in list_moves(deps.instance_path)
            ]
            return {"available_moves": available, "count": len(available)}

        try:
            move, meta = load_move(deps.instance_path, name)
        except FileNotFoundError:
            known = [str(meta.get("name")) for meta in list_moves(deps.instance_path)]
            return {"error": f"no generated move named '{name}'", "available_moves": known}

        logger.info("Tool call: play_generated_move name=%s", name)
        deps.movement_manager.queue_move(GeneratedQueueMove(move, name=name))
        return {"status": "queued", "name": name, "description": meta.get("description")}
