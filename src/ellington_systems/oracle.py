"""Oracle-diff harness — bridges Ellington's ``Engine.rank`` to the
plugin-side shim (:doc:`musescore4-chord-library-plugin#400`) for Goal A
validation.

The shim emits the same JSON shape as Ellington's
:class:`~ellington_systems.models.EngineResponse`. This module:

1. Invokes the shim via subprocess for a given request.
2. Parses the shim's JSON into a Pydantic ``EngineResponse``.
3. Diffs that response against Ellington's own ``Engine.rank(request)``,
   per-component, with a configurable absolute tolerance (default
   0.001 — matches the success criterion in the spike design note).
4. Returns a structured ``DiffResult`` listing matching rows, drift
   rows, and missing-on-either-side rows.

## Goal A — what passing means

The spike's Goal A criterion (per ticket #1 success criteria):

    Python port produces the same ranking and score components as
    shim #400 on all 12 fixture masters across the test battery.
    Ranking exact-match required; score-component delta tolerance
    0.001 absolute.

A run is **passing** when:

- Both sides return the same set of ``voicing_id``s in the same order.
- For each matched row, ``|shim - ellington| < tolerance`` on each of
  ``score``, ``base``, ``master_boost``, ``tolerance_match``.

Drift on ``tolerance_match`` is **expected by construction**: the shim
always emits 0 (the JS doesn't run an ``engine_payload.kind``
dispatcher), while Ellington emits non-zero values when Phase 3 fires.
The diff harness treats ``tolerance_match`` as an **Ellington-only
contribution** and excludes it from the per-side equality check.

## Subprocess + JSON robustness

The shim's exit codes (0/2/3/4) are surfaced as
:class:`OracleInvocationError` with the stderr captured. Non-JSON
stdout is surfaced as a separate error so a missing shim version (e.g.
the plugin repo is checked out at a pre-#406 SHA) doesn't get
silently swallowed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .engine import Engine
from .models import EngineRequest, EngineResponse, RankedVoicing


DEFAULT_TOLERANCE = 0.001
SHIM_RELATIVE_PATH = Path("scripts") / "engine_dump.js"


class OracleInvocationError(RuntimeError):
    """Raised when the shim subprocess fails or emits unparseable output."""


@dataclass(frozen=True)
class DiffRow:
    """One per voicing_id present on either side. Each ``delta`` is
    ``shim_value - ellington_value`` (or ``None`` if one side is missing)."""

    voicing_id: str
    shim_rank: int | None
    ellington_rank: int | None
    shim_score: float | None
    ellington_score: float | None
    score_delta: float | None
    base_delta: float | None
    master_boost_delta: float | None


@dataclass(frozen=True)
class DiffResult:
    """Per-request diff between shim and Ellington engine output."""

    request: EngineRequest
    matching_rows: list[DiffRow] = field(default_factory=list)
    drift_rows: list[DiffRow] = field(default_factory=list)
    shim_only_rows: list[DiffRow] = field(default_factory=list)
    ellington_only_rows: list[DiffRow] = field(default_factory=list)
    tolerance: float = DEFAULT_TOLERANCE
    ranking_match: bool = False

    @property
    def passed(self) -> bool:
        """Goal A passes when ranking matches and no rows are in
        ``drift_rows`` / ``shim_only_rows`` / ``ellington_only_rows``."""
        return (
            self.ranking_match
            and not self.drift_rows
            and not self.shim_only_rows
            and not self.ellington_only_rows
        )


def invoke_shim(
    plugin_path: str | Path,
    chord_symbol: str,
    tuning: str,
    master_id: str | None,
    *,
    n_strings: int = 6,
    style_filter: str | None = None,
    position_preference: str | None = None,
    extra_args: list[str] | None = None,
) -> EngineResponse:
    """Run the plugin shim and return the parsed ``EngineResponse``.

    Args:
        plugin_path: filesystem path to the plugin repo root (must
            contain ``scripts/engine_dump.js`` at or above the shim's
            landing commit).
        chord_symbol, tuning, master_id, n_strings, style_filter,
        position_preference: forwarded to the shim's CLI.
        extra_args: optional pass-through for future shim flags.

    Raises:
        OracleInvocationError: if the shim exits non-zero, or stdout
            doesn't parse as JSON, or the JSON fails ``EngineResponse``
            validation.
    """
    shim = Path(plugin_path) / SHIM_RELATIVE_PATH
    if not shim.is_file():
        raise OracleInvocationError(
            f"shim not found at {shim}. The plugin checkout may be at a "
            "commit before musescore4-chord-library-plugin#400 (PR #406) "
            "landed."
        )

    argv = [
        "node",
        str(shim),
        "--chord",
        chord_symbol,
        "--tuning",
        tuning,
        "--n-strings",
        str(n_strings),
    ]
    if master_id is None:
        argv.append("--no-master")
    else:
        argv.extend(["--master", master_id])
    if style_filter is not None:
        argv.extend(["--style", style_filter])
    if position_preference is not None:
        argv.extend(["--position-preference", position_preference])
    if extra_args:
        argv.extend(extra_args)

    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        cwd=Path(plugin_path),
        timeout=60,
    )

    if proc.returncode != 0:
        raise OracleInvocationError(
            f"shim exited {proc.returncode}; stderr=\n{proc.stderr}"
        )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise OracleInvocationError(
            f"shim stdout did not parse as JSON: {exc}\nstdout[:500]={proc.stdout[:500]}"
        ) from exc

    try:
        return EngineResponse.model_validate(payload)
    except ValidationError as exc:
        raise OracleInvocationError(
            f"shim output failed EngineResponse validation: {exc}"
        ) from exc


def _within_tolerance(a: float, b: float, tol: float) -> bool:
    return abs(a - b) < tol


def diff_responses(
    request: EngineRequest,
    shim_response: EngineResponse,
    ellington_response: EngineResponse,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> DiffResult:
    """Compare two ``EngineResponse`` payloads per Goal A's criterion.

    See module docstring for the matching rules. The shim's
    ``tolerance_match`` is structurally 0 and excluded from the
    equality check.
    """
    shim_by_id: dict[str, RankedVoicing] = {
        row.voicing_id: row for row in shim_response.ranked_voicings
    }
    ell_by_id: dict[str, RankedVoicing] = {
        row.voicing_id: row for row in ellington_response.ranked_voicings
    }

    shim_ids = list(shim_by_id.keys())
    ell_ids = list(ell_by_id.keys())
    ranking_match = shim_ids == ell_ids

    matching: list[DiffRow] = []
    drift: list[DiffRow] = []

    for vid, shim_row in shim_by_id.items():
        ell_row = ell_by_id.get(vid)
        if ell_row is None:
            continue
        shim_components = shim_row.score_components
        ell_components = ell_row.score_components
        score_d = shim_row.score - ell_row.score
        base_d = shim_components.base - ell_components.base
        boost_d = shim_components.master_boost - ell_components.master_boost
        diff_row = DiffRow(
            voicing_id=vid,
            shim_rank=shim_response.ranked_voicings.index(shim_row) + 1,
            ellington_rank=ellington_response.ranked_voicings.index(ell_row) + 1,
            shim_score=shim_row.score,
            ellington_score=ell_row.score,
            score_delta=score_d,
            base_delta=base_d,
            master_boost_delta=boost_d,
        )
        if (
            _within_tolerance(shim_row.score, ell_row.score, tolerance)
            and _within_tolerance(shim_components.base, ell_components.base, tolerance)
            and _within_tolerance(
                shim_components.master_boost, ell_components.master_boost, tolerance
            )
        ):
            matching.append(diff_row)
        else:
            drift.append(diff_row)

    shim_only = [
        DiffRow(
            voicing_id=vid,
            shim_rank=shim_response.ranked_voicings.index(row) + 1,
            ellington_rank=None,
            shim_score=row.score,
            ellington_score=None,
            score_delta=None,
            base_delta=None,
            master_boost_delta=None,
        )
        for vid, row in shim_by_id.items()
        if vid not in ell_by_id
    ]
    ell_only = [
        DiffRow(
            voicing_id=vid,
            shim_rank=None,
            ellington_rank=ellington_response.ranked_voicings.index(row) + 1,
            shim_score=None,
            ellington_score=row.score,
            score_delta=None,
            base_delta=None,
            master_boost_delta=None,
        )
        for vid, row in ell_by_id.items()
        if vid not in shim_by_id
    ]

    return DiffResult(
        request=request,
        matching_rows=matching,
        drift_rows=drift,
        shim_only_rows=shim_only,
        ellington_only_rows=ell_only,
        tolerance=tolerance,
        ranking_match=ranking_match,
    )


def diff_against_shim(
    engine: Engine,
    request: EngineRequest,
    plugin_path: str | Path,
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> DiffResult:
    """Run the shim and Ellington's engine on ``request`` and diff.

    The convenience entry point used by the 12-fixture battery once the
    plugin shim lands on develop.
    """
    shim_response = invoke_shim(
        plugin_path=plugin_path,
        chord_symbol=request.chord_symbol,
        tuning="".join(_short_tuning_name(p) for p in request.tuning) if isinstance(request.tuning, list) else str(request.tuning),
        master_id=request.master_id,
        n_strings=request.context.get("n_strings", len(request.tuning)),
        style_filter=request.style_filter,
        position_preference=request.context.get("position_preference"),
    )
    ellington_response = engine.rank(request)
    return diff_responses(
        request=request,
        shim_response=shim_response,
        ellington_response=ellington_response,
        tolerance=tolerance,
    )


def _short_tuning_name(pitch: str) -> str:
    """Convert ``"E2"`` style pitches into ``"E"`` for the shim's
    ``--tuning EADGBE`` arg shape.

    The shim takes one letter per string (assumes standard MIDI octaves
    for each open string). If we need a richer encoding later — e.g.
    custom tunings the shim can't represent via single-letter notation —
    we'll switch to a JSON-encoded ``--tuning-json`` flag on the shim side.
    """
    if not pitch:
        return ""
    return pitch[0]


__all__ = [
    "DEFAULT_TOLERANCE",
    "DiffResult",
    "DiffRow",
    "OracleInvocationError",
    "diff_against_shim",
    "diff_responses",
    "invoke_shim",
]
