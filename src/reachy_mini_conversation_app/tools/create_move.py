"""Tool: invent a brand-new movement from a natural-language brief."""

from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict

from reachy_mini_conversation_app import sounds
from reachy_mini_conversation_app.generated_moves import GeneratedQueueMove
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.choreographer.store import save_move
from reachy_mini_conversation_app.choreographer.composer import MoveComposer, MoveComposerError

logger = logging.getLogger(__name__)

READY_CHIME = "move_ready.wav"


class CreateMove(Tool):
    """Compose, validate and perform a new move written by a codegen LLM."""

    name = "create_move"
    description = (
        "Invent a NEW movement for the robot (an emotion or a dance) from a description, "
        "when no existing dance/emotion fits or the user explicitly asks you to create/invent one. "
        "Slow: takes up to a minute, so tell the user you are working on it BEFORE calling this, "
        "then continue chatting normally. When the move is ready it plays automatically and you "
        "will receive its name and description."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "brief": {
                "type": "string",
                "description": (
                    "Rich natural-language description of the desired movement: mood, story, "
                    "intensity, rhythm, anything the user said about how it should look."
                ),
            },
            "kind": {
                "type": "string",
                "enum": ["emotion", "dance"],
                "description": "Whether this is an expressive emotion move or a rhythmic dance.",
            },
            "duration_beats": {
                "type": "number",
                "description": "Optional approximate length in musical beats (typical: 4-16).",
            },
            "play": {
                "type": "boolean",
                "description": "Play the move immediately once ready (default true).",
            },
        },
        "required": ["brief"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Compose the move, persist it, chime, and queue it for playback."""
        brief = str(kwargs.get("brief") or "").strip()
        if not brief:
            return {"error": "brief is required"}
        kind = kwargs.get("kind") or "emotion"
        duration_hint = kwargs.get("duration_beats")
        play = kwargs.get("play", True)

        logger.info("Tool call: create_move kind=%s brief=%r", kind, brief)
        try:
            composed = await MoveComposer().compose(
                brief,
                kind=str(kind),
                duration_hint_beats=float(duration_hint) if duration_hint else None,
            )
        except MoveComposerError as error:
            return {"error": f"move creation failed: {error}"}

        name, move_dir = save_move(deps.instance_path, composed, brief)
        logger.info("Generated move '%s' saved to %s", name, move_dir)

        try:
            await asyncio.to_thread(sounds.play, deps.reachy_mini.media, READY_CHIME)
        except Exception as error:
            logger.warning("Could not play ready chime: %s", error)

        duration_s = composed.duration_beats * 60.0 / composed.bpm
        if play:
            deps.movement_manager.queue_move(GeneratedQueueMove(composed.move, name=name))

        return {
            "status": "ready",
            "name": name,
            "description": composed.description,
            "duration_s": round(duration_s, 1),
            "attempts": composed.attempts,
            "playing_now": bool(play),
            "note": "replay it anytime with play_generated_move",
        }
