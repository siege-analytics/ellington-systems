"""Pydantic models for the engine's request/response surface.

Shapes mirror the JSON contract baked into
[musescore4-chord-library-plugin#400](https://github.com/siege-analytics/musescore4-chord-library-plugin/issues/400),
the Node.js shim CLI that serves as Goal A's oracle. EngineResponse must be
structurally identical to the shim's output so the diff harness can compare
ranked voicings and score components element-wise.

`EnginePayload` uses `extra="allow"` to absorb the corpus's heterogeneous
`engine_payload.kind` shapes — see the Investigation Fact Sheet's Entity 5
disposition (`SubstitutionExpand` has 32 distinct top-level keys with
frequencies 1-9 across the 134 instances).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EngineRequest(BaseModel):
    """Top-level input to `Engine.rank`."""

    model_config = ConfigDict(extra="forbid")

    chord_symbol: str = Field(
        description="Chord symbol such as 'Cmaj7', 'F#m7b5', 'G13b9'."
    )
    tuning: list[str] = Field(
        description=(
            "Pitch list per string, low to high. Arbitrary length: 6-string "
            "standard ['E2','A2','D3','G3','B3','E4'], 7-string Van Eps, "
            "baritone, custom — engine discovers string count from len(tuning)."
        ),
        min_length=4,
        max_length=12,
    )
    master_id: str | None = Field(
        default=None,
        description="Master ID from masters.json (e.g. 'joe-pass'); None disables master_boost.",
    )
    style_filter: str | None = Field(
        default=None,
        description="Optional style profile name; None disables profile weighting.",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Free-form context bag carrying position_preference, n_strings, "
            "mode_id, etc. Phase 3 evaluators read what they recognize."
        ),
    )


class ScoreComponents(BaseModel):
    """Score breakdown matching the shim's `score_components` shape.

    The plugin's `_scoreCandidate` formula is additive across multiple
    terms; for the spike, we report three top-level buckets:

    - `base`: total minus master_boost minus tolerance_match
    - `master_boost`: `Math.min(hits, 2) * 30`, max +60
    - `tolerance_match`: reserved at 0.0 (no JS tolerance scoring path
      exists today — placeholder for future Phase 3 contributions)
    """

    model_config = ConfigDict(extra="forbid")

    base: float
    master_boost: float = 0.0
    tolerance_match: float = 0.0


class RankedVoicing(BaseModel):
    """One row of `EngineResponse.ranked_voicings`."""

    model_config = ConfigDict(extra="forbid")

    voicing_id: str = Field(description="Stable ID from voicings.json — unique across the corpus.")
    score: float
    payload_kind: str | None = Field(
        default=None,
        description=(
            "Dominant engine_payload.kind that fired during Phase 3 dispatch "
            "for this voicing, if any. None = Phase 3 was silent."
        ),
    )
    score_components: ScoreComponents
    applied_principles: list[str] = Field(
        default_factory=list,
        description=(
            "Provenance — which masters[*].principles or systems entries contributed. "
            "Each entry is 'master_id/principle_id' or 'master_id/system_id/rule_id'."
        ),
    )


class EngineResponse(BaseModel):
    """Top-level output of `Engine.rank`. Mirrors shim #400's JSON shape."""

    model_config = ConfigDict(extra="forbid")

    request: EngineRequest
    ranked_voicings: list[RankedVoicing]
    engine_version: str = Field(description="Ellington-systems commit SHA at evaluation time.")
    masters_version: str = Field(description="Vendored plugin SHA the masters corpus was loaded from.")


# ---------------------------------------------------------------------------
# Phase 3: engine_payload + dispatcher protocol shapes
# ---------------------------------------------------------------------------


class EnginePayload(BaseModel):
    """An `engine_payload` entry from `masters.json`.

    Shape is intentionally permissive: only `kind` is universal in the corpus
    (per the Investigation Fact Sheet — Entity 5 and Entity 6, both probed
    via `jq` on the 134 SubstitutionExpand + 8 _pending:inner-voice-counterpoint
    instances). All other keys are kind-specific and ad-hoc; `extra="allow"`
    captures them as fields available to Phase 3 evaluators.
    """

    model_config = ConfigDict(extra="allow")

    kind: str = Field(
        description=(
            "Canonical kind (e.g. 'SubstitutionExpand') or '_pending:<kebab>' "
            "for kinds not yet code-implemented (data-first / code-catches-up)."
        ),
    )


class PayloadDelta(BaseModel):
    """The output of a Phase 3 payload evaluator for one (candidate, payload) pair."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["applied", "inert", "rejected"]
    score_delta: float = 0.0
    applied_principle: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Internal candidate shape — voicings.json entries as the engine sees them
# ---------------------------------------------------------------------------


class VoicingDot(BaseModel):
    """One fret placement within a voicing."""

    model_config = ConfigDict(extra="forbid")

    string: int = Field(ge=1, le=12)
    fret: int = Field(ge=0)


class Voicing(BaseModel):
    """A candidate voicing entry from `voicings.json`.

    Field set is taken verbatim from the corpus probe at plugin SHA
    `628ed30…`; see Investigation Fact Sheet Entity 4. `extra="allow"`
    because the corpus may carry plugin-internal fields the engine
    doesn't read but should not reject.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    chord_quality: str
    root: str
    category: str
    strings: int = Field(ge=4, le=12)
    fret_number: int = Field(ge=0)
    visible_frets: int = Field(ge=1)
    dots: list[VoicingDot] = Field(default_factory=list)
    mutes: list[Any] = Field(default_factory=list)
    open: list[Any] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    intervals: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    shape_id: str | None = None
    also_qualities: list[str] = Field(default_factory=list)
    suitableModes: list[str] = Field(default_factory=list)
    voicingStyle: list[str] = Field(
        default_factory=list,
        description=(
            "Tags driving the master_boost intersection. Empty in current "
            "corpus state (0/820 tagged as of plugin SHA 628ed30); "
            "crowdsourcing in flight on plugin #389/#393/#395."
        ),
    )
    playStyle: list[str] = Field(default_factory=list)
    fingering: list[Any] = Field(default_factory=list)


__all__ = [
    "EnginePayload",
    "EngineRequest",
    "EngineResponse",
    "PayloadDelta",
    "RankedVoicing",
    "ScoreComponents",
    "Voicing",
    "VoicingDot",
]
