"""Allowlisted mobile-action tests."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import reachy_mini_conversation_app.local_actions as local_actions


@pytest.mark.parametrize(
    ("action", "tool_name", "arguments"),
    [
        ("look_left", "move_head", {"direction": "left"}),
        ("look_right", "move_head", {"direction": "right"}),
        ("look_up", "move_head", {"direction": "up"}),
        ("look_down", "move_head", {"direction": "down"}),
        ("look_front", "move_head", {"direction": "front"}),
        ("nod_yes", "play_emotion", {"emotion": "yes"}),
        ("shake_no", "play_emotion", {"emotion": "no"}),
        ("welcome", "play_emotion", {"emotion": "welcoming"}),
        ("happy", "play_emotion", {"emotion": "happy"}),
        ("dance", "dance", {"repeat": 1}),
    ],
)
@pytest.mark.asyncio
async def test_execute_local_action_dispatches_fixed_tool_arguments(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    """Every mobile action maps to one immutable tool call."""
    dispatch = AsyncMock(return_value={"status": "queued"})
    monkeypatch.setattr(local_actions, "dispatch_tool_call", dispatch)
    deps = MagicMock()

    result = await local_actions.execute_local_action(action, deps)

    assert result == {"status": "queued"}
    dispatch.assert_awaited_once()
    assert dispatch.await_args.kwargs["tool_name"] == tool_name
    assert json.loads(dispatch.await_args.kwargs["args_json"]) == arguments
    assert dispatch.await_args.kwargs["deps"] is deps


@pytest.mark.asyncio
async def test_execute_local_action_rejects_unknown_name_without_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phone input cannot select arbitrary tools or arguments."""
    dispatch = AsyncMock()
    monkeypatch.setattr(local_actions, "dispatch_tool_call", dispatch)

    result = await local_actions.execute_local_action("run_shell", MagicMock())

    assert result == {"error": "unknown_action"}
    dispatch.assert_not_awaited()


def test_list_local_actions_returns_stable_public_metadata() -> None:
    """The UI receives labels and names without tool implementation details."""
    actions = local_actions.list_local_actions()

    assert [item["name"] for item in actions] == [
        "look_left",
        "look_right",
        "look_up",
        "look_down",
        "look_front",
        "nod_yes",
        "shake_no",
        "welcome",
        "happy",
        "dance",
    ]
    assert all(set(item) == {"name", "label", "category"} for item in actions)


def test_stop_local_actions_clears_the_shared_movement_queue() -> None:
    """The phone stop action targets the same movement manager Qwen uses."""
    movement_manager = MagicMock()
    deps = MagicMock(movement_manager=movement_manager)

    result = local_actions.stop_local_actions(deps)

    movement_manager.clear_move_queue.assert_called_once_with()
    assert result == {"status": "stopped"}
