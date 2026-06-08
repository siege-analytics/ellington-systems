"""Tests for the engine's Pydantic model surface.

Goal A's oracle diff against shim #400 requires that `EngineResponse`
round-trips through JSON bit-identical to the shim's output. These tests
cover the structural invariants; the actual cross-tool diff lives in
`tests/oracle/` once the shim lands.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ellington_systems.models import (
    EnginePayload,
    EngineRequest,
    EngineResponse,
    PayloadDelta,
    RankedVoicing,
    ScoreComponents,
    VersionInfo,
    Voicing,
    VoicingDot,
)


# ---------------------------------------------------------------------------
# EngineRequest
# ---------------------------------------------------------------------------


class TestEngineRequest:
    def test_minimal_six_string_request(self) -> None:
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        assert req.chord_symbol == "Cmaj7"
        assert len(req.tuning) == 6
        assert req.master_id is None
        assert req.category_filter is None
        assert req.context == {}

    def test_van_eps_seven_string_with_master(self) -> None:
        req = EngineRequest(
            chord_symbol="G6",
            tuning=["A1", "E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="van-eps",
            context={"n_strings": 7, "position_preference": "low"},
        )
        assert len(req.tuning) == 7
        assert req.master_id == "van-eps"
        assert req.context["n_strings"] == 7

    def test_baritone_six_string(self) -> None:
        req = EngineRequest(
            chord_symbol="Fmaj7",
            tuning=["B1", "E2", "A2", "D3", "F#3", "B3"],
        )
        assert len(req.tuning) == 6

    def test_custom_tuning_eight_string(self) -> None:
        req = EngineRequest(
            chord_symbol="Bm",
            tuning=["F#1", "B1", "E2", "A2", "D3", "G3", "B3", "E4"],
        )
        assert len(req.tuning) == 8

    def test_tuning_too_short_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EngineRequest(chord_symbol="Cmaj7", tuning=["E2", "A2", "D3"])

    def test_tuning_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EngineRequest(
                chord_symbol="Cmaj7",
                tuning=["A1"] * 13,
            )

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EngineRequest(
                chord_symbol="Cmaj7",
                tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
                hardcoded_typo="oops",
            )


# ---------------------------------------------------------------------------
# ScoreComponents and RankedVoicing
# ---------------------------------------------------------------------------


class TestScoreComponents:
    def test_default_master_boost_zero(self) -> None:
        sc = ScoreComponents(base=100.0)
        assert sc.master_boost == 0.0
        assert sc.tolerance_match == 0.0

    def test_master_boost_capped_value(self) -> None:
        sc = ScoreComponents(base=100.0, master_boost=60.0)
        assert sc.master_boost == 60.0


class TestRankedVoicing:
    def test_minimal_ranked_voicing(self) -> None:
        rv = RankedVoicing(
            voicing_id="c13b9-cm6-altered-6str-26",
            rank=1,
            score=147.5,
            score_components=ScoreComponents(base=147.5),
        )
        assert rv.voicing_id == "c13b9-cm6-altered-6str-26"
        assert rv.payload_kind is None
        assert rv.applied_principles == []

    def test_ranked_voicing_with_payload_and_principles(self) -> None:
        rv = RankedVoicing(
            voicing_id="cmaj7-shell-6str-3",
            rank=1,
            score=200.0,
            payload_kind="SubstitutionExpand",
            score_components=ScoreComponents(base=170.0, master_boost=30.0),
            applied_principles=["joe-pass/drop-2-and-drop-3-chord-melody"],
        )
        assert rv.payload_kind == "SubstitutionExpand"
        assert len(rv.applied_principles) == 1


# ---------------------------------------------------------------------------
# EngineResponse — full shape compatibility with shim #400
# ---------------------------------------------------------------------------


class TestEngineResponseRoundTrip:
    def test_empty_ranked_voicings_is_valid(self) -> None:
        # Empty candidate set after Phase 1 filter is not an error.
        # See design note Step 4 edge cases.
        req = EngineRequest(
            chord_symbol="Xunknown",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
        )
        resp = EngineResponse(
            request=req,
            ranked_voicings=[],
            engine_version=VersionInfo(sha="1c277be", clean=True),
            masters_version=VersionInfo(sha="628ed30", clean=True),
            voicings_version=VersionInfo(sha="628ed30", clean=True),
        )
        assert resp.ranked_voicings == []

    def test_response_json_round_trip(self) -> None:
        req = EngineRequest(
            chord_symbol="Cmaj7",
            tuning=["E2", "A2", "D3", "G3", "B3", "E4"],
            master_id="joe-pass",
        )
        resp = EngineResponse(
            request=req,
            ranked_voicings=[
                RankedVoicing(
                    voicing_id="cmaj7-shell-6str-3",
                    rank=1,
                    score=200.0,
                    payload_kind="SubstitutionExpand",
                    score_components=ScoreComponents(base=170.0, master_boost=30.0),
                    applied_principles=["joe-pass/drop-2-and-drop-3-chord-melody"],
                )
            ],
            engine_version=VersionInfo(sha="abc1234", clean=True),
            masters_version=VersionInfo(sha="628ed30", clean=True),
            voicings_version=VersionInfo(sha="628ed30", clean=True),
        )
        encoded = resp.model_dump_json()
        decoded = EngineResponse.model_validate_json(encoded)
        assert decoded == resp


# ---------------------------------------------------------------------------
# EnginePayload — heterogeneous corpus tolerance (Tiger 2 mitigation)
# ---------------------------------------------------------------------------


class TestEnginePayloadHeterogeneousShape:
    """Tiger 2 mitigation from the pre-mortem.

    The corpus's SubstitutionExpand instances carry 32 distinct top-level
    keys (Fact Sheet Entity 5). EnginePayload must accept any of them
    without rejection. The 5 fixtures below replicate distinct shapes
    pulled from the schematic disposition output.
    """

    def test_minimal_kind_only(self) -> None:
        ep = EnginePayload(kind="SubstitutionExpand")
        assert ep.kind == "SubstitutionExpand"

    def test_substitution_expand_with_interval(self) -> None:
        ep = EnginePayload.model_validate(
            {"kind": "SubstitutionExpand", "interval": "tritone"},
        )
        assert ep.kind == "SubstitutionExpand"
        assert ep.model_dump()["interval"] == "tritone"

    def test_substitution_expand_with_target_and_source(self) -> None:
        ep = EnginePayload.model_validate(
            {
                "kind": "SubstitutionExpand",
                "target_type": "dominant",
                "source_type": "altered",
            },
        )
        assert ep.model_dump()["target_type"] == "dominant"
        assert ep.model_dump()["source_type"] == "altered"

    def test_pending_kind_round_trips(self) -> None:
        ep = EnginePayload.model_validate(
            {
                "kind": "_pending:inner-voice-counterpoint",
                "voice_count": 3,
                "preserve_independence": True,
            },
        )
        assert ep.kind.startswith("_pending:")
        d = ep.model_dump()
        assert d["voice_count"] == 3
        assert d["preserve_independence"] is True

    def test_unknown_kind_accepted_at_model_level(self) -> None:
        # Schema-level validation of the `kind` value is the engine's
        # responsibility, not the model's. The model is permissive so
        # malformed corpus data round-trips for inspection.
        ep = EnginePayload(kind="NotARealKind", arbitrary_field=42)
        assert ep.kind == "NotARealKind"


# ---------------------------------------------------------------------------
# PayloadDelta — Phase 3 evaluator output contract
# ---------------------------------------------------------------------------


class TestPayloadDelta:
    def test_applied_with_score_delta(self) -> None:
        pd = PayloadDelta(
            status="applied",
            score_delta=15.0,
            applied_principle="joe-pass/drop-2",
        )
        assert pd.status == "applied"

    def test_inert_zero_delta_default(self) -> None:
        pd = PayloadDelta(status="inert")
        assert pd.score_delta == 0.0
        assert pd.applied_principle is None

    def test_rejected_carries_notes(self) -> None:
        pd = PayloadDelta(
            status="rejected",
            notes="error:SubstitutionExpand:missing target_type",
        )
        assert pd.status == "rejected"
        assert pd.notes is not None

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PayloadDelta(status="weird")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Voicing — corpus shape compatibility
# ---------------------------------------------------------------------------


class TestVoicing:
    def test_corpus_sample_round_trips(self) -> None:
        # Sample taken verbatim from voicings.json[0] at plugin SHA 628ed30.
        # See Investigation Fact Sheet Entity 4.
        v = Voicing.model_validate(
            {
                "id": "c13b9-cm6-altered-6str-26",
                "name": "C13b9 — Fret 5 — Altered (6th on top)",
                "chord_quality": "13b9",
                "root": "C",
                "category": "altered",
                "strings": 6,
                "fret_number": 5,
                "visible_frets": 4,
                "dots": [
                    {"string": 6, "fret": 4},
                    {"string": 5, "fret": 3},
                    {"string": 4, "fret": 4},
                    {"string": 3, "fret": 2},
                    {"string": 2, "fret": 1},
                    {"string": 1, "fret": 1},
                ],
                "mutes": [],
                "open": [],
                "notes": ["C", "E", "Bb", "Db", "E", "A"],
                "intervals": ["1", "3", "b7", "b9", "3", "6"],
                "tags": ["calculated", "laukens-coverage"],
                "shape_id": "3ff25a701844",
                "also_qualities": [],
                "suitableModes": ["chord-melody"],
            },
        )
        assert v.id == "c13b9-cm6-altered-6str-26"
        assert v.strings == 6
        assert len(v.dots) == 6
        assert v.voicingStyle == []  # 0/820 tagged today

    def test_seven_string_voicing(self) -> None:
        v = Voicing(
            id="dummy",
            name="dummy",
            chord_quality="maj7",
            root="C",
            category="shell",
            strings=7,
            fret_number=3,
            visible_frets=4,
        )
        assert v.strings == 7

    def test_voicing_with_tags_accepted(self) -> None:
        # Future-state: once tagging crowdsourcing (plugin #389/#393/#395) lands.
        v = Voicing(
            id="dummy",
            name="dummy",
            chord_quality="maj7",
            root="C",
            category="shell",
            strings=6,
            fret_number=3,
            visible_frets=4,
            voicingStyle=["van-eps", "drop-2-friendly"],
        )
        assert "van-eps" in v.voicingStyle

    def test_voicing_unknown_field_allowed(self) -> None:
        # Plugin-internal fields the engine doesn't read must not cause rejection.
        v = Voicing.model_validate(
            {
                "id": "dummy",
                "name": "dummy",
                "chord_quality": "maj7",
                "root": "C",
                "category": "shell",
                "strings": 6,
                "fret_number": 3,
                "visible_frets": 4,
                "plugin_internal_qa_tag": "needs-review",
            },
        )
        assert v.id == "dummy"


# ---------------------------------------------------------------------------
# VoicingDot — fret geometry primitive
# ---------------------------------------------------------------------------


class TestVoicingDot:
    def test_valid_dot(self) -> None:
        d = VoicingDot(string=6, fret=3)
        assert d.string == 6
        assert d.fret == 3

    def test_open_string_fret_zero(self) -> None:
        d = VoicingDot(string=5, fret=0)
        assert d.fret == 0

    def test_string_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VoicingDot(string=0, fret=3)

    def test_string_above_twelve_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VoicingDot(string=13, fret=3)

    def test_negative_fret_rejected(self) -> None:
        with pytest.raises(ValidationError):
            VoicingDot(string=6, fret=-1)
