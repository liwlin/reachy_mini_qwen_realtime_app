"""Tests for the move composer (LLM mocked, baking real)."""

from types import SimpleNamespace

import pytest

from reachy_mini_conversation_app.choreographer.composer import MAX_ATTEMPTS, MoveComposer, MoveComposerError

GOOD_REPLY = """```python
# name: gentle_nod
# description: a gentle nod
# bpm: 120
# duration_beats: 4
def move(t_beats):
    return atomic_pitch(t_beats, OscillationParams(amplitude=0.15, subcycles_per_beat=1.0))
```"""

# 0.9 rad pitch amplitude: bakes fine, must be rejected by the validator.
UNSAFE_REPLY = GOOD_REPLY.replace("amplitude=0.15", "amplitude=0.9")

BROKEN_REPLY = """```python
# name: broken
# description: syntax error
# bpm: 120
# duration_beats: 4
def move(t_beats)
    return None
```"""


class FakeClient:
    """OpenAI-compatible stub returning scripted replies and recording messages."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        completions = SimpleNamespace(create=self._create)
        self.chat = SimpleNamespace(completions=completions)

    async def _create(self, *, model, messages, **kwargs):
        self.calls.append(list(messages))
        content = self.replies.pop(0)
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


@pytest.mark.asyncio
async def test_happy_path_single_attempt():
    composer = MoveComposer(client=FakeClient([GOOD_REPLY]), model="test-model")
    composed = await composer.compose("nod gently", kind="emotion")
    assert composed.name == "gentle_nod"
    assert composed.attempts == 1
    assert composed.move["description"] == "a gentle nod"
    assert len(composed.move["time"]) == 101  # 4 beats @ 120 bpm = 2 s @ 50 fps


@pytest.mark.asyncio
async def test_validator_failure_feeds_back_and_retries():
    client = FakeClient([UNSAFE_REPLY, GOOD_REPLY])
    composer = MoveComposer(client=client, model="test-model")
    composed = await composer.compose("nod")
    assert composed.attempts == 2
    retry_messages = client.calls[1]
    assert retry_messages[-1]["role"] == "user"
    assert "safety validator rejected" in retry_messages[-1]["content"]
    assert "head pitch" in retry_messages[-1]["content"]


@pytest.mark.asyncio
async def test_bake_failure_feeds_back_and_retries():
    client = FakeClient([BROKEN_REPLY, GOOD_REPLY])
    composer = MoveComposer(client=client, model="test-model")
    composed = await composer.compose("nod")
    assert composed.attempts == 2
    assert "SyntaxError" in client.calls[1][-1]["content"]


@pytest.mark.asyncio
async def test_attempt_budget_exhausted_raises():
    client = FakeClient([BROKEN_REPLY] * MAX_ATTEMPTS)
    composer = MoveComposer(client=client, model="test-model")
    with pytest.raises(MoveComposerError, match="after 3 attempts"):
        await composer.compose("nod")


@pytest.mark.asyncio
async def test_empty_reply_raises():
    client = FakeClient([None])
    composer = MoveComposer(client=client, model="test-model")
    with pytest.raises(MoveComposerError, match="empty reply"):
        await composer.compose("nod")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
