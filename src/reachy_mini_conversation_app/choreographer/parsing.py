"""Parse the codegen LLM reply into a move header and executable source.

Expected reply shape (enforced by the composer prompt): one fenced Python code
block whose first comment lines declare the move metadata::

    ```python
    # name: anxious_glance
    # description: quick nervous glances with drooping antennas
    # bpm: 100
    # duration_beats: 12
    def move(t_beats):
        ...
    ```
"""

from __future__ import annotations
import re
from dataclasses import dataclass


_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)
_HEADER_RE = re.compile(r"^#\s*(name|description|bpm|duration_beats)\s*:\s*(.+?)\s*$", re.MULTILINE)

MAX_NAME_CHARS = 48
_MIN_BPM, _MAX_BPM = 20.0, 240.0
_MIN_BEATS, _MAX_BEATS = 1.0, 120.0


class ParseError(ValueError):
    """Raised when the LLM reply does not follow the move contract."""


@dataclass(frozen=True)
class MoveHeader:
    """Metadata declared at the top of a generated move."""

    name: str
    description: str
    bpm: float
    duration_beats: float


def slugify(name: str) -> str:
    """Normalize a move name to a filesystem/tool-friendly slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:MAX_NAME_CHARS] or "unnamed_move"


def extract_move_source(text: str) -> tuple[MoveHeader, str]:
    """Return the declared header and the source of the last code block in `text`.

    The last block wins: models sometimes think out loud in earlier blocks.
    Raises ParseError with an LLM-consumable message on any contract breach.
    """
    blocks = _CODE_BLOCK_RE.findall(text)
    if not blocks:
        raise ParseError("reply must contain exactly one fenced ```python code block")
    source = blocks[-1].strip() + "\n"

    if not re.search(r"^def move\(", source, re.MULTILINE):
        raise ParseError("the code block must define a top-level function `def move(t_beats):`")

    fields = dict(_HEADER_RE.findall(source))
    missing = [key for key in ("name", "description", "bpm", "duration_beats") if key not in fields]
    if missing:
        raise ParseError(
            f"missing header comment(s) {missing} - the code block must start with"
            " `# name: ...`, `# description: ...`, `# bpm: ...`, `# duration_beats: ...`"
        )

    try:
        bpm = float(fields["bpm"])
        duration_beats = float(fields["duration_beats"])
    except ValueError as error:
        raise ParseError("`# bpm:` and `# duration_beats:` must be numbers") from error
    if not (_MIN_BPM <= bpm <= _MAX_BPM):
        raise ParseError(f"bpm {bpm:g} out of range [{_MIN_BPM:g}, {_MAX_BPM:g}]")
    if not (_MIN_BEATS <= duration_beats <= _MAX_BEATS):
        raise ParseError(f"duration_beats {duration_beats:g} out of range [{_MIN_BEATS:g}, {_MAX_BEATS:g}]")

    header = MoveHeader(
        name=slugify(fields["name"]),
        description=fields["description"],
        bpm=bpm,
        duration_beats=duration_beats,
    )
    return header, source
