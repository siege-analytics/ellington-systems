"""Evaluator for the canonical ``SubstitutionExpand`` payload kind.

134 corpus instances at plugin SHA `628ed30`. Per the Investigation
Fact Sheet (Entity 5), the payload shape is ad-hoc heterogeneous: only
``kind`` is universal. Common fields when present: ``interval``,
``target_type``, ``source_type``, ``applies_to_contexts``, ``to``,
``from``.

## Spike semantics (deliberately simple)

The spike's job is to **prove the dispatcher mechanism works**, not to
implement the full musical semantics of substitution expansion. So
this evaluator implements a clearly-scoped subset:

- If the payload carries a ``target_type`` field AND the candidate
  voicing's ``chord_quality`` matches it (case-insensitive substring),
  emit ``PayloadDelta(status="applied", score_delta=+8.0)``.
- If the payload carries a ``source_type`` field AND the candidate's
  ``chord_quality`` matches it, emit ``PayloadDelta(status="applied",
  score_delta=+4.0)`` — weaker signal because the candidate is the
  "from", not the "to".
- Otherwise, emit ``PayloadDelta(status="inert")``.

The score-delta values are not load-bearing — they're chosen small
enough that a real substitution-system implementation can later
re-weight without invalidating this evaluator's structural correctness.

The ``applied_principle`` field is populated from ``context.get("principle_id")``
when set (caller's responsibility to thread it through).
"""

from __future__ import annotations

from typing import Any, Mapping

from ..models import EnginePayload, PayloadDelta, Voicing


def substitution_expand(
    payload: EnginePayload,
    voicing: Voicing,
    context: Mapping[str, Any],
) -> PayloadDelta:
    """Evaluate one ``SubstitutionExpand`` payload against a candidate.

    Args:
        payload: the ``engine_payload`` entry, kind=``SubstitutionExpand``.
        voicing: the candidate ``Voicing`` being scored.
        context: free-form caller context; ``principle_id`` if set is
            threaded through to the resulting ``applied_principle``.

    Returns:
        A ``PayloadDelta`` indicating how this payload contributes to
        the candidate's score.
    """
    # `extra="allow"` on EnginePayload puts unknown fields in the dump.
    # Read them defensively since the corpus shape varies per instance.
    payload_data = payload.model_dump()
    target_type = payload_data.get("target_type")
    source_type = payload_data.get("source_type")
    principle_id = context.get("principle_id")

    candidate_quality = voicing.chord_quality.lower()

    if isinstance(target_type, str) and target_type.lower() in candidate_quality:
        return PayloadDelta(
            status="applied",
            score_delta=8.0,
            applied_principle=principle_id,
            notes=f"target_type={target_type!r} matches candidate quality",
        )

    if isinstance(source_type, str) and source_type.lower() in candidate_quality:
        return PayloadDelta(
            status="applied",
            score_delta=4.0,
            applied_principle=principle_id,
            notes=f"source_type={source_type!r} matches candidate quality (weaker signal)",
        )

    return PayloadDelta(
        status="inert",
        score_delta=0.0,
        applied_principle=None,
        notes=None,
    )


__all__ = ["substitution_expand"]
