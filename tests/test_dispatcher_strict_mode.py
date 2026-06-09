"""Strict-mode + namespace-aware logging tests for `PayloadDispatcherRegistry`.

Per `siege-analytics/ellington-systems#14` (partition-with-strict-flag resolution
from `musescore4-chord-library-plugin#412`):

  - ``_pending:*`` kinds without an evaluator: soft-skip in ANY mode,
    INFO-logged. ``_pending:`` is the plugin's explicit "no contract"
    namespace.
  - Canonical (non-``_pending:``) kinds without an evaluator:
      * ``strict_mode=False`` (default): soft-skip, WARN-logged with
        actionable message + epic link.
      * ``strict_mode=True`` (CI/tests): raise ``EvaluatorNotRegistered``.
  - Default constructor MUST be ``strict_mode=False`` so production
    paths can't accidentally crash on a plugin-side kind they haven't
    ported.

The existing inert-on-unknown contract (assertion in
`TestRegistryBasics.test_unregistered_kind_emits_inert`) remains intact
for non-strict mode.
"""

from __future__ import annotations

import logging

import pytest

from ellington_systems.dispatcher import (
    EvaluatorNotRegistered,
    PayloadDispatcherRegistry,
)
from ellington_systems.models import EnginePayload, Voicing


def _voicing() -> Voicing:
    # Mirrors `tests/test_dispatcher.py::_voicing` field shape (Voicing
    # has many required fields beyond what the dispatcher inspects).
    return Voicing(
        id="test-voicing",
        name="test",
        chord_quality="maj7",
        root="C",
        category="shell",
        strings=6,
        fret_number=5,
        visible_frets=4,
        notes=["C", "E", "G", "B"],
        intervals=["1", "3", "5", "7"],
    )


class TestPendingKindAlwaysSoftSkips:
    def test_pending_kind_soft_skip_in_non_strict_mode(self, caplog) -> None:
        reg = PayloadDispatcherRegistry()
        caplog.set_level(logging.INFO, logger="ellington_systems.dispatcher")
        delta = reg.evaluate(
            EnginePayload(kind="_pending:some-overflow-kind"), _voicing(), {}
        )
        assert delta.status == "inert"
        assert delta.notes is not None and "_pending" in delta.notes
        info_records = [r for r in caplog.records if r.levelno == logging.INFO]
        assert any("_pending:" in r.getMessage() for r in info_records)

    def test_pending_kind_soft_skip_in_strict_mode(self, caplog) -> None:
        """`_pending:*` MUST never raise — strict_mode shouldn't affect them."""
        reg = PayloadDispatcherRegistry(strict_mode=True)
        caplog.set_level(logging.INFO, logger="ellington_systems.dispatcher")
        delta = reg.evaluate(
            EnginePayload(kind="_pending:another-overflow"), _voicing(), {}
        )
        assert delta.status == "inert"
        assert delta.notes is not None and "_pending" in delta.notes


class TestCanonicalUnknownInStrictMode:
    def test_canonical_unknown_strict_raises_evaluator_not_registered(self) -> None:
        reg = PayloadDispatcherRegistry(strict_mode=True)
        with pytest.raises(EvaluatorNotRegistered) as ctx:
            reg.evaluate(EnginePayload(kind="VoiceMotion"), _voicing(), {})
        assert "VoiceMotion" in str(ctx.value)

    def test_evaluator_not_registered_is_keyerror_subclass(self) -> None:
        # Callers may catch KeyError generically; the new class shouldn't
        # break that contract.
        assert issubclass(EvaluatorNotRegistered, KeyError)


class TestCanonicalUnknownInNonStrictMode:
    def test_canonical_unknown_non_strict_returns_inert(self, caplog) -> None:
        reg = PayloadDispatcherRegistry()  # default strict_mode=False
        caplog.set_level(logging.WARNING, logger="ellington_systems.dispatcher")
        delta = reg.evaluate(
            EnginePayload(kind="PositionContinuity"), _voicing(), {}
        )
        assert delta.status == "inert"
        assert delta.notes is not None and "unregistered-canonical" in delta.notes

    def test_canonical_unknown_non_strict_warns_with_port_queue_link(
        self, caplog
    ) -> None:
        reg = PayloadDispatcherRegistry()
        caplog.set_level(logging.WARNING, logger="ellington_systems.dispatcher")
        reg.evaluate(EnginePayload(kind="FamilyCoherence"), _voicing(), {})
        warn_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warn_records, "expected at least one WARN log record"
        msg = warn_records[-1].getMessage()
        assert "FamilyCoherence" in msg
        assert "ellington-systems#13" in msg  # actionable: port queue epic


class TestStrictModeDefault:
    def test_default_constructor_is_non_strict(self) -> None:
        reg = PayloadDispatcherRegistry()
        assert reg.strict_mode is False

    def test_explicit_non_strict_constructor(self) -> None:
        reg = PayloadDispatcherRegistry(strict_mode=False)
        assert reg.strict_mode is False

    def test_strict_mode_does_not_affect_registered_evaluators(self, caplog) -> None:
        """Evaluators that ARE registered run normally in strict mode —
        strict_mode only changes the unregistered-canonical branch.
        """
        reg = PayloadDispatcherRegistry(strict_mode=True)
        # Register a no-op evaluator for the canonical kind
        def _noop_evaluator(payload, voicing, context):
            from ellington_systems.models import PayloadDelta
            return PayloadDelta(
                status="applied",
                score_delta=1.0,
                applied_principle=None,
                notes="ok",
            )
        reg.register("VoiceMotion", _noop_evaluator)
        delta = reg.evaluate(EnginePayload(kind="VoiceMotion"), _voicing(), {})
        assert delta.status == "applied"
        assert delta.score_delta == 1.0
