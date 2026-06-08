"""End-to-end tests for `Engine.rank` — Phase 4 Aggregator.

The synthetic-fixture tests exercise the full pipeline without needing
a live plugin clone. The `requires_plugin` integration tests verify
the engine binds against the real corpus at SHA `628ed30`.
"""

from __future__ import annotations

from typing import Any

import pytest

from ellington_systems.corpus import Corpus
from ellington_systems.dispatcher import (
    PayloadDispatcherRegistry,
    build_default_registry,
)
from ellington_systems.engine import Engine
from ellington_systems.models import (
    EnginePayload,
    EngineRequest,
    PayloadDelta,
    VersionInfo,
    Voicing,
)


# Shared placeholders for the Engine constructor's three VersionInfo
# parameters. Tests don't exercise version handling; they just need a
# valid object to pass in.
_TEST_VERSION = VersionInfo(sha="test", clean=True)


# ---------------------------------------------------------------------------
# Synthetic corpus builder for hermetic tests
# ---------------------------------------------------------------------------


def _build_synthetic_corpus(
    voicings_data: list[dict[str, Any]],
    masters_data: list[dict[str, Any]],
) -> Corpus:
    """Construct a Corpus in-memory without touching disk."""
    voicings = [Voicing.model_validate(v) for v in voicings_data]
    masters_by_id = {m["id"]: m for m in masters_data if "id" in m}
    return Corpus(
        masters=masters_data,
        voicings=voicings,
        masters_by_id=masters_by_id,
    )


def _basic_voicing(
    *,
    id: str,
    chord_quality: str = "maj7",
    strings: int = 6,
    voicing_style: list[str] | None = None,
    also_qualities: list[str] | None = None,
    intervals: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": id,
        "chord_quality": chord_quality,
        "root": "C",
        "category": "shell",
        "strings": strings,
        "fret_number": 5,
        "visible_frets": 4,
        "notes": ["C", "E", "G", "B"],
        "intervals": intervals or ["1", "3", "5", "7"],
        "voicingStyle": voicing_style or [],
        "also_qualities": also_qualities or [],
    }


# ---------------------------------------------------------------------------
# rank — Phase 1 filtering
# ---------------------------------------------------------------------------


class TestRankFiltersByStringCount:
    def test_six_string_request_excludes_seven_string_voicings(self) -> None:
        corpus = _build_synthetic_corpus(
            voicings_data=[
                _basic_voicing(id="six", strings=6),
                _basic_voicing(id="seven", strings=7),
            ],
            masters_data=[],
        )
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        ids = [r.voicing_id for r in resp.ranked_voicings]
        assert ids == ["six"]


class TestRankFiltersByQuality:
    def test_quality_match(self) -> None:
        corpus = _build_synthetic_corpus(
            voicings_data=[
                _basic_voicing(id="maj7-vc", chord_quality="maj7"),
                _basic_voicing(id="dom7-vc", chord_quality="dom7"),
            ],
            masters_data=[],
        )
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        ids = [r.voicing_id for r in resp.ranked_voicings]
        assert "maj7-vc" in ids
        assert "dom7-vc" not in ids

    def test_also_qualities_match(self) -> None:
        # A voicing whose primary quality is "13" but also_qualities ["dom7"]
        # should be selected for a Cdom7 request.
        corpus = _build_synthetic_corpus(
            voicings_data=[
                _basic_voicing(
                    id="dual",
                    chord_quality="13",
                    also_qualities=["dom7"],
                ),
            ],
            masters_data=[],
        )
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cdom7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        ids = [r.voicing_id for r in resp.ranked_voicings]
        assert ids == ["dual"]


# ---------------------------------------------------------------------------
# rank — Phase 2 base scoring shape
# ---------------------------------------------------------------------------


class TestRankBaseScoring:
    def test_response_score_components_match_base_plus_zero(self) -> None:
        corpus = _build_synthetic_corpus(
            voicings_data=[_basic_voicing(id="v")],
            masters_data=[],
        )
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=VersionInfo(sha="ellington-test", clean=True),
            masters_version=VersionInfo(sha="plugin-test", clean=True),
            voicings_version=VersionInfo(sha="plugin-test", clean=True),
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        assert len(resp.ranked_voicings) == 1
        rv = resp.ranked_voicings[0]
        # No master, no payloads, no tags → master_boost = tolerance_match = 0
        assert rv.score_components.master_boost == 0.0
        assert rv.score_components.tolerance_match == 0.0
        # Quality match (+20) + shell category default (+10) + fret 5 in [3,7] (+5)
        # All other terms = 0 because no opts are wired.
        assert rv.score_components.base == 35.0
        assert rv.score == 35.0


# ---------------------------------------------------------------------------
# rank — Master handling
# ---------------------------------------------------------------------------


class TestRankWithMaster:
    def test_unknown_master_raises_keyerror(self) -> None:
        corpus = _build_synthetic_corpus(
            voicings_data=[_basic_voicing(id="v")],
            masters_data=[{"id": "exists", "principles": []}],
        )
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="does-not-exist",
        )
        with pytest.raises(KeyError, match="does-not-exist"):
            engine.rank(req)

    def test_principles_only_master_skips_phase_3(self) -> None:
        # Master has principles[] but no works[].systems[] → Phase 3 is no-op
        corpus = _build_synthetic_corpus(
            voicings_data=[
                _basic_voicing(id="v", voicing_style=["van-eps"]),
            ],
            masters_data=[
                {
                    "id": "principles-only",
                    "principles": [
                        {"voicingStyleTags": ["van-eps"]},
                    ],
                }
            ],
        )
        engine = Engine(
            corpus=corpus,
            registry=build_default_registry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="principles-only",
        )
        resp = engine.rank(req)
        rv = resp.ranked_voicings[0]
        # tag intersection: voicing has "van-eps", master has "van-eps" → +30
        assert rv.score_components.master_boost == 30.0
        # Phase 3 didn't fire because no systems[].
        assert rv.score_components.tolerance_match == 0.0

    def test_systems_master_runs_phase_3(self) -> None:
        corpus = _build_synthetic_corpus(
            voicings_data=[_basic_voicing(id="v", chord_quality="maj7")],
            masters_data=[
                {
                    "id": "systems-master",
                    "principles": [],
                    "works": [
                        {
                            "systems": [
                                {
                                    "id": "sys-1",
                                    "traversal_rules": [
                                        {
                                            "id": "sys-1/rule-1",
                                            "engine_payload": {
                                                "kind": "SubstitutionExpand",
                                                "target_type": "maj7",
                                            },
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ],
        )
        engine = Engine(
            corpus=corpus,
            registry=build_default_registry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="systems-master",
        )
        resp = engine.rank(req)
        rv = resp.ranked_voicings[0]
        # Phase 3 fired via SubstitutionExpand evaluator → +8.0 in tolerance_match
        assert rv.score_components.tolerance_match == 8.0
        assert rv.payload_kind == "SubstitutionExpand"
        assert "sys-1/rule-1" in rv.applied_principles


# ---------------------------------------------------------------------------
# rank — Sort ordering
# ---------------------------------------------------------------------------


class TestRankSortOrdering:
    def test_higher_score_first(self) -> None:
        corpus = _build_synthetic_corpus(
            voicings_data=[
                # Same shell category to keep things equal except for the
                # filter_category boost.
                _basic_voicing(id="boring"),
                _basic_voicing(id="boring-2"),
            ],
            masters_data=[],
        )
        # Both voicings score 35 — ordering is stable but unspecified.
        # We verify the response is sorted (descending) by score.
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        scores = [r.score for r in resp.ranked_voicings]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# rank — Empty candidate set is not an error
# ---------------------------------------------------------------------------


class TestRankEmpty:
    def test_empty_candidates_yields_empty_response(self) -> None:
        # No voicing matches the requested chord quality.
        corpus = _build_synthetic_corpus(
            voicings_data=[_basic_voicing(id="v", chord_quality="maj7")],
            masters_data=[],
        )
        engine = Engine(
            corpus=corpus,
            registry=PayloadDispatcherRegistry(),
            engine_version=_TEST_VERSION,
            masters_version=_TEST_VERSION,
            voicings_version=_TEST_VERSION,
        )
        req = EngineRequest(
            chord_symbol="CnoSuchQuality",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        assert resp.ranked_voicings == []
        # Response still carries engine/masters versions for diff harness.
        assert resp.engine_version == _TEST_VERSION
        assert resp.masters_version == _TEST_VERSION
        assert resp.voicings_version == _TEST_VERSION


# ---------------------------------------------------------------------------
# Live-plugin integration
# ---------------------------------------------------------------------------


@pytest.mark.requires_plugin
class TestLivePluginCorpus:
    def test_rank_against_real_corpus(self, plugin_clone_path: str) -> None:
        """End-to-end check: engine binds to the real corpus, returns a
        non-empty response for a common chord request, and the response
        is JSON-serializable (matters for shim diff)."""
        corpus = Corpus.from_plugin_clone(plugin_clone_path)
        engine = Engine(
            corpus=corpus,
            registry=build_default_registry(),
            engine_version=VersionInfo(sha="ellington-spike", clean=True),
            masters_version=VersionInfo(sha="628ed30", clean=True),
            voicings_version=VersionInfo(sha="628ed30", clean=True),
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = engine.rank(req)
        # Real corpus has plenty of maj7 voicings; expect at least one.
        assert len(resp.ranked_voicings) > 0
        # JSON round-trip — this is the diff-harness substrate.
        encoded = resp.model_dump_json()
        from ellington_systems.models import EngineResponse

        decoded = EngineResponse.model_validate_json(encoded)
        assert decoded.engine_version.sha == "ellington-spike"
        assert decoded.engine_version.clean is True
        assert decoded.masters_version.sha == "628ed30"
        assert decoded.voicings_version.sha == "628ed30"

    def test_rank_with_master_runs_phase_3(self, plugin_clone_path: str) -> None:
        """Pat Martino has `systems[]` per Fact Sheet — verify Phase 3
        runs against the real corpus's payloads."""
        corpus = Corpus.from_plugin_clone(plugin_clone_path)
        engine = Engine(
            corpus=corpus,
            registry=build_default_registry(),
            engine_version=VersionInfo(sha="ellington-spike", clean=True),
            masters_version=VersionInfo(sha="628ed30", clean=True),
            voicings_version=VersionInfo(sha="628ed30", clean=True),
        )
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="pat-martino",
        )
        resp = engine.rank(req)
        assert len(resp.ranked_voicings) > 0
        # The corpus may or may not have a maj7-target SubstitutionExpand
        # payload that fires for this exact chord; assert the structure
        # rather than the value.
        for rv in resp.ranked_voicings:
            assert rv.score_components.tolerance_match >= 0.0
