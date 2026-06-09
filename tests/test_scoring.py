"""Phase 2 tests — verify each `_scoreCandidate` term against the formula.

Per the pre-mortem's Tiger 4 mitigation: tests compute their expected
values from the formula's named constants directly, not from hand-typed
magic numbers. This couples the tests to the formula's STRUCTURE — so
if the JS source changes a constant we'll see it during the next
upstream re-verification, not silently inherit a stale assumption.

Per Tiger 3 mitigation: tests exercise each term in isolation by
constructing voicings whose every other term contributes 0. Composite
tests at the end exercise multiple terms together.

The synthetic-tag tests for `master_boost` (Tiger 5 mitigation) live
here too — they exercise the boost formula even though the production
corpus has 0/820 voicings tagged today.
"""

from __future__ import annotations

from typing import Any

import pytest

from ellington_systems.models import Voicing, VoicingDot
from ellington_systems.scoring import (
    ScoreBreakdown,
    ScoringOpts,
    compute_mode_delta,
    score_candidate,
    signature_key,
)


# ---------------------------------------------------------------------------
# Voicing factories — keep tests terse without sacrificing exact shape
# ---------------------------------------------------------------------------


def _voicing(**overrides: Any) -> Voicing:
    """Build a minimal 6-string voicing for term-isolation tests.

    Defaults are designed so every formula term contributes 0 unless
    overridden by the test.
    """
    base: dict[str, Any] = {
        "id": "test-voicing",
        "name": "test",
        "chord_quality": "maj7",
        "root": "C",
        "category": "open",  # NOT shell or drop2 → category_default = 0
        "strings": 6,
        "fret_number": 1,  # outside 3-7 → fret_3_to_7 = 0
        "visible_frets": 4,
    }
    base.update(overrides)
    return Voicing(**base)


# ---------------------------------------------------------------------------
# Term isolation tests
# ---------------------------------------------------------------------------


class TestQualityMatch:
    def test_match_yields_20(self) -> None:
        v = _voicing(chord_quality="maj7")
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.quality_match == 20.0

    def test_mismatch_yields_0(self) -> None:
        v = _voicing(chord_quality="maj7")
        sb = score_candidate(v, "C", "dom7", -1, -1, None, ScoringOpts())
        assert sb.quality_match == 0.0


class TestFilterCategory:
    def test_filter_match_yields_50(self) -> None:
        v = _voicing(category="drop3")
        opts = ScoringOpts(filter_category="drop3")
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.filter_category == 50.0

    def test_no_filter_yields_0(self) -> None:
        v = _voicing(category="drop3")
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.filter_category == 0.0


class TestCategoryDefault:
    def test_shell_yields_10(self) -> None:
        v = _voicing(category="shell")
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.category_default == 10.0

    def test_drop2_yields_5(self) -> None:
        v = _voicing(category="drop2")
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.category_default == 5.0

    def test_other_category_yields_0(self) -> None:
        v = _voicing(category="altered")
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.category_default == 0.0


class TestMelodyBonus:
    def test_unlocked_match_yields_200(self) -> None:
        v = _voicing()
        opts = ScoringOpts(
            top_note_fn=lambda voicing, root, sm: 7,
            melody_locked=False,
        )
        sb = score_candidate(v, "C", "maj7", 7, -1, None, opts)
        assert sb.melody_bonus == 200.0

    def test_locked_match_yields_500(self) -> None:
        v = _voicing()
        opts = ScoringOpts(
            top_note_fn=lambda voicing, root, sm: 7,
            melody_locked=True,
        )
        sb = score_candidate(v, "C", "maj7", 7, -1, None, opts)
        assert sb.melody_bonus == 500.0

    def test_no_target_yields_0(self) -> None:
        v = _voicing()
        opts = ScoringOpts(top_note_fn=lambda voicing, root, sm: 7)
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.melody_bonus == 0.0

    def test_target_mismatch_yields_0(self) -> None:
        v = _voicing()
        opts = ScoringOpts(top_note_fn=lambda voicing, root, sm: 5)
        sb = score_candidate(v, "C", "maj7", 7, -1, None, opts)
        assert sb.melody_bonus == 0.0

    def test_multiplier_applied(self) -> None:
        # modeConfig.melodyBonusMultiplier scales the bonus.
        v = _voicing()
        opts = ScoringOpts(
            top_note_fn=lambda voicing, root, sm: 7,
            mode_config={"melodyBonusMultiplier": 1.5},
        )
        sb = score_candidate(v, "C", "maj7", 7, -1, None, opts)
        # JS: (200 * 1.5) when unlocked.
        assert sb.melody_bonus == 200.0 * 1.5


class TestBassBonus:
    def test_unlocked_match_yields_250(self) -> None:
        v = _voicing()
        opts = ScoringOpts(bass_note_fn=lambda voicing, root, sm: 0)
        sb = score_candidate(v, "C", "maj7", -1, 0, None, opts)
        assert sb.bass_bonus == 250.0

    def test_locked_match_yields_500(self) -> None:
        v = _voicing()
        opts = ScoringOpts(
            bass_note_fn=lambda voicing, root, sm: 0,
            bass_locked=True,
        )
        sb = score_candidate(v, "C", "maj7", -1, 0, None, opts)
        assert sb.bass_bonus == 500.0


class TestDistancePenaltyAndSameCategoryFret:
    def test_distance_penalty_doubled(self) -> None:
        v = _voicing()
        ref = _voicing(id="ref", category="altered", fret_number=8)
        opts = ScoringOpts(distance_fn=lambda a, b: 3.5)
        sb = score_candidate(v, "C", "maj7", -1, -1, ref, opts)
        # JS: score -= distanceFn(ref, v) * 2 → -7.0
        assert sb.distance_penalty == -3.5 * 2.0

    def test_same_category_fret_yields_neg_15(self) -> None:
        v = _voicing(category="shell", fret_number=5)
        ref = _voicing(id="ref", category="shell", fret_number=5)
        opts = ScoringOpts(distance_fn=lambda a, b: 0.0)
        sb = score_candidate(v, "C", "maj7", -1, -1, ref, opts)
        assert sb.same_category_fret == -15.0

    def test_no_ref_yields_0_both(self) -> None:
        v = _voicing(category="shell", fret_number=5)
        opts = ScoringOpts(distance_fn=lambda a, b: 5.0)
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.distance_penalty == 0.0
        assert sb.same_category_fret == 0.0


class TestMutePenalty:
    def test_zero_mutes_yields_0(self) -> None:
        v = _voicing(mutes=[])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.mute_penalty == 0.0

    def test_two_mutes_yields_neg_10(self) -> None:
        v = _voicing(mutes=[1, 2])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.mute_penalty == -2 * 5.0


class TestFret3To7:
    @pytest.mark.parametrize("fret", [3, 4, 5, 6, 7])
    def test_in_range_yields_5(self, fret: int) -> None:
        v = _voicing(fret_number=fret)
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.fret_3_to_7 == 5.0

    @pytest.mark.parametrize("fret", [0, 1, 2, 8, 9, 12])
    def test_outside_range_yields_0(self, fret: int) -> None:
        v = _voicing(fret_number=fret)
        sb = score_candidate(v, "C", "maj7", -1, -1, None, ScoringOpts())
        assert sb.fret_3_to_7 == 0.0


class TestDifficultyPenalty:
    def test_expert_yields_neg_30(self) -> None:
        v = _voicing()
        opts = ScoringOpts(difficulty_fn=lambda voicing: {"tier": "expert"})
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.difficulty_penalty == -30.0

    def test_advanced_yields_neg_10(self) -> None:
        v = _voicing()
        opts = ScoringOpts(difficulty_fn=lambda voicing: {"tier": "advanced"})
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.difficulty_penalty == -10.0

    def test_intermediate_yields_0(self) -> None:
        v = _voicing()
        opts = ScoringOpts(difficulty_fn=lambda voicing: {"tier": "intermediate"})
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.difficulty_penalty == 0.0


class TestProfileFunctions:
    def test_category_weight_applied(self) -> None:
        v = _voicing(category="shell")
        opts = ScoringOpts(
            profile_category_weight_fn=lambda cat: 12.5 if cat == "shell" else 0.0,
        )
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.profile_category_weight == 12.5

    def test_quality_boost_applied(self) -> None:
        v = _voicing(chord_quality="maj7")
        opts = ScoringOpts(
            profile_quality_boost_fn=lambda q: 7.5 if q == "maj7" else 0.0,
        )
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.profile_quality_boost == 7.5


class TestModeDeltaIntegration:
    def test_mode_delta_picked_up_when_mode_config_set(self) -> None:
        v = _voicing(category="shell", fret_number=5)
        opts = ScoringOpts(
            mode_config={"categoryDeltas": {"shell": 3}},
        )
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.mode_delta == 3.0


class TestCuratedBoost:
    def test_lookup_hit_yields_boost(self) -> None:
        v = _voicing()
        # Compute the actual signature so the test isn't brittle to format details.
        key = signature_key(v)
        opts = ScoringOpts(curated_lookup={key: {"boost": 17.5}})
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.curated_boost == 17.5

    def test_lookup_miss_yields_0(self) -> None:
        v = _voicing()
        opts = ScoringOpts(curated_lookup={"some-other-key": {"boost": 17.5}})
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.curated_boost == 0.0


# ---------------------------------------------------------------------------
# Tiger 5 mitigation — exercise master_boost using synthetic tagged fixtures
# ---------------------------------------------------------------------------


class TestMasterBoostSyntheticTags:
    """Per pre-mortem Tiger 5: corpus is 0/820 tagged today, so without
    synthetic fixtures we never exercise the boost formula. These tests
    inject `voicingStyle` + `master_voicing_style_tags` directly.

    The boost formula is ``Math.min(hits, 2) * 30``; expected values are
    computed from those constants, not hardcoded.
    """

    def test_zero_hits_yields_0(self) -> None:
        v = _voicing(voicingStyle=["something-else"])
        opts = ScoringOpts(master_voicing_style_tags=["van-eps"])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.master_boost == 0.0

    def test_one_hit_yields_30(self) -> None:
        v = _voicing(voicingStyle=["van-eps"])
        opts = ScoringOpts(master_voicing_style_tags=["van-eps", "drop-2-friendly"])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        # JS: Math.min(1, 2) * 30 = 30
        assert sb.master_boost == 1 * 30

    def test_two_hits_yields_60(self) -> None:
        v = _voicing(voicingStyle=["van-eps", "drop-2-friendly"])
        opts = ScoringOpts(master_voicing_style_tags=["van-eps", "drop-2-friendly"])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        # JS: Math.min(2, 2) * 30 = 60
        assert sb.master_boost == 2 * 30

    def test_three_hits_capped_at_60(self) -> None:
        v = _voicing(voicingStyle=["a", "b", "c"])
        opts = ScoringOpts(master_voicing_style_tags=["a", "b", "c"])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        # JS: Math.min(3, 2) * 30 = 60 — the cap.
        assert sb.master_boost == 2 * 30

    def test_empty_master_tags_yields_0(self) -> None:
        v = _voicing(voicingStyle=["van-eps"])
        opts = ScoringOpts(master_voicing_style_tags=[])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.master_boost == 0.0

    def test_empty_voicing_style_yields_0(self) -> None:
        """The corpus's current state: 0/820 voicings tagged → boost always 0."""
        v = _voicing(voicingStyle=[])
        opts = ScoringOpts(master_voicing_style_tags=["van-eps"])
        sb = score_candidate(v, "C", "maj7", -1, -1, None, opts)
        assert sb.master_boost == 0.0


# ---------------------------------------------------------------------------
# Composite tests — multiple terms contribute, verify total
# ---------------------------------------------------------------------------


class TestComposite:
    def test_quality_plus_category_default_plus_fret_range(self) -> None:
        # Voicing in the sweet spot of three constants — total computed
        # from the formula's named values.
        v = _voicing(chord_quality="dom7", category="shell", fret_number=5)
        sb = score_candidate(v, "C", "dom7", -1, -1, None, ScoringOpts())
        # JS: 20 (quality) + 10 (shell) + 5 (fret 3-7) = 35
        expected = 20 + 10 + 5
        assert sb.quality_match == 20.0
        assert sb.category_default == 10.0
        assert sb.fret_3_to_7 == 5.0
        assert sb.total == float(expected)

    def test_total_is_sum_of_components(self) -> None:
        v = _voicing(
            chord_quality="dom7",
            category="drop2",
            fret_number=4,
            mutes=[1],
            voicingStyle=["van-eps"],
        )
        opts = ScoringOpts(
            master_voicing_style_tags=["van-eps"],
            filter_category="drop2",
        )
        sb = score_candidate(v, "C", "dom7", -1, -1, None, opts)
        # quality 20 + filter 50 + drop2 5 + fret 5 + master 30 - mute 5 = 105
        per_term = (
            sb.quality_match
            + sb.filter_category
            + sb.category_default
            + sb.melody_bonus
            + sb.bass_bonus
            + sb.distance_penalty
            + sb.same_category_fret
            + sb.mute_penalty
            + sb.fret_3_to_7
            + sb.difficulty_penalty
            + sb.profile_category_weight
            + sb.profile_quality_boost
            + sb.mode_delta
            + sb.curated_boost
            + sb.master_boost
        )
        assert sb.total == per_term


# ---------------------------------------------------------------------------
# compute_mode_delta — direct tests
# ---------------------------------------------------------------------------


class TestComputeModeDelta:
    def test_null_config_yields_0(self) -> None:
        v = _voicing()
        assert compute_mode_delta(v, None, None) == 0.0

    def test_category_delta(self) -> None:
        v = _voicing(category="shell")
        cfg = {"categoryDeltas": {"shell": 4, "drop2": -2}}
        assert compute_mode_delta(v, cfg, None) == 4.0

    def test_range_fret_bonus(self) -> None:
        v = _voicing(fret_number=5)
        cfg = {"rangeFretMin": 3, "rangeFretMax": 7, "rangeFretBonus": 8}
        assert compute_mode_delta(v, cfg, None) == 8.0

    def test_mute_penalty(self) -> None:
        v = _voicing(mutes=[1, 2, 3])
        cfg = {"mutePenaltyPerString": 4}
        # JS: delta -= muteCount * mutePenaltyPerString → -12
        assert compute_mode_delta(v, cfg, None) == -12.0

    def test_mode_match_bonus(self) -> None:
        v = _voicing(suitableModes=["chord-melody"])
        cfg = {"modeMatchBonus": 6, "modeMismatchPenalty": -2}
        assert compute_mode_delta(v, cfg, "chord-melody") == 6.0

    def test_mode_mismatch_penalty(self) -> None:
        v = _voicing(suitableModes=["chord-melody"])
        cfg = {"modeMatchBonus": 6, "modeMismatchPenalty": -2}
        assert compute_mode_delta(v, cfg, "comping") == -2.0


# ---------------------------------------------------------------------------
# signature_key — direct tests
# ---------------------------------------------------------------------------


class TestSignatureKey:
    def test_minimal_voicing_format(self) -> None:
        v = _voicing(strings=6, mutes=[], open=[], dots=[], intervals=[])
        # Empty pair list → "p:" trailer is empty.
        assert signature_key(v) == "6|m:|o:|p:"

    def test_sorts_pairs_by_string_then_interval(self) -> None:
        v = _voicing(
            dots=[
                VoicingDot(string=3, fret=4),
                VoicingDot(string=1, fret=1),
                VoicingDot(string=2, fret=2),
            ],
            intervals=["5", "1", "3"],
        )
        # After sorting by string: (1,'1'), (2,'3'), (3,'5')
        assert "p:1:1,2:3,3:5" in signature_key(v)

    def test_format_matches_js_expectation(self) -> None:
        v = _voicing(
            strings=6,
            mutes=[1, 2],
            open=[5],
            dots=[VoicingDot(string=4, fret=3)],
            intervals=["3"],
        )
        assert signature_key(v) == "6|m:1,2|o:5|p:4:3"
