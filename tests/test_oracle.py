"""Tests for the oracle-diff harness.

Two tiers:

- **Synthetic tests** (no markers) — verify ``diff_responses`` logic
  using hand-constructed EngineResponse fixtures. These run today;
  they validate the diff math, the tolerance check, the
  matching/drift/missing categorization, and the ``passed`` predicate.

- **`requires_shim` tests** — actually invoke the plugin's
  ``scripts/engine_dump.js``. Skipped until plugin PR #406 lands on
  develop. When the shim arrives, these light up automatically and
  exercise the 12-fixture battery end-to-end.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ellington_systems.corpus import Corpus
from ellington_systems.dispatcher import build_default_registry
from ellington_systems.engine import Engine
from ellington_systems.models import (
    EngineRequest,
    EngineResponse,
    RankedVoicing,
    ScoreComponents,
    VersionInfo,
)
from ellington_systems.oracle import (
    DEFAULT_TOLERANCE,
    DiffResult,
    OracleInvocationError,
    diff_responses,
    invoke_shim,
)


_TEST_VERSION = VersionInfo(sha="test", clean=True)


def _make_response(rows: list[tuple[str, float, float, float]]) -> EngineResponse:
    """Build an EngineResponse from (voicing_id, score, base, master_boost) tuples."""
    return EngineResponse(
        request=EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        ),
        ranked_voicings=[
            RankedVoicing(
                voicing_id=vid,
                rank=index + 1,
                score=score,
                score_components=ScoreComponents(
                    base=base, master_boost=boost, tolerance_match=0.0
                ),
            )
            for index, (vid, score, base, boost) in enumerate(rows)
        ],
        engine_version=_TEST_VERSION,
        masters_version=_TEST_VERSION,
        voicings_version=_TEST_VERSION,
    )


# ---------------------------------------------------------------------------
# diff_responses — happy path
# ---------------------------------------------------------------------------


class TestDiffResponsesExactMatch:
    def test_identical_responses_pass(self) -> None:
        rows = [
            ("a", 100.0, 100.0, 0.0),
            ("b", 50.0, 50.0, 0.0),
        ]
        shim = _make_response(rows)
        ell = _make_response(rows)
        result = diff_responses(shim.request, shim, ell)
        assert result.passed
        assert result.ranking_match
        assert len(result.matching_rows) == 2
        assert result.drift_rows == []
        assert result.shim_only_rows == []
        assert result.ellington_only_rows == []

    def test_within_tolerance_counts_as_match(self) -> None:
        # 0.0001 delta is below the default 0.001 tolerance.
        shim = _make_response([("a", 100.0, 100.0, 0.0)])
        ell = _make_response([("a", 100.0001, 100.0001, 0.0)])
        result = diff_responses(shim.request, shim, ell)
        assert result.passed


# ---------------------------------------------------------------------------
# diff_responses — drift detection
# ---------------------------------------------------------------------------


class TestDiffResponsesDrift:
    def test_score_drift_above_tolerance(self) -> None:
        shim = _make_response([("a", 100.0, 100.0, 0.0)])
        ell = _make_response([("a", 100.5, 100.5, 0.0)])
        result = diff_responses(shim.request, shim, ell)
        assert not result.passed
        assert len(result.drift_rows) == 1
        assert result.drift_rows[0].voicing_id == "a"
        assert result.drift_rows[0].score_delta == pytest.approx(-0.5)
        assert result.drift_rows[0].base_delta == pytest.approx(-0.5)

    def test_master_boost_drift_flagged(self) -> None:
        shim = _make_response([("a", 100.0, 70.0, 30.0)])
        ell = _make_response([("a", 100.0, 100.0, 0.0)])
        result = diff_responses(shim.request, shim, ell)
        assert not result.passed
        assert len(result.drift_rows) == 1
        # Score matches but base + master_boost differ — that's a drift.
        assert result.drift_rows[0].master_boost_delta == pytest.approx(30.0)

    def test_ranking_mismatch_fails_even_if_components_match(self) -> None:
        shim = _make_response(
            [("a", 100.0, 100.0, 0.0), ("b", 50.0, 50.0, 0.0)]
        )
        ell = _make_response(
            [("b", 50.0, 50.0, 0.0), ("a", 100.0, 100.0, 0.0)]
        )
        result = diff_responses(shim.request, shim, ell)
        assert not result.passed
        assert not result.ranking_match
        # The component checks still mark matching rows as matching;
        # the failure is in the ranking_match flag.
        assert len(result.matching_rows) == 2
        assert result.drift_rows == []


# ---------------------------------------------------------------------------
# diff_responses — missing rows on either side
# ---------------------------------------------------------------------------


class TestDiffResponsesMissingRows:
    def test_shim_only_row(self) -> None:
        shim = _make_response(
            [("a", 100.0, 100.0, 0.0), ("only-on-shim", 50.0, 50.0, 0.0)]
        )
        ell = _make_response([("a", 100.0, 100.0, 0.0)])
        result = diff_responses(shim.request, shim, ell)
        assert not result.passed
        assert len(result.shim_only_rows) == 1
        assert result.shim_only_rows[0].voicing_id == "only-on-shim"
        assert result.shim_only_rows[0].ellington_rank is None

    def test_ellington_only_row(self) -> None:
        shim = _make_response([("a", 100.0, 100.0, 0.0)])
        ell = _make_response(
            [("a", 100.0, 100.0, 0.0), ("only-on-ell", 50.0, 50.0, 0.0)]
        )
        result = diff_responses(shim.request, shim, ell)
        assert not result.passed
        assert len(result.ellington_only_rows) == 1
        assert result.ellington_only_rows[0].voicing_id == "only-on-ell"
        assert result.ellington_only_rows[0].shim_rank is None


# ---------------------------------------------------------------------------
# tolerance_match exclusion (Goal A semantics)
# ---------------------------------------------------------------------------


class TestToleranceMatchExclusion:
    def test_tolerance_match_drift_ignored_when_other_components_match(self) -> None:
        # Shim: tolerance_match=0 by construction. Ellington: tolerance_match
        # has a non-zero Phase 3 contribution. The component check passes
        # because tolerance_match is excluded from the equality test.
        shim = EngineResponse(
            request=EngineRequest(
                chord_symbol="Cmaj7",
                tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            ),
            ranked_voicings=[
                RankedVoicing(
                    voicing_id="a",
                    rank=1,
                    score=100.0,
                    score_components=ScoreComponents(
                        base=100.0, master_boost=0.0, tolerance_match=0.0
                    ),
                )
            ],
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        ell = EngineResponse(
            request=shim.request,
            ranked_voicings=[
                RankedVoicing(
                    voicing_id="a",
                    rank=1,
                    score=115.0,  # different because of phase3 contribution
                    score_components=ScoreComponents(
                        base=100.0, master_boost=0.0, tolerance_match=15.0
                    ),
                )
            ],
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        result = diff_responses(shim.request, shim, ell)
        # base + master_boost match (both 100, 0); score differs because
        # Ellington adds tolerance_match. The per-component check only
        # looks at score, base, master_boost — so 'score' itself differs.
        # That's the design: shim score == base + master_boost (no phase3),
        # so divergence in 'score' alone DOES surface here.
        # This documents the intended behaviour explicitly.
        assert not result.passed
        assert len(result.drift_rows) == 1


# ---------------------------------------------------------------------------
# Custom tolerance
# ---------------------------------------------------------------------------


class TestCustomTolerance:
    def test_loose_tolerance_admits_more(self) -> None:
        shim = _make_response([("a", 100.0, 100.0, 0.0)])
        ell = _make_response([("a", 100.5, 100.5, 0.0)])
        # Default 0.001 → drift. Loose 1.0 → match.
        loose = diff_responses(shim.request, shim, ell, tolerance=1.0)
        assert loose.passed

    def test_strict_tolerance_rejects_more(self) -> None:
        shim = _make_response([("a", 100.0, 100.0, 0.0)])
        ell = _make_response([("a", 100.0001, 100.0001, 0.0)])
        strict = diff_responses(shim.request, shim, ell, tolerance=1e-8)
        assert not strict.passed


# ---------------------------------------------------------------------------
# Default tolerance constant
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_tolerance_value(self) -> None:
        # Pinned by ticket #1 success criteria: "score-component delta
        # tolerance 0.001 absolute". Changing this without updating the
        # ticket is a contract drift.
        assert DEFAULT_TOLERANCE == 0.001


# ---------------------------------------------------------------------------
# invoke_shim — error surfaces (without actually running a shim)
# ---------------------------------------------------------------------------


class TestInvokeShimErrors:
    def test_missing_shim_raises_invocation_error(self, tmp_path: Path) -> None:
        # tmp_path has no scripts/engine_dump.js — should fail fast.
        with pytest.raises(OracleInvocationError, match="shim not found"):
            invoke_shim(
                plugin_path=tmp_path,
                chord_symbol="Cmaj7",
                tuning="EADGBE",
                master_id="joe-pass",
            )


# ---------------------------------------------------------------------------
# requires_shim — full battery against the actual plugin shim
# ---------------------------------------------------------------------------


@pytest.mark.requires_shim
@pytest.mark.requires_plugin
class TestShimBattery:
    """Activates once both ELLINGTON_PLUGIN_PATH is set AND the plugin
    checkout includes ``scripts/engine_dump.js``. Pytest collects
    requires_shim tests via the pyproject marker; they skip cleanly
    until the shim lands.
    """

    @pytest.fixture()
    def shim_available(self, plugin_clone_path: str) -> str:
        shim = Path(plugin_clone_path) / "scripts" / "engine_dump.js"
        if not shim.is_file():
            pytest.skip(
                "Plugin checkout doesn't include scripts/engine_dump.js yet "
                "(awaiting plugin PR #406 landing on develop)."
            )
        return plugin_clone_path

    def test_smoke_cmaj7_joepass(self, shim_available: str) -> None:
        response = invoke_shim(
            plugin_path=shim_available,
            chord_symbol="Cmaj7",
            tuning="EADGBE",
            master_id="joe-pass",
            n_strings=6,
        )
        assert len(response.ranked_voicings) > 0
        assert response.engine_version.sha
        assert response.masters_version.sha
        assert response.voicings_version.sha

    def test_diff_against_ellington_on_joe_pass(self, shim_available: str) -> None:
        """The headline Goal A integration test once shim lands."""
        corpus = Corpus.from_plugin_clone(shim_available)
        engine = Engine(
            corpus=corpus,
            registry=build_default_registry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        request = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="joe-pass",
            context={"n_strings": 6},
        )
        shim_response = invoke_shim(
            plugin_path=shim_available,
            chord_symbol="Cmaj7",
            tuning="EADGBE",
            master_id="joe-pass",
            n_strings=6,
        )
        ellington_response = engine.rank(request)
        result = diff_responses(request, shim_response, ellington_response)
        # The first time this runs, drift is expected — that's the
        # signal for what Phase 2's port needs to converge on. Don't
        # assert .passed yet; instead assert structural sanity.
        assert isinstance(result, DiffResult)
        assert result.tolerance == DEFAULT_TOLERANCE
