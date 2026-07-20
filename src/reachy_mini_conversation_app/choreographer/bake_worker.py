"""Subprocess entry point that samples an LLM-generated move function.

Runs with ``python -I -m reachy_mini_conversation_app.choreographer.bake_worker``,
reads ``{"source", "bpm", "duration_beats", "fps"}`` as JSON on stdin and writes
a RecordedMove-shaped trajectory as JSON on stdout. It never touches the robot:
process isolation (plus the caller's scrubbed environment and wall-clock
timeout) contains buggy generated code, and the caller's validator is the
actual safety gate for whatever comes out.
"""

from __future__ import annotations
import sys
import json
import math
from typing import Any

_CPU_SECONDS_LIMIT = 10


def _apply_self_rlimits() -> None:
    """Bound our own CPU (and, on Linux, memory) before running generated code."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (_CPU_SECONDS_LIMIT, _CPU_SECONDS_LIMIT))
        if sys.platform.startswith("linux"):
            memory_bytes = 1 << 30  # 1 GiB
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except Exception:  # pragma: no cover - resource may be missing on exotic platforms
        pass


def _build_namespace() -> dict[str, Any]:
    """Expose the symbolic-motion vocabulary the generated code may use."""
    import numpy as np
    from reachy_mini_dances_library import rhythmic_motion

    namespace: dict[str, Any] = {"math": math, "np": np, "numpy": np}
    for name in dir(rhythmic_motion):
        if not name.startswith("_"):
            namespace[name] = getattr(rhythmic_motion, name)
    return namespace


def main() -> int:
    """Sample the move function described on stdin and print the trajectory."""
    _apply_self_rlimits()

    spec = json.loads(sys.stdin.read())
    source: str = spec["source"]
    bpm = float(spec["bpm"])
    duration_beats = float(spec["duration_beats"])
    fps = float(spec.get("fps", 50.0))
    if bpm <= 0 or duration_beats <= 0 or fps <= 0:
        print("bpm, duration_beats and fps must all be positive", file=sys.stderr)
        return 1

    from reachy_mini.utils import create_head_pose

    namespace = _build_namespace()
    exec(compile(source, "<generated_move>", "exec"), namespace)  # noqa: S102 - the whole point of this worker
    move_fn = namespace.get("move")
    if not callable(move_fn):
        print("generated source must define a function `move(t_beats)`", file=sys.stderr)
        return 1

    duration_s = duration_beats * 60.0 / bpm
    frame_count = int(duration_s * fps) + 1
    time: list[float] = []
    frames: list[dict[str, Any]] = []
    for index in range(frame_count):
        t = index / fps
        offsets = move_fn(t * bpm / 60.0)
        x, y, z = (float(v) for v in offsets.position_offset)
        roll, pitch, yaw = (float(v) for v in offsets.orientation_offset)
        head = create_head_pose(x=x, y=y, z=z, roll=roll, pitch=pitch, yaw=yaw, degrees=False, mm=False)
        time.append(t)
        frames.append(
            {
                "head": head.tolist(),
                "antennas": [float(offsets.antennas_offset[0]), float(offsets.antennas_offset[1])],
                "body_yaw": 0.0,
            }
        )

    json.dump({"time": time, "set_target_data": frames}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
