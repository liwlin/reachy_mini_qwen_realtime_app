"""Run generated move source in an isolated subprocess and collect the trajectory."""

from __future__ import annotations
import sys
import json
import logging
import tempfile
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_FPS = 50.0
DEFAULT_TIMEOUT_S = 20.0
_STDERR_EXCERPT_CHARS = 2000


class BakeError(RuntimeError):
    """Raised when generated source cannot be baked into a trajectory."""


def bake_source(
    source: str,
    *,
    bpm: float,
    duration_beats: float,
    fps: float = DEFAULT_FPS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Sample `source` (which must define ``move(t_beats)``) into a trajectory dict.

    The code runs in a separate ``python -I`` process with a scrubbed
    environment, its own CPU rlimit, and a wall-clock timeout, so hangs,
    crashes, and resource blowups in LLM-generated code cannot take the app
    down. Raises BakeError with an LLM-consumable message on any failure.
    """
    spec = json.dumps({"source": source, "bpm": bpm, "duration_beats": duration_beats, "fps": fps})
    with tempfile.TemporaryDirectory(prefix="choreographer_bake_") as scratch_home:
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-m", "reachy_mini_conversation_app.choreographer.bake_worker"],
                input=spec,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                env={"HOME": scratch_home},
                cwd=scratch_home,
            )
        except subprocess.TimeoutExpired as error:
            raise BakeError(
                f"baking timed out after {timeout_s:.0f}s - the move function must be a fast, "
                "pure function of t_beats with no loops over time and no I/O"
            ) from error

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()[-_STDERR_EXCERPT_CHARS:]
        raise BakeError(f"generated code failed while baking:\n{stderr or 'no error output'}")

    try:
        move: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise BakeError("bake worker produced invalid output; the move function must not print") from error
    logger.debug("Baked %d frames at %.0f fps", len(move.get("time", [])), fps)
    return move
