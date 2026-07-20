"""Tests for the generated-moves store."""

import pytest

from reachy_mini_conversation_app.choreographer.store import list_moves, load_move, save_move
from reachy_mini_conversation_app.choreographer.composer import ComposedMove


def composed(name="test_move"):
    return ComposedMove(
        name=name,
        description="a test move",
        bpm=120,
        duration_beats=4,
        source="def move(t_beats):\n    return None\n",
        move={"description": "a test move", "time": [0.0, 0.02], "set_target_data": [{}, {}]},
        model="test-model",
        attempts=1,
    )


def test_save_load_roundtrip(tmp_path):
    name, move_dir = save_move(tmp_path, composed(), brief="do a test")
    assert name == "test_move"
    assert (move_dir / "source.py").exists()
    move, meta = load_move(tmp_path, name)
    assert move["time"] == [0.0, 0.02]
    assert meta["brief"] == "do a test"
    assert meta["model"] == "test-model"


def test_name_collision_gets_suffix(tmp_path):
    assert save_move(tmp_path, composed(), brief="b")[0] == "test_move"
    assert save_move(tmp_path, composed(), brief="b")[0] == "test_move_2"
    assert save_move(tmp_path, composed(), brief="b")[0] == "test_move_3"


def test_list_moves_most_recent_first(tmp_path):
    save_move(tmp_path, composed("first"), brief="b")
    save_move(tmp_path, composed("second"), brief="b")
    names = [meta["name"] for meta in list_moves(tmp_path)]
    assert names == ["second", "first"]


def test_list_moves_empty_when_missing(tmp_path):
    assert list_moves(tmp_path / "nothing_here") == []


def test_load_missing_move_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_move(tmp_path, "ghost")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
