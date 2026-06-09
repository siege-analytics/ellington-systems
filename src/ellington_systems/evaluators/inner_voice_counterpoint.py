"""Evaluator for the ``_pending:inner-voice-counterpoint`` payload kind.

8 corpus instances at plugin SHA `628ed30`. Per the Investigation
Fact Sheet (Entity 6), payload fields are ``voice_count`` (2 of 8),
``preserve_independence`` (1 of 8), ``bass_role`` (1 of 8). Closest
``_pending:`` kind to graduating to canonical per the cross-agent
reply.

## Spike semantics

The spike's purpose for this kind is to **demonstrate the
data-first / code-catches-up loop** — the plugin's data carries
``_pending:inner-voice-counterpoint`` references already; this Python
evaluator is the first code that does anything with them.

Implementation: if the payload declares a ``voice_count``, treat that
as the minimum number of distinct sounding notes the candidate must
have for the rule to "apply." Mute strings reduce the sounding count.

- ``payload.voice_count <= len(voicing.notes) - len(voicing.mutes)``:
  emit ``PayloadDelta(status="applied", score_delta=+6.0)``.
- Otherwise emit ``PayloadDelta(status="inert")``.

If the payload has no ``voice_count`` at all, return ``inert`` — the
rule doesn't have enough constraints to evaluate. (Future graduation
to canonical may add a default; the spike preserves the conservative
behaviour.)
"""

from __future__ import annotations

from typing import Any, Mapping

from ..models import EnginePayload, PayloadDelta, Voicing


def inner_voice_counterpoint(
    payload: EnginePayload,
    voicing: Voicing,
    context: Mapping[str, Any],
) -> PayloadDelta:
    """Evaluate one ``_pending:inner-voice-counterpoint`` payload."""
    payload_data = payload.model_dump()
    voice_count_required = payload_data.get("voice_count")
    principle_id = context.get("principle_id")

    if not isinstance(voice_count_required, int):
        return PayloadDelta(
            status="inert",
            score_delta=0.0,
            applied_principle=None,
            notes="payload has no voice_count constraint to evaluate",
        )

    # Sounding notes = total notes minus muted strings (defensive on
    # nullable corpus fields).
    notes_count = len(voicing.notes) if voicing.notes else 0
    mute_count = len(voicing.mutes) if voicing.mutes else 0
    sounding = max(0, notes_count - mute_count)

    if sounding >= voice_count_required:
        return PayloadDelta(
            status="applied",
            score_delta=6.0,
            applied_principle=principle_id,
            notes=f"sounding={sounding} satisfies voice_count={voice_count_required}",
        )

    return PayloadDelta(
        status="inert",
        score_delta=0.0,
        applied_principle=None,
        notes=f"sounding={sounding} < voice_count={voice_count_required}",
    )


__all__ = ["inner_voice_counterpoint"]
