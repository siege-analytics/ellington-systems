"""Phase 2 — `BaseScorer`: port of `ChordSelector._scoreCandidate`.

Mirrors the JavaScript formula at
`plugin/model/ChordSelector.js:240-304` of the
musescore4-chord-library-plugin at SHA
`628ed30fbb03bbf015f167ce8962edef8c0e5273`.

**Tiger 3 mitigation** (pre-mortem on ticket #1): operation order is preserved
term-by-term against the JS source. The Python expression structure is
intentionally NOT refactored into "cleaner" idioms — each term is its
own statement that maps 1:1 to the JS line that produced it. The reader
should be able to diff this module against the JS source side-by-side
and see equivalence.

`compute_mode_delta` and `signature_key` are local ports of the helper
functions at `ChordSelector.js:181-211` and `ChordSelector.js:94-120`
respectively. Their separate existence in this module mirrors the JS
file's layout for the same diffability reason.

Return type is `ScoreBreakdown` — every component is exposed individually
so the Goal A oracle diff against shim CLI #400 can compare per-term, not
just per-total. Per-term comparison is what catches float-drift bugs in
single components even when the total happens to coincide (Tiger 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import Voicing


# ---------------------------------------------------------------------------
# Score breakdown — internal per-component record
# ---------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Per-term breakdown of one voicing's score under `_scoreCandidate`.

    Each field corresponds to one statement in the JS formula. `total`
    is the sum across all fields; expose it as a property so Pydantic
    doesn't need to track derived state.

    `master_boost` is the only field with a documented hard cap (+60 in
    JS, via `Math.min(hits, 2) * 30`). Every other field is unbounded
    on the up/down side per the JS source.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    quality_match: float = 0.0
    filter_category: float = 0.0
    category_default: float = 0.0
    melody_bonus: float = 0.0
    bass_bonus: float = 0.0
    distance_penalty: float = 0.0
    same_category_fret: float = 0.0
    mute_penalty: float = 0.0
    fret_3_to_7: float = 0.0
    difficulty_penalty: float = 0.0
    profile_category_weight: float = 0.0
    profile_quality_boost: float = 0.0
    mode_delta: float = 0.0
    curated_boost: float = 0.0
    master_boost: float = 0.0

    @property
    def total(self) -> float:
        """Sum of all components. Mirrors the final value of `score` at the
        end of `_scoreCandidate` in JS."""
        return (
            self.quality_match
            + self.filter_category
            + self.category_default
            + self.melody_bonus
            + self.bass_bonus
            + self.distance_penalty
            + self.same_category_fret
            + self.mute_penalty
            + self.fret_3_to_7
            + self.difficulty_penalty
            + self.profile_category_weight
            + self.profile_quality_boost
            + self.mode_delta
            + self.curated_boost
            + self.master_boost
        )


# ---------------------------------------------------------------------------
# Opts bag — mirrors the JS `opts` object passed to _scoreCandidate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoringOpts:
    """Call-context bag matching the JS `opts` shape.

    The JS engine wires `topNoteFn` / `bassNoteFn` / `distanceFn` /
    `difficultyFn` / `profileCategoryWeightFn` / `profileQualityBoostFn`
    from `MelodyEngine` / `FingeringEngine` / `StyleComposer`. For the
    spike, Phase 2 takes them as injected callables. Implementing them
    natively in Python is out of spike scope.

    `mode_config` and `mode_id` drive `compute_mode_delta`.
    `curated_lookup` is a precomputed map from `signature_key` to a
    `{boost: float, ...}` entry.
    """

    filter_category: Optional[str] = None
    melody_locked: bool = False
    bass_locked: bool = False
    semitone_map: Optional[Mapping[str, int]] = None
    master_voicing_style_tags: list[str] = field(default_factory=list)
    mode_config: Optional[Mapping[str, Any]] = None
    mode_id: Optional[str] = None
    curated_lookup: Optional[Mapping[str, Mapping[str, Any]]] = None

    # Injected callables (see module docstring; out of spike scope to implement)
    top_note_fn: Optional[Callable[[Voicing, str, Mapping[str, int] | None], int]] = None
    bass_note_fn: Optional[Callable[[Voicing, str, Mapping[str, int] | None], int]] = None
    distance_fn: Optional[Callable[[Voicing, Voicing], float]] = None
    difficulty_fn: Optional[Callable[[Voicing], Mapping[str, Any] | None]] = None
    profile_category_weight_fn: Optional[Callable[[str], float]] = None
    profile_quality_boost_fn: Optional[Callable[[str], float]] = None


# ---------------------------------------------------------------------------
# Helpers — ported from ChordSelector.js
# ---------------------------------------------------------------------------


def compute_mode_delta(
    voicing: Voicing,
    mode_config: Mapping[str, Any] | None,
    mode_id: str | None,
) -> float:
    """Port of `computeModeDelta` at `ChordSelector.js:181-211`.

    Operation order preserved against JS source. Returns 0 for a null
    mode_config (matches `if (!modeConfig) return 0` at line 182).
    """
    if not mode_config:
        return 0.0
    delta: float = 0.0
    cd = mode_config.get("categoryDeltas") or {}
    if voicing.category and voicing.category in cd:
        delta += cd[voicing.category]
    fret = voicing.fret_number or 0
    if (
        mode_config.get("rangeFretMin") is not None
        and mode_config.get("rangeFretMax") is not None
        and fret >= mode_config["rangeFretMin"]
        and fret <= mode_config["rangeFretMax"]
    ):
        delta += mode_config.get("rangeFretBonus", 0) or 0
    if mode_config.get("mutePenaltyPerString"):
        mute_count = len(voicing.mutes) if voicing.mutes else 0
        delta -= mute_count * mode_config["mutePenaltyPerString"]
    if mode_id and voicing.suitableModes and len(voicing.suitableModes) > 0:
        if mode_id in voicing.suitableModes:
            delta += mode_config.get("modeMatchBonus", 0) or 0
        else:
            delta += mode_config.get("modeMismatchPenalty", 0) or 0
    return delta


def signature_key(voicing: Voicing) -> str:
    """Port of `signatureKey` at `ChordSelector.js:94-120`.

    Produces a root-relative fingering signature used as the
    `curated_lookup` key. Format must match the JS exactly so a curated
    payload generated by the plugin's `scripts/derive_curated_shapes.py`
    can be consumed unchanged.

    Format: ``"<strings>|m:<sorted-mutes>|o:<sorted-opens>|p:<sorted (string,interval) pairs>"``
    """
    if voicing is None:
        return ""
    strings = voicing.strings or 6
    mutes = sorted(voicing.mutes) if voicing.mutes else []
    opens = sorted(voicing.open) if voicing.open else []
    dots = voicing.dots or []
    intervals = voicing.intervals or []
    pairs: list[tuple[int, str]] = []
    for i, dot in enumerate(dots):
        if i >= len(intervals):
            continue
        pairs.append((dot.string, intervals[i]))
    # JS sort: numeric on string, lexicographic on interval
    pairs.sort(key=lambda p: (p[0], p[1]))
    pair_str = ",".join(f"{p[0]}:{p[1]}" for p in pairs)
    mute_str = ",".join(str(m) for m in mutes)
    open_str = ",".join(str(o) for o in opens)
    return f"{strings}|m:{mute_str}|o:{open_str}|p:{pair_str}"


# ---------------------------------------------------------------------------
# score_candidate — the formula itself
# ---------------------------------------------------------------------------


def score_candidate(
    voicing: Voicing,
    target_root: str,
    quality: str,
    melody_target: int,
    bass_target: int,
    ref: Voicing | None,
    opts: ScoringOpts,
) -> ScoreBreakdown:
    """Port of `_scoreCandidate` at `ChordSelector.js:240-303`.

    Operation order preserved term-by-term against JS. Each JS statement
    that contributes to `score` becomes one named field on the returned
    `ScoreBreakdown`. The reader should be able to diff this function
    against the JS line-by-line.

    Args:
        voicing: candidate voicing to score (`v` in JS).
        target_root: root note of the requested chord.
        quality: canonical quality ID being requested (e.g. ``"dom7"``).
        melody_target: top-note semitone target, or ``-1`` for no constraint.
        bass_target: bass-note semitone target, or ``-1`` for no constraint.
        ref: optional reference voicing for voice-leading distance (`ref` in JS).
        opts: full call context.

    Returns:
        A `ScoreBreakdown` whose `.total` matches what the JS formula
        would assign to the same voicing+context.
    """
    # ---- quality_match (JS line 243) ----
    quality_match = 20.0 if voicing.chord_quality == quality else 0.0

    # ---- filter_category (JS line 247) ----
    filter_category = (
        50.0
        if opts.filter_category and voicing.category == opts.filter_category
        else 0.0
    )

    # ---- category_default (JS lines 249-250) ----
    if voicing.category == "shell":
        category_default = 10.0
    elif voicing.category == "drop2":
        category_default = 5.0
    else:
        category_default = 0.0

    # ---- melody / bass multipliers (JS lines 252-255) ----
    mode_config = opts.mode_config
    mel_mul = 1.0
    bass_mul = 1.0
    if mode_config:
        if mode_config.get("melodyBonusMultiplier") is not None:
            mel_mul = mode_config["melodyBonusMultiplier"]
        if mode_config.get("bassBonusMultiplier") is not None:
            bass_mul = mode_config["bassBonusMultiplier"]

    # ---- melody_bonus (JS lines 257-260) ----
    melody_bonus = 0.0
    if melody_target >= 0 and opts.top_note_fn is not None:
        bonus = (500.0 if opts.melody_locked else 200.0) * mel_mul
        if opts.top_note_fn(voicing, target_root, opts.semitone_map) == melody_target:
            melody_bonus = bonus

    # ---- bass_bonus (JS lines 261-264) ----
    bass_bonus = 0.0
    if bass_target >= 0 and opts.bass_note_fn is not None:
        bonus = (500.0 if opts.bass_locked else 250.0) * bass_mul
        if opts.bass_note_fn(voicing, target_root, opts.semitone_map) == bass_target:
            bass_bonus = bonus

    # ---- distance_penalty + same_category_fret (JS lines 265-268) ----
    distance_penalty = 0.0
    same_category_fret = 0.0
    if ref is not None and opts.distance_fn is not None:
        distance_penalty = -opts.distance_fn(ref, voicing) * 2.0
        if ref.category == voicing.category and ref.fret_number == voicing.fret_number:
            same_category_fret = -15.0

    # ---- mute_penalty (JS line 269) ----
    mute_count = len(voicing.mutes) if voicing.mutes else 0
    mute_penalty = -mute_count * 5.0

    # ---- fret_3_to_7 (JS lines 270-271) ----
    fret = voicing.fret_number or 0
    fret_3_to_7 = 5.0 if 3 <= fret <= 7 else 0.0

    # ---- difficulty_penalty (JS lines 272-280) ----
    difficulty_penalty = 0.0
    if opts.difficulty_fn is not None:
        d = opts.difficulty_fn(voicing)
        if d is not None:
            tier = d.get("tier")
            if tier == "expert":
                difficulty_penalty = -30.0
            elif tier == "advanced":
                difficulty_penalty = -10.0

    # ---- profile_category_weight (JS line 281) ----
    profile_category_weight = 0.0
    if opts.profile_category_weight_fn is not None:
        profile_category_weight = opts.profile_category_weight_fn(voicing.category)

    # ---- profile_quality_boost (JS line 282) ----
    profile_quality_boost = 0.0
    if opts.profile_quality_boost_fn is not None:
        profile_quality_boost = opts.profile_quality_boost_fn(voicing.chord_quality)

    # ---- mode_delta (JS line 283) ----
    mode_delta = 0.0
    if opts.mode_config:
        mode_delta = compute_mode_delta(voicing, opts.mode_config, opts.mode_id)

    # ---- curated_boost (JS lines 285-290) ----
    curated_boost = 0.0
    if opts.curated_lookup is not None:
        entry = opts.curated_lookup.get(signature_key(voicing))
        if entry and entry.get("boost"):
            curated_boost = entry["boost"]

    # ---- master_boost (JS lines 294-302) ----
    master_boost = 0.0
    if (
        opts.master_voicing_style_tags
        and len(opts.master_voicing_style_tags) > 0
        and voicing.voicingStyle
        and len(voicing.voicingStyle) > 0
    ):
        # Tag intersection — count matches up to the cap.
        master_tags = set(opts.master_voicing_style_tags)
        hits = sum(1 for tag in voicing.voicingStyle if tag in master_tags)
        if hits > 0:
            master_boost = float(min(hits, 2) * 30)

    return ScoreBreakdown(
        quality_match=quality_match,
        filter_category=filter_category,
        category_default=category_default,
        melody_bonus=melody_bonus,
        bass_bonus=bass_bonus,
        distance_penalty=distance_penalty,
        same_category_fret=same_category_fret,
        mute_penalty=mute_penalty,
        fret_3_to_7=fret_3_to_7,
        difficulty_penalty=difficulty_penalty,
        profile_category_weight=profile_category_weight,
        profile_quality_boost=profile_quality_boost,
        mode_delta=mode_delta,
        curated_boost=curated_boost,
        master_boost=master_boost,
    )


__all__ = [
    "ScoreBreakdown",
    "ScoringOpts",
    "compute_mode_delta",
    "score_candidate",
    "signature_key",
]
