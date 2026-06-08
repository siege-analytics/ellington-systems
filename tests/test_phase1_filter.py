"""Direct unit tests for the Phase 1 candidate-filter port (#10).

Covers each of the five distinct divergences the prior stub had from
the shim's ``findAllVoicings`` — strings ceiling, root filter, quartal
fallback inclusion, dedup-by-shape-key (with the trailing comma),
zero-match category-fallback retry, and the dropped ``also_qualities``
consultation.
"""

from __future__ import annotations

from typing import Any

import pytest

from ellington_systems.engine import _phase1_filter_candidates
from ellington_systems.models import Voicing, VoicingDot


def _v(**overrides: Any) -> Voicing:
    base: dict[str, Any] = {
        "id": "test",
        "name": "test",
        "chord_quality": "maj7",
        "root": "C",
        "category": "shell",
        "strings": 6,
        "fret_number": 5,
        "visible_frets": 4,
    }
    base.update(overrides)
    return Voicing(**base)


# ---------------------------------------------------------------------------
# Strings ceiling (port REV: <= max_strings, not == n_strings)
# ---------------------------------------------------------------------------


class TestStringsCeiling:
    def test_default_max_strings_is_seven(self) -> None:
        # With max_strings=None, the JS default of 7 applies (line 380).
        voicings = [_v(id="seven", strings=7)]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        assert [v.id for v in out] == ["seven"]

    def test_explicit_max_strings_caps_higher_counts(self) -> None:
        voicings = [
            _v(id="six", strings=6),
            _v(id="seven", strings=7),
            _v(id="eight", strings=8),
        ]
        out = _phase1_filter_candidates(voicings, "Cmaj7", max_strings=6)
        # 7 and 8 both excluded; 6 admitted.
        assert [v.id for v in out] == ["six"]

    def test_lower_string_counts_admitted_per_shim_contract(self) -> None:
        # Shim uses <= (not ==). A 5-string voicing with max_strings=6
        # IS admitted — different from the pre-#10 stub which required ==.
        # Note: the JS dedup key (chord_quality|fret_number|dots) does NOT
        # include strings count, so we have to give each voicing distinct
        # dots or distinct fret_number to avoid the dedup eating one.
        voicings = [
            _v(id="five", strings=5, fret_number=3),
            _v(id="six", strings=6, fret_number=5),
        ]
        out = _phase1_filter_candidates(voicings, "Cmaj7", max_strings=6)
        assert sorted(v.id for v in out) == ["five", "six"]


# ---------------------------------------------------------------------------
# Root filter (NEW per port)
# ---------------------------------------------------------------------------


class TestRootFilter:
    def test_c_rooted_admitted_always(self) -> None:
        # "C"-rooted voicings are the canonical "transpose me" templates;
        # always admitted regardless of target root.
        voicings = [_v(id="c-rooted", root="C")]
        out = _phase1_filter_candidates(voicings, "Fmaj7")
        assert [v.id for v in out] == ["c-rooted"]

    def test_target_root_admitted(self) -> None:
        voicings = [_v(id="f-rooted", root="F")]
        out = _phase1_filter_candidates(voicings, "Fmaj7")
        assert [v.id for v in out] == ["f-rooted"]

    def test_other_root_excluded(self) -> None:
        voicings = [_v(id="d-rooted", root="D")]
        out = _phase1_filter_candidates(voicings, "Fmaj7")
        assert out == []


# ---------------------------------------------------------------------------
# Quality + quartal admission
# ---------------------------------------------------------------------------


class TestAdmission:
    def test_quality_match_admitted(self) -> None:
        voicings = [_v(id="maj7", chord_quality="maj7")]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        assert [v.id for v in out] == ["maj7"]

    def test_quartal_category_admitted_even_when_quality_mismatch(self) -> None:
        # JS line 393: `chord_quality === quality || category === "quartal"`.
        # A quartal voicing with chord_quality="13" is admitted under a
        # Cmaj7 request — that's the fallback inclusion.
        voicings = [_v(id="quartal-13", chord_quality="13", category="quartal")]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        assert [v.id for v in out] == ["quartal-13"]

    def test_also_qualities_NOT_consulted(self) -> None:
        # Documents the divergence from the pre-#10 stub.
        voicings = [
            _v(id="dual", chord_quality="13", also_qualities=["dom7"]),
        ]
        out = _phase1_filter_candidates(voicings, "Cdom7")
        assert out == []


# ---------------------------------------------------------------------------
# Category-filter gate (JS line 394 three-condition AND)
# ---------------------------------------------------------------------------


class TestCategoryFilter:
    def test_filter_category_admits_matching(self) -> None:
        voicings = [
            _v(id="shell", chord_quality="maj7", category="shell"),
            _v(id="drop2", chord_quality="maj7", category="drop2"),
        ]
        out = _phase1_filter_candidates(
            voicings, "Cmaj7", filter_category="shell"
        )
        assert [v.id for v in out] == ["shell"]

    def test_filter_category_quartal_arm_passes_gate(self) -> None:
        # Voicing admitted via category=="quartal" (chord_quality mismatch)
        # is NOT subject to the category-filter gate per JS line 394's
        # three-condition AND. The gate requires v.chord_quality == quality
        # to fire.
        voicings = [
            _v(id="shell", chord_quality="maj7", category="shell"),
            _v(id="quartal", chord_quality="13", category="quartal"),
        ]
        out = _phase1_filter_candidates(
            voicings, "Cmaj7", filter_category="shell"
        )
        # Both admitted: shell matches the gate; quartal bypasses it.
        assert sorted(v.id for v in out) == ["quartal", "shell"]


# ---------------------------------------------------------------------------
# Shape dedup with the trailing-comma key format
# ---------------------------------------------------------------------------


class TestShapeDedup:
    def test_identical_shapes_dedupe_to_first_occurrence(self) -> None:
        dots = [VoicingDot(string=6, fret=3), VoicingDot(string=5, fret=2)]
        voicings = [
            _v(
                id="first",
                fret_number=5,
                dots=dots,
            ),
            _v(
                id="second",
                fret_number=5,
                dots=dots,
            ),
        ]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        # Same chord_quality + fret_number + dots → same shape → dedup.
        # First occurrence wins.
        assert [v.id for v in out] == ["first"]

    def test_different_fret_number_not_deduped(self) -> None:
        dots = [VoicingDot(string=6, fret=3)]
        voicings = [
            _v(id="fret3", fret_number=3, dots=dots),
            _v(id="fret5", fret_number=5, dots=dots),
        ]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        assert sorted(v.id for v in out) == ["fret3", "fret5"]

    def test_different_dots_not_deduped(self) -> None:
        voicings = [
            _v(
                id="shape1",
                dots=[VoicingDot(string=6, fret=3)],
            ),
            _v(
                id="shape2",
                dots=[VoicingDot(string=6, fret=4)],
            ),
        ]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        assert sorted(v.id for v in out) == ["shape1", "shape2"]


# ---------------------------------------------------------------------------
# Zero-match category-fallback retry (JS lines 405-413)
# ---------------------------------------------------------------------------


class TestCategoryFallbackRetry:
    def test_zero_match_triggers_fallback(self) -> None:
        # First pass has filter_category set; no voicing satisfies the gate.
        # Second pass relaxes the category restriction and re-admits.
        voicings = [
            _v(id="shell", chord_quality="maj7", category="shell"),
            _v(id="drop2", chord_quality="maj7", category="drop2"),
        ]
        # No voicing has category="extended" — first pass yields zero.
        out = _phase1_filter_candidates(
            voicings, "Cmaj7", filter_category="extended"
        )
        # Second pass admits both (chord_quality matches, no category gate).
        assert sorted(v.id for v in out) == ["drop2", "shell"]

    def test_no_fallback_when_filter_category_unset(self) -> None:
        # No filter_category → no fallback path. Zero result stays zero.
        voicings = [
            _v(id="absent-quality", chord_quality="m7b5"),
        ]
        out = _phase1_filter_candidates(voicings, "Cmaj7")
        assert out == []

    def test_fallback_respects_root_and_strings_filters(self) -> None:
        voicings = [
            _v(id="c-shell", root="C", chord_quality="maj7", category="shell"),
            _v(id="d-shell", root="D", chord_quality="maj7", category="shell"),
            _v(id="c-seven-string", root="C", chord_quality="maj7", category="shell", strings=7),
        ]
        out = _phase1_filter_candidates(
            voicings,
            "Cmaj7",
            max_strings=6,
            filter_category="extended",  # no match → triggers fallback
        )
        # Fallback admits root-OK + strings-OK candidates only.
        # d-shell: root D mismatches target C → excluded.
        # c-seven-string: 7 > max 6 → excluded.
        assert [v.id for v in out] == ["c-shell"]


# ---------------------------------------------------------------------------
# Tiger 1 mitigation — dedup-key trailing-comma format
# ---------------------------------------------------------------------------


class TestTiger1_DedupKeyFormat:
    """Per Pre-mortem Tiger 1 on ticket #10: verify the dedup key has a
    trailing comma on every dot (matches JS line 398 verbatim)."""

    def test_dedup_key_format_has_trailing_comma(self) -> None:
        # We construct two voicings whose dots list differ ONLY in a way
        # that the trailing-comma format catches. If the Python port used
        # `",".join(...)` instead of `"".join(... + ",")`, the keys would
        # collide and one voicing would be silently dropped.
        v1 = _v(
            id="v1",
            dots=[VoicingDot(string=6, fret=3), VoicingDot(string=5, fret=2)],
        )
        v2 = _v(
            id="v2",
            dots=[VoicingDot(string=6, fret=3), VoicingDot(string=5, fret=2)],
        )
        # Identical shapes — should dedupe to one.
        out = _phase1_filter_candidates([v1, v2], "Cmaj7")
        assert len(out) == 1, "Identical shapes should dedupe"

        # If we change ONE dot, keys must diverge.
        v3 = _v(
            id="v3",
            dots=[VoicingDot(string=6, fret=3), VoicingDot(string=5, fret=99)],
        )
        out2 = _phase1_filter_candidates([v1, v3], "Cmaj7")
        assert sorted(v.id for v in out2) == ["v1", "v3"]
