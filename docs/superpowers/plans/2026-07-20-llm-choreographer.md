# LLM Choreographer Implementation Plan

> Executed inline in this session (user requested fully-autonomous build).
> Spec: /Users/remi/reachy_mini_apps/llm_choreographer/ANALYSIS.md

**Goal:** During conversation, the user asks for a new movement ("make an anxious move");
a background tool has a codegen LLM write a symbolic move function, bakes it to a sampled
trajectory in a robot-less subprocess, validates the data against hardware-safety limits,
plays it through the MovementManager queue, announces it, and remembers it by name.

**Architecture:** compile-don't-interpret. LLM emits Python source for
`def move(t_beats) -> MoveOffsets` (rhythmic_motion vocabulary). A sandboxed
`python -I -m ...bake_worker` subprocess (rlimits, timeout, scrubbed env, no robot)
samples it at 50 Hz into RecordedMove-shaped JSON. A numeric validator enforces
offset/velocity/duration caps (the daemon has NO velocity limiting — this is the safety
gate). On success: persist to disk, chime, queue via a RecordedMove wrapper, LLM announces.

**Tech stack:** existing deps only — openai (AsyncOpenAI against HF router by default,
reuses HF_TOKEN), numpy, reachy_mini (RecordedMove, create_head_pose),
reachy_mini_dances_library (rhythmic_motion available to generated code).

## Global constraints

- Branch `llm-choreographer` off origin/main, worktree at
  `reachy_mini_conversation_app-choreographer`. Commit per task, short messages, no Co-Authored-By.
- CI parity: `VIRTUAL_ENV= uv run ruff check .` + `ruff format --check .` + `uv run mypy`
  (strict, files=src/) + `uv run pytest` (needs `uv sync --frozen --all-extras --group dev`).
- Composer config via env: `MOVE_COMPOSER_MODEL` (default `Qwen/Qwen3-Coder-480B-A35B-Instruct`),
  `MOVE_COMPOSER_BASE_URL` (default `https://router.huggingface.co/v1`),
  `MOVE_COMPOSER_API_KEY` (default: HF_TOKEN, then huggingface_hub.get_token()).
- Safety limits (validator, conservative starting points):
  |pos offset| ≤ 0.04 m/axis; |roll,pitch| ≤ 30°; |yaw| ≤ 60°; antennas ≤ ±100°;
  translation vel ≤ 0.15 m/s; head rot vel ≤ 180°/s; antenna vel ≤ 400°/s;
  duration 0.5–30 s; all values finite; first frame within 0.02 m / 15° / 30° (ant.) of neutral.
- Bake: 50 Hz, body_yaw fixed 0.0 (symbolic language has no body yaw), head pose composed
  exactly like `DanceMove.evaluate` (`create_head_pose(..., degrees=False, mm=False)`).

## File map

```
src/reachy_mini_conversation_app/choreographer/
  __init__.py        exports: compose_move, ComposedMove, MoveComposerError
  limits.py          SafetyLimits dataclass + DEFAULT_LIMITS (single source of truth)
  validator.py       validate_trajectory(move_dict, limits) -> list[str] (violations)
  bake_worker.py     __main__-style stdin/stdout subprocess entry (imports only math/numpy/
                     rhythmic_motion + create_head_pose; defines exec namespace)
  bake.py            bake_source(source, bpm, duration_beats, fps=50, timeout_s=20) ->
                     dict (RecordedMove shape) — runs bake_worker via subprocess, rlimits
  parsing.py         extract_move_source(llm_text) -> MoveHeader(name,bpm,duration_beats)+source
  composer.py        MoveComposer: prompt build (few-shots from dances lib), AsyncOpenAI
                     call, bake+validate retry loop (max 2 retries, violations fed back)
  store.py           moves_dir_for_instance(), save_move(), load_move(), list_moves()
  cli.py             python -m ...choreographer.cli "brief" [--play] — robot-optional test path
sounds/__init__.py   play(media, filename) — packaged-file guard (port of dream-branch util)
sounds/move_ready.wav  generated two-note chime (numpy)
tools/create_move.py        Tool create_move (background; composes, saves, chimes, queues)
tools/play_generated_move.py Tool play_generated_move (list/replay saved moves)
generated_moves.py   GeneratedQueueMove(RecordedMove wrapper, mirrors EmotionQueueMove)
profiles/default/tools.txt  + create_move, play_generated_move
tests/choreographer/ test_validator.py test_bake.py test_parsing.py test_composer.py
                     test_store.py test_tools_create_move.py
```

## Interfaces (contracts between tasks)

- `SafetyLimits` frozen dataclass; `DEFAULT_LIMITS: SafetyLimits`.
- `validate_trajectory(move: dict, limits: SafetyLimits = DEFAULT_LIMITS) -> list[str]`
  — empty list = valid; move dict = `{"description": str, "time": [...],
  "set_target_data": [{"head": 4x4 list, "antennas": [l, r], "body_yaw": 0.0}]}`.
- `bake_source(source: str, *, bpm: float, duration_beats: float, fps: int = 50,
  timeout_s: float = 20) -> dict` — raises `BakeError(str)` on syntax error/timeout/crash.
- `MoveHeader = (name: str, bpm: float, duration_beats: float)`;
  `extract_move_source(text) -> tuple[MoveHeader, str]` — raises `ParseError`.
- `MoveComposer.compose(brief: str, kind: str, duration_hint_beats: float | None) ->
  ComposedMove(name, description, bpm, duration_beats, source, move: dict, attempts: int)`
  — raises `MoveComposerError` after retries exhausted.
- `save_move(instance_path, composed) -> Path`; `load_move(instance_path, name) ->
  tuple[dict, dict]` (move, meta); `list_moves(instance_path) -> list[dict]` (meta dicts).
- `GeneratedQueueMove(move_dict)` — Move subclass wrapping `RecordedMove`.

## Tasks (each: tests first where practical, run, implement, run green, commit)

1. Plan doc committed. ✔ (this file)
2. `limits.py` + `validator.py` + tests (valid gentle sine passes; amplitude, velocity,
   non-finite, bad start pose, too-short each rejected with a message naming the channel).
3. `bake_worker.py` + `bake.py` + tests (simple nod source bakes to N frames with valid
   shape; `while True` source → BakeError timeout; syntax error → BakeError with stderr;
   worker cannot see parent env secrets).
4. `parsing.py` + tests (well-formed reply parses; missing header → ParseError; code fence
   variants).
5. `composer.py` + tests with fake OpenAI client (happy path 1 attempt; validator failure
   then corrected retry; API error → MoveComposerError).
6. `store.py` + tests (save→load roundtrip, slug collision suffixing, list ordering).
7. `generated_moves.py` (GeneratedQueueMove) + `sounds/` + chime wav + tests.
8. `tools/create_move.py` + `tools/play_generated_move.py` + tools.txt + tests
   (monkeypatched composer; queue interaction via fake movement_manager).
9. `cli.py` (`--play` optional, works robot-less with `--no-play`) + smoke test.
10. Full CI parity run (ruff, ruff format, mypy strict, pytest) — fix everything.
11. Docs: README section + .env.example entries.
