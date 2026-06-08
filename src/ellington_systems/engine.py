"""Phase 4 — `Engine.rank`: the top-level entry point that ties Phases
1, 2, and 3 together and emits an `EngineResponse` matching shim
CLI #400's JSON shape.

The phases referenced in the design note Step 4 architecture:

- **Phase 1 (CandidateGenerator):** filter ``corpus.voicings`` by the
  request's chord symbol + tuning string-count. Per the design note's
  A3 assumption, the spike uses ``voicings.json`` as the candidate
  set; on-demand geometry generation is deferred until shim CLI #400
  confirms the candidate-set source.
- **Phase 2 (BaseScorer):** call ``scoring.score_candidate`` on each
  candidate, returning a ``ScoreBreakdown`` with 15 per-component
  values.
- **Phase 3 (PayloadDispatcher):** walk the master's
  ``works[*].systems[*].traversal_rules[]`` and
  ``modification_rules[]`` (when ``systems[]`` is present), dispatch
  each ``engine_payload`` through the registry, accumulate
  ``PayloadDelta``s.
- **Phase 4 (Aggregator, this file):** collapse the 15 Phase 2
  components into the shim's 3-bucket ``ScoreComponents``
  (``base`` / ``master_boost`` / ``tolerance_match``); sort by total
  score; emit ``EngineResponse``.

## ScoreBreakdown → ScoreComponents collapse

The shim's contract carries ``score_components.{base, master_boost,
tolerance_match}``. The 15 Phase 2 components map as:

- ``master_boost`` ← ``ScoreBreakdown.master_boost``  (1:1)
- ``tolerance_match`` ← sum of Phase 3 ``PayloadDelta.score_delta``
  for ``status="applied"`` deltas (reserved bucket; design note
  Phase 4 description allocates it for Phase 3 contributions)
- ``base`` ← everything else from ``ScoreBreakdown``

This collapse is reversible at debug time via the
``EnginePayload.notes`` field on each ``PayloadDelta`` — the
per-component breakdown is preserved in the dispatcher's per-payload
notes if a caller wants to drill down.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .corpus import Corpus, parse_chord_symbol
from .dispatcher import PayloadDispatcherRegistry
from .master_store import collect_voicing_style_tags
from .models import (
    EnginePayload,
    EngineRequest,
    EngineResponse,
    PayloadDelta,
    RankedVoicing,
    ScoreComponents,
    VersionInfo,
    Voicing,
)
from .scoring import ScoreBreakdown, ScoringOpts, score_candidate


def _phase1_filter_candidates(
    voicings: list[Voicing],
    chord_symbol: str,
    *,
    max_strings: int | None = None,
    filter_category: str | None = None,
) -> list[Voicing]:
    """Phase 1 — port of the candidate-filter subset of
    ``ChordSelector.findAllVoicings`` (``plugin/model/ChordSelector.js:379-413``).

    Mirrors the JS line-by-line per the [Phase 1 alignment ticket #10](
    https://github.com/siege-analytics/ellington-systems/issues/10) so the
    oracle diff against shim CLI #400 can converge to ranking exact-match.

    The JS function also does scoring + sorting after the filter; that work
    lives in ``Engine.rank`` (Phase 2 + Phase 4) so this Python function
    implements only the candidate-filter subset.

    Behaviour:

    1. **Strings ceiling**: ``v.strings <= max_strings`` (default 7 per
       JS ``opts.maxStrings || 7``).
    2. **Root filter**: ``v.root == "C"`` (canonical "transpose me"
       voicings) OR ``v.root == target_root`` (already-transposed).
    3. **Admission**: ``v.chord_quality == quality`` OR
       ``v.category == "quartal"`` (the quartal fallback inclusion).
    4. **Category-filter gate** (when ``filter_category`` is set):
       skip ``v`` IFF ``v.category != filter_category`` AND
       ``v.chord_quality == quality``. Voicings admitted via the
       quartal arm pass this gate regardless.
    5. **Shape dedup**: build a key
       ``f"{chord_quality}|{fret_number}|{string:fret,string:fret,...}"``
       — note the trailing comma per JS line 398. First-occurrence
       wins; later duplicates are silently dropped.
    6. **Zero-match category fallback** (JS lines 405-413): if the
       first pass yielded zero candidates AND ``filter_category`` was
       set, run a second pass WITHOUT the category restriction. Dedup
       is NOT applied on the second pass (the JS doesn't either).

    Notable differences from the previous stub:

    - **Drops ``also_qualities`` consultation.** The shim does not
      consult ``v.also_qualities`` either, so this divergence is
      removed in the alignment. Voicings whose ``chord_quality`` does
      not exactly match the request — even if their ``also_qualities``
      list contains the requested quality — are NOT admitted by Phase 1.
    - **Drops ``filterContext`` + ``contextStringCounts``** support
      that the JS (lines 382-385) uses to cap ``maxStrings`` further.
      Ellington has no ``filter_context`` concept today; the branch is
      inert in practice. Add when the concept lands.
    """
    target_root, quality = parse_chord_symbol(chord_symbol)
    effective_max = max_strings if max_strings is not None else 7

    candidates: list[Voicing] = []
    seen_shapes: set[str] = set()
    for v in voicings:
        if (v.strings or 6) > effective_max:
            continue
        if v.root != "C" and v.root != target_root:
            continue
        if v.chord_quality == quality or v.category == "quartal":
            if (
                filter_category is not None
                and v.category != filter_category
                and v.chord_quality == quality
            ):
                continue
            # Shape dedup key — JS line 398: trailing comma per dot.
            dots_str = "".join(f"{d.string}:{d.fret}," for d in (v.dots or []))
            shape_key = f"{v.chord_quality}|{v.fret_number or 0}|{dots_str}"
            if shape_key in seen_shapes:
                continue
            seen_shapes.add(shape_key)
            candidates.append(v)

    # Zero-match category-fallback retry per JS lines 405-413.
    if not candidates and filter_category is not None:
        for v in voicings:
            if v.chord_quality != quality and v.category != "quartal":
                continue
            if v.root != "C" and v.root != target_root:
                continue
            if (v.strings or 6) > effective_max:
                continue
            candidates.append(v)

    return candidates


def _walk_payloads(master: dict[str, Any]) -> list[tuple[str, EnginePayload]]:
    """Phase 3 input — collect every ``engine_payload`` in a master's
    ``systems[]`` tree.

    Returns a list of ``(principle_id, payload)`` tuples where the
    principle_id is the ``rule.id`` if present (so PayloadDelta
    ``applied_principle`` is meaningful provenance).

    Returns an empty list for a master with no ``systems[]`` — that's
    the design note's A7 case (5 of 29 masters are ``principles[]``-
    only at SHA 628ed30; for them Phase 3 is a no-op).
    """
    payloads: list[tuple[str, EnginePayload]] = []
    works = master.get("works") or []
    for work in works:
        systems = work.get("systems") or []
        for system in systems:
            system_id = system.get("id", "unknown-system")
            for rule_key in ("traversal_rules", "modification_rules"):
                rules = system.get(rule_key) or []
                for rule in rules:
                    rule_id = rule.get("id", f"{system_id}/unknown-rule")
                    payload_dict = rule.get("engine_payload")
                    if payload_dict and isinstance(payload_dict, dict):
                        try:
                            payload = EnginePayload.model_validate(payload_dict)
                            payloads.append((rule_id, payload))
                        except Exception:  # noqa: BLE001
                            # Per design note edge case: schema violation
                            # at bootstrap is OK to skip silently per
                            # walk; bootstrap-level validation belongs
                            # to a separate validator (out of spike).
                            continue
    return payloads


@dataclass(frozen=True)
class _PhaseOutput:
    """Internal per-candidate accumulator used by ``rank``."""

    voicing: Voicing
    breakdown: ScoreBreakdown
    payload_deltas: list[PayloadDelta]
    applied_kind: str | None
    applied_principles: list[str]
    phase3_score: float


class Engine:
    """The Ellington engine. Construct once, call ``rank`` per request."""

    def __init__(
        self,
        corpus: Corpus,
        registry: PayloadDispatcherRegistry,
        engine_version: VersionInfo,
        masters_version: VersionInfo,
        voicings_version: VersionInfo,
    ) -> None:
        """Construct an engine bound to a corpus snapshot and registry.

        Args:
            corpus: loaded via ``Corpus.from_plugin_clone`` or
                ``Corpus.from_env``.
            registry: typically ``dispatcher.build_default_registry()``
                for the spike's three-kind demo.
            engine_version: ``VersionInfo`` for the Ellington binding
                this engine implements. Emitted in every
                ``EngineResponse`` so diff-time version mismatch is
                detectable (Tiger 6 mitigation). The ``clean`` flag
                catches dev-running-against-uncommitted-tree silently.
            masters_version: ``VersionInfo`` for the masters.json the
                corpus was loaded from. For the spike's frozen oracle,
                ``sha`` should reference a commit at or before plugin
                SHA ``628ed30…``.
            voicings_version: ``VersionInfo`` for voicings.json the
                corpus was loaded from. Matches the shim's emission.
        """
        self._corpus = corpus
        self._registry = registry
        self._engine_version = engine_version
        self._masters_version = masters_version
        self._voicings_version = voicings_version

    def rank(self, request: EngineRequest) -> EngineResponse:
        """Compute the ranked-voicings response for one request.

        Pipeline:

        1. Phase 1 filter on string count + chord quality.
        2. Phase 2 score each surviving candidate.
        3. Phase 3 dispatch payloads (if master has ``systems[]``).
        4. Phase 4 collapse and sort.

        Raises:
            ``KeyError``: when ``request.master_id`` is set but the
                master does not exist in the corpus. Mirrors the
                design note's ``MasterNotFoundError`` edge case
                (raised, not silently degraded).
        """
        master: dict[str, Any] | None = None
        if request.master_id is not None:
            master = self._corpus.masters_by_id.get(request.master_id)
            if master is None:
                raise KeyError(
                    f"master_id={request.master_id!r} not found in corpus "
                    f"(loaded {len(self._corpus.masters_by_id)} masters; "
                    f"check spelling against the plugin's masters.json)"
                )

        # Phase 1 — strings filter uses len(tuning) as the upper bound.
        # When request.tuning is the compact-string form ("EADGBE"), len()
        # gives the same 6 the list-form would; for a custom tuning with
        # multi-char pitches passed in list form, len() yields the string
        # count directly. category_filter wires the JS engine's
        # opts.filterCategory through to the filter.
        candidates = _phase1_filter_candidates(
            self._corpus.voicings,
            request.chord_symbol,
            max_strings=len(request.tuning),
            filter_category=request.category_filter,
        )

        # Phase 3 prep — collect payloads once per request, not per candidate.
        payloads = _walk_payloads(master) if master else []
        master_tags = collect_voicing_style_tags(master) if master else []

        # Per-candidate Phase 2 + 3
        outputs: list[_PhaseOutput] = []
        for v in candidates:
            opts = ScoringOpts(master_voicing_style_tags=master_tags)
            breakdown = score_candidate(
                voicing=v,
                target_root=parse_chord_symbol(request.chord_symbol)[0],
                quality=parse_chord_symbol(request.chord_symbol)[1],
                melody_target=-1,
                bass_target=-1,
                ref=None,
                opts=opts,
            )

            # Phase 3 — walk payloads per candidate; thread principle_id.
            payload_deltas: list[PayloadDelta] = []
            applied_principles: list[str] = []
            applied_kind: str | None = None
            phase3_score = 0.0
            for principle_id, payload in payloads:
                context = {"principle_id": principle_id, "request": request}
                delta = self._registry.evaluate(payload, v, context)
                payload_deltas.append(delta)
                if delta.status == "applied":
                    phase3_score += delta.score_delta
                    if delta.applied_principle is not None:
                        applied_principles.append(delta.applied_principle)
                    if applied_kind is None:
                        applied_kind = payload.kind

            outputs.append(
                _PhaseOutput(
                    voicing=v,
                    breakdown=breakdown,
                    payload_deltas=payload_deltas,
                    applied_kind=applied_kind,
                    applied_principles=applied_principles,
                    phase3_score=phase3_score,
                )
            )

        # Phase 4 — collapse + sort + emit
        # Sort tuples first so the rank assignment lines up with the final
        # array order (RankedVoicing.rank is 1-indexed dense, matching the
        # shim's contract).
        scored_tuples: list[tuple[float, _PhaseOutput, ScoreComponents]] = []
        for o in outputs:
            score_components = ScoreComponents(
                base=(
                    o.breakdown.total
                    - o.breakdown.master_boost  # already its own bucket
                ),
                master_boost=o.breakdown.master_boost,
                tolerance_match=o.phase3_score,
            )
            total = (
                score_components.base
                + score_components.master_boost
                + score_components.tolerance_match
            )
            scored_tuples.append((total, o, score_components))

        scored_tuples.sort(key=lambda t: t[0], reverse=True)

        ranked: list[RankedVoicing] = [
            RankedVoicing(
                voicing_id=o.voicing.id,
                rank=index + 1,
                score=total,
                payload_kind=o.applied_kind,
                score_components=score_components,
                applied_principles=o.applied_principles,
            )
            for index, (total, o, score_components) in enumerate(scored_tuples)
        ]

        return EngineResponse(
            request=request,
            ranked_voicings=ranked,
            engine_version=self._engine_version,
            masters_version=self._masters_version,
            voicings_version=self._voicings_version,
        )


__all__ = ["Engine"]
