"""Evaluators for `engine_payload.kind` entries.

Each module exposes a single callable matching the `PayloadEvaluator`
protocol (`dispatcher.PayloadEvaluator`). The dispatcher's
`build_default_registry()` wires all three of these into a registry.

The spike implements three kinds to cover the three states a payload
kind can be in:

- **`substitution_expand`** — canonical kind, 134 corpus instances.
  Demonstrates the dispatcher handles the most-implemented kind.
- **`inner_voice_counterpoint`** — `_pending:` kind, 8 corpus
  instances. Demonstrates the data-first / code-catches-up loop.
- **`melodic_cell_traversal`** — Ellington-local kind with NO plugin
  corpus instances. Demonstrates the dispatcher accepts kinds the
  plugin schema doesn't ship (Goal B expansibility claim).
"""
