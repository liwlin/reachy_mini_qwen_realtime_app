"""Codegen LLM orchestration: brief -> source -> baked, validated trajectory.

The composer is a separate LLM API call (OpenAI-compatible; defaults to the
Hugging Face router so the app's existing HF token just works). The realtime
speech model only captures the user's brief - this module does the writing,
baking and validating, feeding violations back to the model for a bounded
number of repair attempts.
"""

from __future__ import annotations
import os
import asyncio
import logging
from typing import Any, Protocol
from dataclasses import dataclass

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.choreographer.bake import BakeError, bake_source
from reachy_mini_conversation_app.choreographer.limits import DEFAULT_LIMITS
from reachy_mini_conversation_app.choreographer.parsing import MoveHeader, ParseError, extract_move_source
from reachy_mini_conversation_app.choreographer.validator import validate_trajectory


logger = logging.getLogger(__name__)

DEFAULT_COMPOSER_MODEL = "Qwen/Qwen3-Coder-480B-A35B-Instruct"
DEFAULT_COMPOSER_BASE_URL = "https://router.huggingface.co/v1"
MAX_ATTEMPTS = 3
_REQUEST_TIMEOUT_S = 120.0
_MAX_COMPLETION_TOKENS = 4096

SYSTEM_PROMPT = """You are the choreographer of Reachy Mini, a small expressive robot: a 6-DOF head \
(x, y, z translation in meters; roll, pitch, yaw in radians) and two antennas (radians). \
You write short Python move functions that give the robot life: dances that lock to a beat, \
and emotion moves with narrative shape (anticipation, action, settle).

OUTPUT CONTRACT - reply with exactly one fenced ```python code block:
```python
# name: <short_snake_case_name>
# description: <one line>
# bpm: <beats per minute, 20-240>
# duration_beats: <total length in beats, 1-120>
def move(t_beats):
    ...
    return <MoveOffsets>
```
`move(t_beats)` is a PURE function of musical time in beats (t_beats = seconds * bpm / 60). \
It is sampled at 50 Hz; no loops over time, no I/O, no state between calls, no printing.

AVAILABLE VOCABULARY (already imported - do not import them):
- MoveOffsets(position_offset=np.array([x, y, z]), orientation_offset=np.array([roll, pitch, yaw]), \
antennas_offset=np.array([left, right])) - offsets from the neutral pose (meters / radians).
- OscillationParams(amplitude, subcycles_per_beat=1.0, phase_offset=0.0, waveform="sin") \
with waveform in {sin, cos, square, triangle, sawtooth}.
- TransientParams(amplitude, duration_in_beats=1.0, delay_beats=0.0, repeat_every=0.0) - a smoothstep \
pulse; NOTE it snaps back to 0 when it ends, so shape your own release if you need a smooth return.
- oscillation_motion(t_beats, params) -> float, transient_motion(t_beats, params) -> float.
- Per-channel helpers, each (t_beats, OscillationParams) -> MoveOffsets: atomic_x_pos, atomic_y_pos, \
atomic_z_pos, atomic_roll, atomic_pitch, atomic_yaw, atomic_antenna_wiggle (antiphase), \
atomic_antenna_both (in phase).
- combine_offsets([offsets, ...]) -> MoveOffsets sums them.
- `math` and `np`/`numpy` are available; writing your own phase/envelope/waypoint math is encouraged \
for staged, narrative moves (if/elif over beat ranges, eased segments, holds).

HARD SAFETY ENVELOPE (a validator rejects your code beyond these; stay comfortably inside):
- |x|, |y|, |z| <= 0.035 m; |roll|, |pitch| <= 0.44 rad (25 deg); |yaw| <= 0.87 rad (50 deg); \
|antennas| <= 1.4 rad (80 deg).
- Oscillation frequency per channel: subcycles_per_beat * bpm / 60 <= 3 Hz. No discontinuous jumps: \
square/sawtooth waveforms and instant transitions between segments create huge velocities - blend or \
keep their amplitude small (e.g. yaw square wave <= 0.15 rad).
- Head must move smoothly: translation <= 0.15 m/s, rotation <= 3 rad/s, antennas <= 7 rad/s.
- START AT NEUTRAL: move(0) must return (near-)zero offsets, and ending near neutral looks best.

STYLE NOTES:
- Antennas are the robot's eyebrows - use them for expressiveness (droop = sad/anxious, \
perky wiggle = joy, slow sway = calm).
- Emotions read best as 2-4 staged segments with easing (e.g. smoothstep s = 3*u**2 - 2*u**3) \
and asymmetry; dances read best as layered oscillators with frequency ratios and phase offsets.
- Secondary motion sells it: a small z bob under a yaw glance, a roll tilt with a pitch nod.

EXAMPLE (a groovy sway - layered oscillators):
```python
# name: groovy_sway
# description: relaxed side-to-side groove with rolling head and swinging antennas
# bpm: 100
# duration_beats: 8
def move(t_beats):
    sway = atomic_y_pos(t_beats, OscillationParams(amplitude=0.025, subcycles_per_beat=0.5))
    roll = atomic_roll(t_beats, OscillationParams(amplitude=0.2, subcycles_per_beat=0.5, phase_offset=0.25))
    bob = atomic_z_pos(t_beats, OscillationParams(amplitude=0.01, subcycles_per_beat=1.0))
    ears = atomic_antenna_wiggle(t_beats, OscillationParams(amplitude=0.6, subcycles_per_beat=0.5))
    return combine_offsets([sway, roll, bob, ears])
```

EXAMPLE (an emotion with narrative stages - custom math):
```python
# name: curious_peek
# description: lean in, tilt with perked antennas, then settle back
# bpm: 60
# duration_beats: 6
def move(t_beats):
    import math as _m
    def ease(u):
        u = max(0.0, min(1.0, u))
        return 3 * u**2 - 2 * u**3
    if t_beats < 1.5:  # lean forward, curious
        k = ease(t_beats / 1.5)
    elif t_beats < 4.0:  # hold with a tiny inquisitive wobble
        k = 1.0
    else:  # settle back to neutral
        k = 1.0 - ease((t_beats - 4.0) / 2.0)
    wobble = 0.05 * _m.sin(2 * _m.pi * 1.0 * t_beats) * (1.0 if 1.5 <= t_beats < 4.0 else 0.0)
    return MoveOffsets(
        position_offset=np.array([0.02 * k, 0.0, 0.005 * k]),
        orientation_offset=np.array([0.15 * k + wobble, -0.12 * k, 0.25 * k]),
        antennas_offset=np.array([0.9 * k, 0.5 * k]),
    )
```
"""


class ChatClient(Protocol):
    """Minimal protocol for the OpenAI-compatible client the composer needs."""

    @property
    def chat(self) -> Any:  # pragma: no cover - structural typing only
        """Chat completions namespace."""
        ...


class MoveComposerError(RuntimeError):
    """Raised when no valid move could be produced within the attempt budget."""


@dataclass(frozen=True)
class ComposedMove:
    """A generated move that passed baking and validation."""

    name: str
    description: str
    bpm: float
    duration_beats: float
    source: str
    move: dict[str, Any]  # RecordedMove-shaped trajectory
    model: str
    attempts: int


def _resolve_api_key() -> str | None:
    """Composer API key: explicit env var, then the app's HF token, then hf auth login."""
    explicit = (os.getenv("MOVE_COMPOSER_API_KEY") or "").strip()
    if explicit:
        return explicit
    if config.HF_TOKEN:
        return str(config.HF_TOKEN)
    try:
        from huggingface_hub import get_token

        return get_token()
    except Exception:  # pragma: no cover - hub always present in practice
        return None


def build_default_client() -> Any:
    """Create the AsyncOpenAI client for the configured composer endpoint."""
    from openai import AsyncOpenAI

    api_key = _resolve_api_key()
    if not api_key:
        raise MoveComposerError(
            "no API key for the move composer: set MOVE_COMPOSER_API_KEY or HF_TOKEN (or run `hf auth login`)"
        )
    base_url = (os.getenv("MOVE_COMPOSER_BASE_URL") or "").strip() or DEFAULT_COMPOSER_BASE_URL
    return AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=_REQUEST_TIMEOUT_S)


def composer_model() -> str:
    """Model id used for move generation."""
    return (os.getenv("MOVE_COMPOSER_MODEL") or "").strip() or DEFAULT_COMPOSER_MODEL


def _user_prompt(brief: str, kind: str, duration_hint_beats: float | None) -> str:
    """Build the initial user message from the captured brief."""
    lines = [f"Create a new {kind} move for the robot.", f"Brief: {brief}"]
    if duration_hint_beats:
        lines.append(f"Aim for roughly {duration_hint_beats:g} beats.")
    lines.append("Reply with the single ```python code block only.")
    return "\n".join(lines)


class MoveComposer:
    """Turns a natural-language brief into a validated, playable trajectory."""

    def __init__(self, client: Any | None = None, model: str | None = None) -> None:
        """Create a composer; `client` and `model` are injectable for tests."""
        self._client = client
        self._model = model or composer_model()

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = build_default_client()
        return self._client

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        response = await self._get_client().chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=_MAX_COMPLETION_TOKENS,
        )
        content = response.choices[0].message.content
        if not content:
            raise MoveComposerError("composer model returned an empty reply")
        return str(content)

    async def compose(
        self,
        brief: str,
        *,
        kind: str = "emotion",
        duration_hint_beats: float | None = None,
    ) -> ComposedMove:
        """Generate, bake and validate a move; retry with feedback on failure."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(brief, kind, duration_hint_beats)},
        ]
        last_failure = "no attempt made"

        for attempt in range(1, MAX_ATTEMPTS + 1):
            reply = await self._complete(messages)
            try:
                header, source = extract_move_source(reply)
                move = await asyncio.to_thread(
                    bake_source,
                    source,
                    bpm=header.bpm,
                    duration_beats=header.duration_beats,
                )
                violations = validate_trajectory(move, DEFAULT_LIMITS)
                if violations:
                    raise _ValidationFailed(violations)
            except (ParseError, BakeError, _ValidationFailed) as error:
                last_failure = _feedback_for(error)
                logger.warning("Move attempt %d/%d failed: %s", attempt, MAX_ATTEMPTS, last_failure)
                messages.append({"role": "assistant", "content": reply})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"That attempt failed:\n{last_failure}\n"
                            "Fix these exact problems and reply with the corrected single ```python block."
                        ),
                    }
                )
                continue

            logger.info("Composed move '%s' in %d attempt(s)", header.name, attempt)
            return ComposedMove(
                name=header.name,
                description=header.description,
                bpm=header.bpm,
                duration_beats=header.duration_beats,
                source=source,
                move=_with_description(move, header),
                model=self._model,
                attempts=attempt,
            )

        raise MoveComposerError(
            f"could not produce a valid move after {MAX_ATTEMPTS} attempts; last failure: {last_failure}"
        )


class _ValidationFailed(Exception):
    """Internal: carries validator violations through the retry loop."""

    def __init__(self, violations: list[str]) -> None:
        super().__init__("; ".join(violations))
        self.violations = violations


def _feedback_for(error: Exception) -> str:
    """Render a failure as actionable feedback for the model."""
    if isinstance(error, _ValidationFailed):
        return "safety validator rejected the trajectory:\n- " + "\n- ".join(error.violations)
    return str(error)


def _with_description(move: dict[str, Any], header: MoveHeader) -> dict[str, Any]:
    """Stamp the RecordedMove 'description' field expected by the SDK parser."""
    move["description"] = header.description
    return move
