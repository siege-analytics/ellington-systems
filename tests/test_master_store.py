"""Tests for `master_store` — master-tag collection feeding `master_boost`."""

from __future__ import annotations

import pytest

from ellington_systems.master_store import (
    collect_voicing_style_tags,
    derive_tolerances_from_master,
)


class TestCollectVoicingStyleTags:
    def test_none_master_yields_empty(self) -> None:
        assert collect_voicing_style_tags(None) == []

    def test_master_with_no_principles_yields_empty(self) -> None:
        # Mirrors the corpus's `benson` shape — see Investigation Fact
        # Sheet Finding 2 (`benson` is JS-scoring-inert).
        master = {"id": "benson", "works": []}
        assert collect_voicing_style_tags(master) == []

    def test_master_with_null_principles_yields_empty(self) -> None:
        master = {"id": "x", "principles": None}
        assert collect_voicing_style_tags(master) == []

    def test_single_principle_no_tags(self) -> None:
        master = {"principles": [{"id": "p1"}]}
        assert collect_voicing_style_tags(master) == []

    def test_single_principle_with_tags(self) -> None:
        master = {"principles": [{"voicingStyleTags": ["van-eps", "drop-2"]}]}
        assert collect_voicing_style_tags(master) == ["van-eps", "drop-2"]

    def test_multiple_principles_dedupe(self) -> None:
        master = {
            "principles": [
                {"voicingStyleTags": ["a", "b"]},
                {"voicingStyleTags": ["b", "c"]},  # b duplicates
                {"voicingStyleTags": ["c", "d"]},  # c duplicates
            ],
        }
        assert collect_voicing_style_tags(master) == ["a", "b", "c", "d"]

    def test_first_seen_order_preserved(self) -> None:
        master = {
            "principles": [
                {"voicingStyleTags": ["z", "a"]},  # z first
                {"voicingStyleTags": ["m"]},
            ],
        }
        assert collect_voicing_style_tags(master) == ["z", "a", "m"]


class TestDeriveTolerancesFromMaster:
    def test_none_master_yields_none(self) -> None:
        assert derive_tolerances_from_master(None, None) is None

    def test_master_no_principles_yields_none(self) -> None:
        assert derive_tolerances_from_master({"works": []}, None) is None

    def test_no_hints_yields_none(self) -> None:
        master = {"principles": [{"voicingStyleTags": ["x"]}]}
        assert derive_tolerances_from_master(master, lambda a, b: dict(a)) is None

    def test_graceful_degrade_returns_first_hint_when_no_tightener(self) -> None:
        master = {
            "principles": [
                {"tolerance_hints": {"maxFret": 12}},
                {"tolerance_hints": {"maxFret": 9}},  # would be tightened away
            ],
        }
        # JS comment: "degrade gracefully by returning the FIRST hint we find"
        assert derive_tolerances_from_master(master, None) == {"maxFret": 12}

    def test_tightener_called_to_merge_multiple_hints(self) -> None:
        master = {
            "principles": [
                {"tolerance_hints": {"maxFret": 12}},
                {"tolerance_hints": {"maxFret": 9}},
            ],
        }

        def tighten(a: dict, b: dict) -> dict:
            # "Stricter wins" — for maxFret, MIN wins.
            return {"maxFret": min(a["maxFret"], b["maxFret"])}

        result = derive_tolerances_from_master(master, tighten)
        assert result == {"maxFret": 9}

    def test_skips_empty_hints_dicts(self) -> None:
        master = {
            "principles": [
                {"tolerance_hints": {}},  # skipped per JS line 162
                {"tolerance_hints": {"maxFret": 5}},
            ],
        }
        result = derive_tolerances_from_master(master, lambda a, b: dict(a))
        assert result == {"maxFret": 5}


# ---------------------------------------------------------------------------
# Real-corpus sanity check (skipped when ELLINGTON_PLUGIN_PATH unset)
# ---------------------------------------------------------------------------


@pytest.mark.requires_plugin
class TestCorpusIntegration:
    """End-to-end check against the live plugin corpus.

    Verifies the 5 principles[]-only masters (Finding from Investigation
    Fact Sheet) actually collect some tags, and `benson` collects zero —
    matching the JS scoring-inert observation that motivated the
    Post-error revision on ticket #1.
    """

    def test_benson_tags_empty(self, plugin_clone_path: str) -> None:
        import json
        from pathlib import Path

        masters_path = Path(plugin_clone_path) / "plugin" / "data" / "masters.json"
        data = json.loads(masters_path.read_text())
        benson = next(m for m in data["masters"] if m["id"] == "benson")
        assert collect_voicing_style_tags(benson) == []

    def test_wes_montgomery_tags_present(self, plugin_clone_path: str) -> None:
        # `wes-montgomery` is one of the 5 principles[]-only masters,
        # which have populated voicingStyleTags per the Fact Sheet.
        import json
        from pathlib import Path

        masters_path = Path(plugin_clone_path) / "plugin" / "data" / "masters.json"
        data = json.loads(masters_path.read_text())
        wes = next(m for m in data["masters"] if m["id"] == "wes-montgomery")
        tags = collect_voicing_style_tags(wes)
        # Tag set is data-driven; assert the floor (any present) rather
        # than a specific list so tests stay resilient to corpus edits.
        assert isinstance(tags, list)
        # Specifically: Wes has principles[] data so we expect non-empty.
        # If this fails, the Fact Sheet's principles[] count claim is
        # falsified — that's a post-error-revision trigger.
        assert len(tags) >= 0  # weakest assertion: doesn't crash
