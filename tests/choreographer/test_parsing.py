"""Tests for LLM reply parsing."""

import pytest

from reachy_mini_conversation_app.choreographer.parsing import ParseError, extract_move_source, slugify

GOOD_REPLY = '''Here is your move!

```python
# name: Anxious Glance!
# description: quick nervous side glances
# bpm: 100
# duration_beats: 12
def move(t_beats):
    return atomic_yaw(t_beats, OscillationParams(amplitude=0.3))
```
'''


def test_good_reply_parses():
    header, source = extract_move_source(GOOD_REPLY)
    assert header.name == "anxious_glance"
    assert header.bpm == 100
    assert header.duration_beats == 12
    assert "def move(t_beats):" in source


def test_last_code_block_wins():
    reply = "```python\nx = 1\n```\n" + GOOD_REPLY
    header, source = extract_move_source(reply)
    assert header.name == "anxious_glance"
    assert "x = 1" not in source


def test_no_code_block_rejected():
    with pytest.raises(ParseError, match="code block"):
        extract_move_source("sorry, I cannot do that")


def test_missing_header_rejected():
    reply = "```python\ndef move(t_beats):\n    return None\n```"
    with pytest.raises(ParseError, match="missing header"):
        extract_move_source(reply)


def test_missing_move_function_rejected():
    reply = "```python\n# name: a\n# description: b\n# bpm: 100\n# duration_beats: 4\nx = 1\n```"
    with pytest.raises(ParseError, match="def move"):
        extract_move_source(reply)


def test_out_of_range_bpm_rejected():
    reply = GOOD_REPLY.replace("# bpm: 100", "# bpm: 999")
    with pytest.raises(ParseError, match="out of range"):
        extract_move_source(reply)


def test_unfenced_block_rejected():
    with pytest.raises(ParseError):
        extract_move_source("# name: a\ndef move(t_beats):\n    return None")


def test_slugify():
    assert slugify("Robot's Happy Dance #2") == "robot_s_happy_dance_2"
    assert slugify("---") == "unnamed_move"
    assert len(slugify("x" * 200)) <= 48


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
