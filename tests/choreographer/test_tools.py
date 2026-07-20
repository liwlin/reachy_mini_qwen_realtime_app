"""Tests for the create_move / play_generated_move tools."""

from types import SimpleNamespace

import pytest

from reachy_mini_conversation_app.tools import create_move as create_move_module
from reachy_mini_conversation_app.tools.create_move import CreateMove
from reachy_mini_conversation_app.choreographer.store import save_move
from reachy_mini_conversation_app.choreographer.composer import ComposedMove, MoveComposerError
from reachy_mini_conversation_app.tools.play_generated_move import PlayGeneratedMove


class FakeMovementManager:
    """Test double: FakeMovementManager."""

    def __init__(self):
        """Initialize the test double."""
        self.queued = []

    def queue_move(self, move):
        """Queue move."""
        self.queued.append(move)


class FakeMedia:
    """Test double: FakeMedia."""

    def __init__(self):
        """Initialize the test double."""
        self.played = []

    def play_sound(self, sound_file):
        """Play sound."""
        self.played.append(sound_file)


def make_deps(tmp_path):
    """Make deps."""
    return SimpleNamespace(
        reachy_mini=SimpleNamespace(media=FakeMedia()),
        movement_manager=FakeMovementManager(),
        instance_path=tmp_path,
    )


def make_composed(move_dict, name="proud_strut"):
    """Make composed."""
    return ComposedMove(
        name=name,
        description="a proud strut",
        bpm=120,
        duration_beats=4,
        source="def move(t_beats):\n    ...\n",
        move=move_dict,
        model="test-model",
        attempts=1,
    )


class FakeComposer:
    """Test double: FakeComposer."""

    def __init__(self, result=None, error=None):
        """Initialize the test double."""
        self._result = result
        self._error = error

    async def compose(self, brief, *, kind="emotion", duration_hint_beats=None):
        """Compose."""
        if self._error:
            raise self._error
        return self._result


@pytest.mark.asyncio
async def test_create_move_success_saves_chimes_and_queues(tmp_path, monkeypatch, make_move):
    """Check create move success saves chimes and queues."""
    deps = make_deps(tmp_path)
    monkeypatch.setattr(
        create_move_module, "MoveComposer", lambda: FakeComposer(result=make_composed(make_move(duration_s=2.0)))
    )

    result = await CreateMove()(deps, brief="strut proudly", kind="emotion")

    assert result["status"] == "ready"
    assert result["name"] == "proud_strut"
    assert result["playing_now"] is True
    assert len(deps.movement_manager.queued) == 1
    assert deps.reachy_mini.media.played and deps.reachy_mini.media.played[0].endswith("move_ready.wav")
    assert (tmp_path / "generated_moves" / "proud_strut" / "move.json").exists()


@pytest.mark.asyncio
async def test_create_move_play_false_does_not_queue(tmp_path, monkeypatch, make_move):
    """Check create move play false does not queue."""
    deps = make_deps(tmp_path)
    monkeypatch.setattr(
        create_move_module, "MoveComposer", lambda: FakeComposer(result=make_composed(make_move(duration_s=2.0)))
    )

    result = await CreateMove()(deps, brief="strut", play=False)

    assert result["playing_now"] is False
    assert deps.movement_manager.queued == []


@pytest.mark.asyncio
async def test_create_move_reports_composer_failure(tmp_path, monkeypatch):
    """Check create move reports composer failure."""
    deps = make_deps(tmp_path)
    monkeypatch.setattr(
        create_move_module,
        "MoveComposer",
        lambda: FakeComposer(error=MoveComposerError("no valid move")),
    )

    result = await CreateMove()(deps, brief="impossible move")

    assert "move creation failed" in result["error"]
    assert deps.movement_manager.queued == []


@pytest.mark.asyncio
async def test_create_move_requires_brief(tmp_path):
    """Check create move requires brief."""
    result = await CreateMove()(make_deps(tmp_path), brief="   ")
    assert "error" in result


@pytest.mark.asyncio
async def test_play_generated_move_lists_when_no_name(tmp_path, make_move):
    """Check play generated move lists when no name."""
    deps = make_deps(tmp_path)
    save_move(tmp_path, make_composed(make_move(duration_s=2.0), "happy_hop"), brief="hop happily")

    result = await PlayGeneratedMove()(deps)

    assert result["count"] == 1
    assert result["available_moves"][0]["name"] == "happy_hop"


@pytest.mark.asyncio
async def test_play_generated_move_queues_saved_move(tmp_path, make_move):
    """Check play generated move queues saved move."""
    deps = make_deps(tmp_path)
    save_move(tmp_path, make_composed(make_move(duration_s=2.0), "happy_hop"), brief="hop")

    result = await PlayGeneratedMove()(deps, name="happy_hop")

    assert result["status"] == "queued"
    assert len(deps.movement_manager.queued) == 1


@pytest.mark.asyncio
async def test_play_generated_move_unknown_name(tmp_path):
    """Check play generated move unknown name."""
    result = await PlayGeneratedMove()(make_deps(tmp_path), name="ghost")
    assert "no generated move" in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
