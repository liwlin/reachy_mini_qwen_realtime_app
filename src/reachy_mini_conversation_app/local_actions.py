"""Allowlisted actions exposed to the local mobile controller."""

import json
import logging

from reachy_mini_conversation_app.tools.core_tools import ToolDependencies, dispatch_tool_call


logger = logging.getLogger(__name__)

_ACTION_DEFINITIONS: dict[str, tuple[str, str, str, dict[str, object]]] = {
    "look_left": ("Look left", "head", "move_head", {"direction": "left"}),
    "look_right": ("Look right", "head", "move_head", {"direction": "right"}),
    "look_up": ("Look up", "head", "move_head", {"direction": "up"}),
    "look_down": ("Look down", "head", "move_head", {"direction": "down"}),
    "look_front": ("Look front", "head", "move_head", {"direction": "front"}),
    "nod_yes": ("Nod yes", "gesture", "play_emotion", {"emotion": "yes"}),
    "shake_no": ("Shake no", "gesture", "play_emotion", {"emotion": "no"}),
    "welcome": ("Welcome", "emotion", "play_emotion", {"emotion": "welcoming"}),
    "happy": ("Happy", "emotion", "play_emotion", {"emotion": "happy"}),
    "dance": ("Dance", "dance", "dance", {"repeat": 1}),
}


def list_local_actions() -> list[dict[str, str]]:
    """Return stable metadata for every phone-safe action."""
    return [
        {"name": name, "label": label, "category": category}
        for name, (label, category, _tool_name, _arguments) in _ACTION_DEFINITIONS.items()
    ]


async def execute_local_action(name: str, deps: ToolDependencies) -> dict[str, object]:
    """Dispatch one phone-safe action through the active Qwen tool registry."""
    action = _ACTION_DEFINITIONS.get(name)
    if action is None:
        return {"error": "unknown_action"}
    _label, _category, tool_name, arguments = action
    logger.info("Local control action: %s", name)
    result = await dispatch_tool_call(
        tool_name=tool_name,
        args_json=json.dumps(arguments),
        deps=deps,
    )
    return dict(result)


def stop_local_actions(deps: ToolDependencies) -> dict[str, str]:
    """Clear queued motion through the active Qwen movement manager."""
    logger.info("Local control action: stop")
    deps.movement_manager.clear_move_queue()
    return {"status": "stopped"}
