"""Layer 3 — The four specialized agents (design doc §4).

Each module exposes `node(state)`: it runs its tools (recorded), asks its LLM to analyze
the evidence with its YAML prompt, validates the JSON reply and persists the result.
"""
