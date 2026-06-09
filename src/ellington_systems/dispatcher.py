"""Phase 3 — `PayloadDispatcher`: the systems-with-three-layers runtime
that the plugin schema designed for but plugin JS does not yet run.

Per the Investigation Fact Sheet (Finding 1) and the design note's
"What does NOT exist" section: the plugin's 1033 `engine_payload`
instances are inert data in JavaScript. Ellington's Goal B is to be
the system that actually executes them. This module is that engine.

## Architecture

The dispatcher is a registry mapping `engine_payload.kind` strings to
evaluator callables. For each `engine_payload` encountered in a
master's `traversal_rules[]` or `modification_rules[]`, the dispatcher
looks up the registered evaluator and calls it with the
`(payload, voicing, context)` triple, receiving a `PayloadDelta` in
return.

Unregistered kinds (including any `_pending:` kind without a registered
implementation) produce `PayloadDelta(status="inert", score_delta=0.0)`.
This mirrors the plugin's silent round-trip behaviour per Fact Sheet
Entity 5/6 — data with unknown kinds round-trips without crashing.

Evaluators that raise are caught: `PayloadDelta(status="rejected", ...)`
is emitted with the exception captured in `notes`. One bad evaluator
does not sink the entire request (design note Step 4 edge case).

## Goal B's three demonstration kinds

- `SubstitutionExpand` — canonical 12-kind enum member, 134 corpus
  instances. Implemented in `evaluators.substitution_expand`.
- `_pending:inner-voice-counterpoint` — `_pending:` overflow kind, 8
  corpus instances, closest-to-graduating to canonical per the
  cross-agent reply. Implemented in `evaluators.inner_voice_counterpoint`.
- `_pending:melodic-cell-traversal` — Ellington-local Pat Martino kind
  with NO plugin corpus instances. Demonstrates that the dispatcher
  accepts kinds the plugin's schema doesn't ship (Goal B
  expansibility claim). Implemented in
  `evaluators.melodic_cell_traversal`.

Together they cover: canonical + pending + plugin-unknown, the three
states a payload kind can be in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

from .models import EnginePayload, PayloadDelta, Voicing


_log = logging.getLogger(__name__)


class EvaluatorNotRegistered(KeyError):
    """Raised by `PayloadDispatcherRegistry` in `strict_mode=True` when a
    canonical (non-``_pending:``) kind has no registered evaluator.

    Production dispatch paths use ``strict_mode=False`` (default) and
    silently soft-skip; tests / CI use ``strict_mode=True`` to catch
    drift between the plugin's kind vocabulary and Ellington's port
    coverage. Resolution from
    `musescore4-chord-library-plugin#412`_ — see
    `siege-analytics/ellington-systems#13`_ for the port queue.

    .. _musescore4-chord-library-plugin#412: https://github.com/siege-analytics/musescore4-chord-library-plugin/issues/412
    .. _siege-analytics/ellington-systems#13: https://github.com/siege-analytics/ellington-systems/issues/13
    """


@runtime_checkable
class PayloadEvaluator(Protocol):
    """Callable contract for a payload-kind evaluator.

    An evaluator receives the parsed `EnginePayload`, the candidate
    `Voicing` being scored, and a free-form `context` dict (mirroring
    the JS `opts` bag — tuning, mode, master_id, anything Phase 3 wants
    in scope). It returns a `PayloadDelta` indicating whether the rule
    fired, by how much, and which principle ID can be credited.
    """

    def __call__(
        self,
        payload: EnginePayload,
        voicing: Voicing,
        context: Mapping[str, Any],
    ) -> PayloadDelta: ...


@dataclass(frozen=True)
class _DispatchOutcome:
    """Internal — the result of one dispatch call, including the kind
    that fired. Used by the dispatcher's diagnostic surface (debug
    logs, oracle-diff drill-down) but not exposed in the public delta."""

    kind: str
    delta: PayloadDelta


@dataclass
class PayloadDispatcherRegistry:
    """Registry of `engine_payload.kind` → `PayloadEvaluator`.

    Mutable on purpose — call sites register evaluators at engine
    bootstrap. The registry itself is not threadsafe; concurrent
    bootstrap is unusual but worth flagging.
    """

    _evaluators: dict[str, PayloadEvaluator] = field(default_factory=dict)
    strict_mode: bool = False
    """When ``True``, unregistered canonical kinds raise
    :class:`EvaluatorNotRegistered` instead of returning an inert
    delta. ``_pending:*`` kinds always soft-skip regardless. Default
    ``False`` is production-safe; tests / CI flip it.
    """

    def register(self, kind: str, evaluator: PayloadEvaluator) -> None:
        """Register an evaluator for a given `engine_payload.kind`.

        Re-registration replaces the prior evaluator (no error). This
        is intentional: tests may need to swap stubs, and `_pending:`
        kinds may graduate to canonical names with new implementations.
        """
        self._evaluators[kind] = evaluator

    def unregister(self, kind: str) -> None:
        """Remove an evaluator. No-op if not registered."""
        self._evaluators.pop(kind, None)

    def is_registered(self, kind: str) -> bool:
        return kind in self._evaluators

    def registered_kinds(self) -> list[str]:
        """Return the sorted list of kinds with registered evaluators."""
        return sorted(self._evaluators.keys())

    def evaluate(
        self,
        payload: EnginePayload,
        voicing: Voicing,
        context: Mapping[str, Any],
    ) -> PayloadDelta:
        """Dispatch one payload through its registered evaluator.

        Returns:
            - `PayloadDelta(status="applied", ...)` — evaluator fired
              and produced a positive contribution.
            - `PayloadDelta(status="inert", ...)` — no registered
              evaluator OR evaluator chose to do nothing.
            - `PayloadDelta(status="rejected", ...)` — evaluator raised;
              the exception is captured in `notes`.
        """
        evaluator = self._evaluators.get(payload.kind)
        if evaluator is not None:
            try:
                return evaluator(payload, voicing, context)
            except Exception as exc:  # noqa: BLE001 — design intent: catch any failure
                return PayloadDelta(
                    status="rejected",
                    score_delta=0.0,
                    applied_principle=None,
                    notes=f"error:{payload.kind}:{exc!r}",
                )
        # Unknown kind. Branch by namespace per plugin#412 partition policy.
        if payload.kind.startswith("_pending:"):
            # `_pending:*` is plugin's explicit "no contract" namespace.
            # Soft-skip in any mode; log at INFO so visibility is cheap.
            _log.info(
                "dispatcher: skipping _pending: kind %r (no contract — see plugin#412)",
                payload.kind,
            )
            return PayloadDelta(
                status="inert",
                score_delta=0.0,
                applied_principle=None,
                notes=f"_pending:{payload.kind}",
            )
        # Canonical (non-`_pending:`) kind with no registered evaluator.
        # strict_mode flips between production-safe (soft-skip + WARN) and
        # CI-strict (raise so test runs catch drift).
        if self.strict_mode:
            raise EvaluatorNotRegistered(payload.kind)
        _log.warning(
            "dispatcher: unregistered canonical kind %r — no port yet "
            "(see siege-analytics/ellington-systems#13)",
            payload.kind,
        )
        return PayloadDelta(
            status="inert",
            score_delta=0.0,
            applied_principle=None,
            notes=f"unregistered-canonical:{payload.kind!r}",
        )

    def evaluate_many(
        self,
        payloads: list[EnginePayload],
        voicing: Voicing,
        context: Mapping[str, Any],
    ) -> list[PayloadDelta]:
        """Dispatch a list of payloads in order. Useful for walking a
        master's `traversal_rules[]` or `modification_rules[]`.
        Aggregation (summing score_deltas, collecting applied
        principles) is the caller's responsibility — Phase 3 does not
        decide composition semantics in the spike scope.
        """
        return [self.evaluate(p, voicing, context) for p in payloads]


def build_default_registry() -> PayloadDispatcherRegistry:
    """Construct a registry pre-wired with Ellington's spike evaluators.

    Order of registration is irrelevant to behaviour — `kind`-keyed
    lookups don't care. Including all three at once is the
    "demonstration triple" referenced in the design note's Goal B.
    """
    # Local imports keep the dispatcher module free of import cycles
    # and let evaluator modules be optional in future deployments.
    from .evaluators.inner_voice_counterpoint import inner_voice_counterpoint
    from .evaluators.melodic_cell_traversal import melodic_cell_traversal
    from .evaluators.substitution_expand import substitution_expand

    registry = PayloadDispatcherRegistry()
    registry.register("SubstitutionExpand", substitution_expand)
    registry.register("_pending:inner-voice-counterpoint", inner_voice_counterpoint)
    registry.register("_pending:melodic-cell-traversal", melodic_cell_traversal)
    return registry


__all__ = [
    "PayloadDispatcherRegistry",
    "PayloadEvaluator",
    "build_default_registry",
]
