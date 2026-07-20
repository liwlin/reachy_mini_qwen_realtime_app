r"""Standalone test harness for the choreographer pipeline.

Runs the real codegen LLM -> bake -> validate pipeline without the
conversation app::

    uv run python -m reachy_mini_conversation_app.choreographer.cli \\
        "a nervous, anxious little shiver" --kind emotion --play

Without ``--play`` no robot is needed at all. Configure the model with
MOVE_COMPOSER_MODEL / MOVE_COMPOSER_BASE_URL / MOVE_COMPOSER_API_KEY
(defaults: Hugging Face router with your HF token).
"""

from __future__ import annotations
import sys
import time
import asyncio
import logging
import argparse

from reachy_mini_conversation_app.choreographer.store import save_move
from reachy_mini_conversation_app.choreographer.composer import MoveComposer, MoveComposerError, composer_model


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate (and optionally play) a new Reachy Mini move.")
    parser.add_argument("brief", help="natural-language description of the desired move")
    parser.add_argument("--kind", choices=["emotion", "dance"], default="emotion")
    parser.add_argument("--duration-beats", type=float, default=None, help="approximate length in beats")
    parser.add_argument("--play", action="store_true", help="play the move on a connected robot")
    parser.add_argument("--no-save", action="store_true", help="do not persist the move to the repertoire")
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the choreographer CLI."""
    args = _parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")

    print(f"Composing with model: {composer_model()}")
    started = time.monotonic()
    try:
        composed = asyncio.run(
            MoveComposer().compose(args.brief, kind=args.kind, duration_hint_beats=args.duration_beats)
        )
    except MoveComposerError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    elapsed = time.monotonic() - started

    duration_s = composed.duration_beats * 60.0 / composed.bpm
    print(f"\n--- generated source ({composed.attempts} attempt(s), {elapsed:.1f}s) ---")
    print(composed.source)
    print(
        f"--- '{composed.name}': {composed.description} | {composed.bpm:g} bpm, "
        f"{composed.duration_beats:g} beats ({duration_s:.1f}s), {len(composed.move['time'])} frames, validator OK ---"
    )

    if not args.no_save:
        name, move_dir = save_move(None, composed, args.brief)
        print(f"saved as '{name}' in {move_dir}")

    if args.play:
        from reachy_mini import ReachyMini
        from reachy_mini.motion.recorded_move import RecordedMove

        print("connecting to robot...")
        with ReachyMini() as mini:
            print("playing...")
            mini.play_move(RecordedMove(composed.move), initial_goto_duration=1.0)
        print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
