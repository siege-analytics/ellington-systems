"""Tests for the Phase 3 PayloadDispatcher registry — Goal B's core."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from ellington_systems.dispatcher import (
    PayloadDispatcherRegistry,
    build_default_registry,
)
from ellington_systems.models import EnginePayload, PayloadDelta, Voicing


# ---------------------------------------------------------------------------
# Voicing factory for terse tests
# ---------------------------------------------------------------------------


def _voicing(**overrides: Any) -> Voicing:
    base: dict[str, Any] = {
        "id": "test-voicing",
        "name": "test",
        "chord_quality": "maj7",
        "root": "C",
        "category": "shell",
        "strings": 6,
        "fret_number": 5,
        "visible_frets": 4,
        "notes": ["C", "E", "G", "B"],
        "intervals": ["1", "3", "5", "7"],
    }
    base.update(overrides)
    return Voicing(**base)


# ---------------------------------------------------------------------------
# Registry mechanics
# ---------------------------------------------------------------------------


class TestRegistryBasics:
    def test_unregistered_kind_emits_inert(self) -> None:
        reg = PayloadDispatcherRegistry()
        delta = reg.evaluate(EnginePayload(kind="UnknownKind"), _voicing(), {})
        assert delta.status == "inert"
        assert delta.score_delta == 0.0
        # Post-#412 partition: canonical-unknown gets a distinct notes tag
        # so logs / oracle drill-down can tell "we should have ported this"
        # apart from "_pending: was meant to be skipped" (see also the
        # TestPendingKindRoundTripWithoutEvaluator suite below).
        assert delta.notes is not None and "unregistered-canonical" in delta.notes

    def test_register_and_evaluate(self) -> None:
        reg = PayloadDispatcherRegistry()

        def always_applied(
            payload: EnginePayload, voicing: Voicing, context: Mapping[str, Any]
        ) -> PayloadDelta:
            return PayloadDelta(status="applied", score_delta=7.0)

        reg.register("MyKind", always_applied)
        delta = reg.evaluate(EnginePayload(kind="MyKind"), _voicing(), {})
        assert delta.status == "applied"
        assert delta.score_delta == 7.0

    def test_re_registration_replaces_prior(self) -> None:
        reg = PayloadDispatcherRegistry()
        reg.register("K", lambda p, v, c: PayloadDelta(status="applied", score_delta=1.0))
        reg.register("K", lambda p, v, c: PayloadDelta(status="applied", score_delta=99.0))
        delta = reg.evaluate(EnginePayload(kind="K"), _voicing(), {})
        assert delta.score_delta == 99.0

    def test_unregister(self) -> None:
        reg = PayloadDispatcherRegistry()
        reg.register("K", lambda p, v, c: PayloadDelta(status="applied", score_delta=1.0))
        assert reg.is_registered("K")
        reg.unregister("K")
        assert not reg.is_registered("K")
        delta = reg.evaluate(EnginePayload(kind="K"), _voicing(), {})
        assert delta.status == "inert"

    def test_unregister_unknown_is_noop(self) -> None:
        reg = PayloadDispatcherRegistry()
        reg.unregister("never-registered")  # must not raise

    def test_registered_kinds_returns_sorted(self) -> None:
        reg = PayloadDispatcherRegistry()
        reg.register("Z", lambda p, v, c: PayloadDelta(status="inert"))
        reg.register("A", lambda p, v, c: PayloadDelta(status="inert"))
        reg.register("M", lambda p, v, c: PayloadDelta(status="inert"))
        assert reg.registered_kinds() == ["A", "M", "Z"]


class TestEvaluatorRaisesIsRejected:
    """Pre-mortem mandate: one bad evaluator does not sink the entire request."""

    def test_raising_evaluator_yields_rejected(self) -> None:
        reg = PayloadDispatcherRegistry()

        def bad(p: EnginePayload, v: Voicing, c: Mapping[str, Any]) -> PayloadDelta:
            raise ValueError("intentional failure")

        reg.register("BadKind", bad)
        delta = reg.evaluate(EnginePayload(kind="BadKind"), _voicing(), {})
        assert delta.status == "rejected"
        assert delta.score_delta == 0.0
        assert delta.notes is not None
        assert "error:BadKind:" in delta.notes
        assert "ValueError" in delta.notes


class TestEvaluateMany:
    def test_returns_one_delta_per_payload(self) -> None:
        reg = build_default_registry()
        payloads = [
            EnginePayload(kind="SubstitutionExpand", target_type="maj7"),
            EnginePayload(kind="_pending:inner-voice-counterpoint", voice_count=4),
            EnginePayload(kind="UnknownKind"),
        ]
        deltas = reg.evaluate_many(payloads, _voicing(), {})
        assert len(deltas) == 3
        assert deltas[0].status == "applied"
        assert deltas[1].status == "applied"
        assert deltas[2].status == "inert"


# ---------------------------------------------------------------------------
# build_default_registry — Goal B's demonstration triple is wired in
# ---------------------------------------------------------------------------


class TestDefaultRegistry:
    def test_all_three_demo_kinds_registered(self) -> None:
        reg = build_default_registry()
        kinds = reg.registered_kinds()
        assert "SubstitutionExpand" in kinds
        assert "_pending:inner-voice-counterpoint" in kinds
        # The Ellington-LOCAL kind that proves the expansibility claim
        assert "_pending:melodic-cell-traversal" in kinds

    def test_canonical_kind_fires(self) -> None:
        reg = build_default_registry()
        payload = EnginePayload(kind="SubstitutionExpand", target_type="maj7")
        delta = reg.evaluate(payload, _voicing(chord_quality="maj7"), {})
        assert delta.status == "applied"

    def test_pending_kind_fires_when_constraint_satisfied(self) -> None:
        reg = build_default_registry()
        # 4 notes, 0 mutes → sounding=4 → satisfies voice_count=3
        payload = EnginePayload(kind="_pending:inner-voice-counterpoint", voice_count=3)
        delta = reg.evaluate(payload, _voicing(notes=["C", "E", "G", "B"], mutes=[]), {})
        assert delta.status == "applied"

    def test_ellington_local_kind_fires(self) -> None:
        reg = build_default_registry()
        # Pat Martino "harmonic-structure-dictates-melodic-choice" cell
        payload = EnginePayload(
            kind="_pending:melodic-cell-traversal",
            cell="dorian-minor-ii-v",
            target_intervals=["1", "b3", "5", "b7"],
        )
        # Voicing has 4 matches against target — well above the 2-hit threshold.
        delta = reg.evaluate(
            payload,
            _voicing(intervals=["1", "b3", "5", "b7"]),
            {"principle_id": "pat-martino/harmonic-structure-dictates-melodic-choice"},
        )
        assert delta.status == "applied"
        assert delta.applied_principle == "pat-martino/harmonic-structure-dictates-melodic-choice"


# ---------------------------------------------------------------------------
# Pending-kind round-trip — Goal B's data-first / code-catches-up claim
# ---------------------------------------------------------------------------


class TestPendingKindRoundTripWithoutEvaluator:
    """Per Fact Sheet Entity 5/6 + design note A9: the plugin treats
    `_pending:` kinds without evaluators as silent round-trip. The
    Python dispatcher MUST mirror this — an unregistered `_pending:`
    kind emits inert + a notes message, never crashes.
    """

    def test_unregistered_pending_kind_yields_inert(self) -> None:
        reg = PayloadDispatcherRegistry()
        delta = reg.evaluate(
            EnginePayload(kind="_pending:completely-new-kind"), _voicing(), {}
        )
        assert delta.status == "inert"
        assert delta.score_delta == 0.0

    def test_unregistered_pending_kind_with_ad_hoc_fields_yields_inert(self) -> None:
        # The corpus's `_pending:inner-voice-counterpoint` carries voice_count,
        # preserve_independence, bass_role per Fact Sheet Entity 6. An
        # unregistered kind with similar ad-hoc keys must still round-trip
        # without rejection — the model layer's extra="allow" makes the
        # payload parseable; the dispatcher must not crash on the parse.
        payload = EnginePayload(
            kind="_pending:future-melodic-thing",
            voice_count=3,
            preserve_independence=True,
            arbitrary_future_field=[1, 2, 3],
        )
        reg = PayloadDispatcherRegistry()
        delta = reg.evaluate(payload, _voicing(), {})
        assert delta.status == "inert"


# ---------------------------------------------------------------------------
# Direct evaluator tests — each kind, in isolation
# ---------------------------------------------------------------------------


class TestSubstitutionExpand:
    """Direct tests for `evaluators.substitution_expand`."""

    def test_target_type_match_yields_score_delta_8(self) -> None:
        from ellington_systems.evaluators.substitution_expand import (
            substitution_expand,
        )

        payload = EnginePayload(kind="SubstitutionExpand", target_type="maj7")
        delta = substitution_expand(payload, _voicing(chord_quality="maj7"), {})
        assert delta.status == "applied"
        assert delta.score_delta == 8.0

    def test_source_type_match_yields_score_delta_4(self) -> None:
        from ellington_systems.evaluators.substitution_expand import (
            substitution_expand,
        )

        # When source_type matches and target_type doesn't, the weaker
        # source signal fires.
        payload = EnginePayload(kind="SubstitutionExpand", source_type="dom7")
        delta = substitution_expand(payload, _voicing(chord_quality="dom7"), {})
        assert delta.status == "applied"
        assert delta.score_delta == 4.0

    def test_target_type_wins_when_both_match(self) -> None:
        from ellington_systems.evaluators.substitution_expand import (
            substitution_expand,
        )

        payload = EnginePayload(
            kind="SubstitutionExpand",
            target_type="maj7",
            source_type="maj7",
        )
        delta = substitution_expand(payload, _voicing(chord_quality="maj7"), {})
        # target_type is checked first → +8.0 wins
        assert delta.score_delta == 8.0

    def test_no_match_yields_inert(self) -> None:
        from ellington_systems.evaluators.substitution_expand import (
            substitution_expand,
        )

        payload = EnginePayload(kind="SubstitutionExpand", target_type="m7b5")
        delta = substitution_expand(payload, _voicing(chord_quality="maj7"), {})
        assert delta.status == "inert"

    def test_no_target_or_source_type_yields_inert(self) -> None:
        from ellington_systems.evaluators.substitution_expand import (
            substitution_expand,
        )

        # Many corpus instances of SubstitutionExpand carry ONLY kind +
        # one ad-hoc field that this spike doesn't read (e.g. interval,
        # to, from). Those must round-trip without rejection.
        payload = EnginePayload(kind="SubstitutionExpand", interval="tritone")
        delta = substitution_expand(payload, _voicing(), {})
        assert delta.status == "inert"

    def test_principle_id_threaded_through(self) -> None:
        from ellington_systems.evaluators.substitution_expand import (
            substitution_expand,
        )

        payload = EnginePayload(kind="SubstitutionExpand", target_type="maj7")
        delta = substitution_expand(
            payload, _voicing(chord_quality="maj7"), {"principle_id": "x/y"}
        )
        assert delta.applied_principle == "x/y"


class TestInnerVoiceCounterpoint:
    def test_sounding_meets_voice_count_yields_applied(self) -> None:
        from ellington_systems.evaluators.inner_voice_counterpoint import (
            inner_voice_counterpoint,
        )

        payload = EnginePayload(
            kind="_pending:inner-voice-counterpoint", voice_count=3
        )
        # 4 notes, 0 mutes → sounding=4 → satisfies voice_count=3
        delta = inner_voice_counterpoint(
            payload, _voicing(notes=["C", "E", "G", "B"], mutes=[]), {}
        )
        assert delta.status == "applied"
        assert delta.score_delta == 6.0

    def test_mutes_reduce_sounding_count(self) -> None:
        from ellington_systems.evaluators.inner_voice_counterpoint import (
            inner_voice_counterpoint,
        )

        payload = EnginePayload(
            kind="_pending:inner-voice-counterpoint", voice_count=4
        )
        # 4 notes, 2 mutes → sounding=2 → does NOT satisfy voice_count=4
        delta = inner_voice_counterpoint(
            payload, _voicing(notes=["C", "E", "G", "B"], mutes=[1, 2]), {}
        )
        assert delta.status == "inert"

    def test_no_voice_count_yields_inert(self) -> None:
        from ellington_systems.evaluators.inner_voice_counterpoint import (
            inner_voice_counterpoint,
        )

        payload = EnginePayload(
            kind="_pending:inner-voice-counterpoint",
            preserve_independence=True,
            bass_role="root",
        )
        delta = inner_voice_counterpoint(payload, _voicing(), {})
        assert delta.status == "inert"
        assert delta.notes is not None and "voice_count" in delta.notes


class TestMelodicCellTraversal:
    """Goal B's expansibility demonstration — an Ellington-local kind."""

    def test_two_hits_yields_applied(self) -> None:
        from ellington_systems.evaluators.melodic_cell_traversal import (
            melodic_cell_traversal,
        )

        payload = EnginePayload(
            kind="_pending:melodic-cell-traversal",
            cell="ii-v-i",
            target_intervals=["1", "b3", "5", "b7"],
        )
        # Voicing intervals: 1, b3, 5 → 3 hits ≥ 2 threshold.
        delta = melodic_cell_traversal(
            payload, _voicing(intervals=["1", "b3", "5"]), {}
        )
        assert delta.status == "applied"
        assert delta.score_delta == 5.0

    def test_one_hit_yields_inert(self) -> None:
        from ellington_systems.evaluators.melodic_cell_traversal import (
            melodic_cell_traversal,
        )

        payload = EnginePayload(
            kind="_pending:melodic-cell-traversal",
            target_intervals=["1", "b3", "5", "b7"],
        )
        # Voicing intervals: 1, 9 → only 1 hits.
        delta = melodic_cell_traversal(
            payload, _voicing(intervals=["1", "9"]), {}
        )
        assert delta.status == "inert"

    def test_empty_target_intervals_yields_inert(self) -> None:
        from ellington_systems.evaluators.melodic_cell_traversal import (
            melodic_cell_traversal,
        )

        payload = EnginePayload(
            kind="_pending:melodic-cell-traversal", target_intervals=[]
        )
        delta = melodic_cell_traversal(payload, _voicing(), {})
        assert delta.status == "inert"

    def test_voicing_with_no_intervals_yields_inert(self) -> None:
        from ellington_systems.evaluators.melodic_cell_traversal import (
            melodic_cell_traversal,
        )

        payload = EnginePayload(
            kind="_pending:melodic-cell-traversal",
            target_intervals=["1", "b3"],
        )
        delta = melodic_cell_traversal(payload, _voicing(intervals=[]), {})
        assert delta.status == "inert"


# ---------------------------------------------------------------------------
# Goal B's headline claim: dispatcher composes across all three kind states
# ---------------------------------------------------------------------------


class TestGoalBComposition:
    """End-to-end demonstration that the dispatcher composes for:
    - a canonical kind (SubstitutionExpand)
    - a corpus-known `_pending:` kind (inner-voice-counterpoint)
    - an Ellington-LOCAL `_pending:` kind (melodic-cell-traversal)

    Each evaluator emits an independent PayloadDelta; the caller is
    free to aggregate.
    """

    def test_one_voicing_processed_through_all_three_kinds(self) -> None:
        reg = build_default_registry()
        voicing = _voicing(
            chord_quality="maj7",
            notes=["C", "E", "G", "B"],
            intervals=["1", "3", "5", "7"],
        )
        payloads = [
            EnginePayload(kind="SubstitutionExpand", target_type="maj7"),
            EnginePayload(
                kind="_pending:inner-voice-counterpoint", voice_count=3
            ),
            EnginePayload(
                kind="_pending:melodic-cell-traversal",
                target_intervals=["1", "3", "5"],
            ),
        ]
        deltas = reg.evaluate_many(payloads, voicing, {})
        # All three are designed to fire on this voicing.
        statuses = [d.status for d in deltas]
        assert statuses == ["applied", "applied", "applied"]
        # Per-kind deltas distinct.
        assert deltas[0].score_delta == 8.0  # SubstitutionExpand
        assert deltas[1].score_delta == 6.0  # inner-voice-counterpoint
        assert deltas[2].score_delta == 5.0  # melodic-cell-traversal
        # Summed score contribution from Phase 3 for this candidate.
        assert sum(d.score_delta for d in deltas) == 19.0
