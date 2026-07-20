"""LLM-generated movement pipeline (compose -> bake -> validate -> play).

The choreographer lets a codegen LLM write a symbolic move function which is
executed in a robot-less subprocess, sampled into a RecordedMove-shaped
trajectory, and numerically validated before it is allowed anywhere near the
robot. See docs/superpowers/plans/2026-07-20-llm-choreographer.md.
"""
