"""Evaluator for ``_pending:melodic-cell-traversal`` — an Ellington-LOCAL
payload kind with NO plugin corpus instances at SHA `628ed30`.

## Why this exists

Per the design note's Goal B and the Pre-mortem's Elephant 2: the
plugin's `MelodyEngine.js` is a helper library, not a scorer, and the
corpus carries zero melodic ``engine_payload`` kinds today. Ellington's
spike must demonstrate that its dispatcher accepts kinds the plugin
schema doesn't ship — proving the expansibility primitive works in
both directions (plugin-defined kinds AND Ellington-defined kinds).

This evaluator is that demonstration. It's wired into the default
registry alongside the two plugin-corpus kinds. A future plugin update
that adds ``_pending:melodic-cell-traversal`` to the schema (or
graduates it to a canonical name) would replace this evaluator's
"sole owner" status without changing the dispatcher contract.

## Spike semantics

Pat Martino's ``harmonic-structure-dictates-melodic-choice`` principle
(per the [Investigation Fact Sheet](https://github.com/siege-analytics/ellington-systems/issues/1#issuecomment-4646021266) — `pat-martino` corpus entry, 3
principles) is the conceptual driver: a melodic cell is a small
recurring interval pattern that maps onto an underlying chord position.

Inputs the evaluator reads (all optional, ad-hoc per the
heterogeneous-shape pattern of the canonical kinds):

- ``cell``: a string identifier (e.g. ``"min-pent"``,
  ``"diminished-passing"``) — informational only in the spike.
- ``target_intervals``: a list of interval strings (e.g.
  ``["1", "b3", "5", "b7"]``) — the cell's interval vocabulary.

Behaviour:

- If the candidate's ``intervals`` field contains AT LEAST 2 of the
  ``target_intervals``, emit ``PayloadDelta(status="applied",
  score_delta=+5.0)`` (modest signal — melodic cells are weak voicing
  preferences, not strong constraints).
- Otherwise emit ``PayloadDelta(status="inert")``.

The intersection-of-2 threshold is the same shape as
``_scoreCandidate``'s master-boost gate (``Math.min(hits, 2)``) so the
behaviour scales with the existing system rather than introducing a
new heuristic.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..models import EnginePayload, PayloadDelta, Voicing


def melodic_cell_traversal(
    payload: EnginePayload,
    voicing: Voicing,
    context: Mapping[str, Any],
) -> PayloadDelta:
    """Evaluate one ``_pending:melodic-cell-traversal`` payload."""
    payload_data = payload.model_dump()
    target_intervals = payload_data.get("target_intervals") or []
    principle_id = context.get("principle_id")

    if not isinstance(target_intervals, list) or len(target_intervals) == 0:
        return PayloadDelta(
            status="inert",
            score_delta=0.0,
            applied_principle=None,
            notes="payload has no target_intervals to evaluate",
        )

    if not voicing.intervals:
        return PayloadDelta(
            status="inert",
            score_delta=0.0,
            applied_principle=None,
            notes="candidate has no intervals to match against",
        )

    target_set = set(target_intervals)
    hits = sum(1 for iv in voicing.intervals if iv in target_set)

    if hits >= 2:
        return PayloadDelta(
            status="applied",
            score_delta=5.0,
            applied_principle=principle_id,
            notes=f"melodic-cell match: hits={hits} (target_intervals={target_intervals})",
        )

    return PayloadDelta(
        status="inert",
        score_delta=0.0,
        applied_principle=None,
        notes=f"melodic-cell miss: hits={hits} < 2",
    )


__all__ = ["melodic_cell_traversal"]
