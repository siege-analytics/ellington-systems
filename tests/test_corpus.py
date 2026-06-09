"""Tests for `corpus.py`."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ellington_systems.corpus import Corpus, parse_chord_symbol


# ---------------------------------------------------------------------------
# parse_chord_symbol — covers the spike's chord-parsing surface
# ---------------------------------------------------------------------------


class TestParseChordSymbol:
    def test_single_letter_root(self) -> None:
        assert parse_chord_symbol("Cmaj7") == ("C", "maj7")

    def test_flat_root(self) -> None:
        assert parse_chord_symbol("Bbm7b5") == ("Bb", "m7b5")

    def test_sharp_root(self) -> None:
        assert parse_chord_symbol("F#13b9") == ("F#", "13b9")

    def test_quality_with_extensions(self) -> None:
        assert parse_chord_symbol("Gm7b5") == ("G", "m7b5")

    def test_no_quality(self) -> None:
        assert parse_chord_symbol("C") == ("C", "")

    def test_unknown_root_returned_empty(self) -> None:
        # Spike contract: caller can detect malformed input via empty root.
        assert parse_chord_symbol("Xunknown") == ("", "Xunknown")

    def test_empty_string(self) -> None:
        assert parse_chord_symbol("") == ("", "")

    def test_all_natural_roots(self) -> None:
        for root in "ABCDEFG":
            r, q = parse_chord_symbol(root + "maj7")
            assert r == root
            assert q == "maj7"


# ---------------------------------------------------------------------------
# Corpus — file-loader contract tests using synthetic fixtures
# ---------------------------------------------------------------------------


class TestCorpusSyntheticFixtures:
    @pytest.fixture()
    def synthetic_plugin_root(self, tmp_path: Path) -> Path:
        """Build a minimal valid plugin-clone-shape directory."""
        plugin_dir = tmp_path / "plugin" / "data"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "masters.json").write_text(
            json.dumps(
                {
                    "masters": [
                        {"id": "test-master-1", "principles": []},
                        {"id": "test-master-2", "principles": []},
                    ],
                    "schemaNote": "synthetic",
                    "version": "test",
                }
            )
        )
        (plugin_dir / "voicings.json").write_text(
            json.dumps(
                {
                    "voicings": [
                        {
                            "id": "v1",
                            "name": "v1",
                            "chord_quality": "maj7",
                            "root": "C",
                            "category": "shell",
                            "strings": 6,
                            "fret_number": 5,
                            "visible_frets": 4,
                        }
                    ]
                }
            )
        )
        return tmp_path

    def test_load_from_plugin_clone(self, synthetic_plugin_root: Path) -> None:
        corpus = Corpus.from_plugin_clone(synthetic_plugin_root)
        assert len(corpus.masters) == 2
        assert len(corpus.voicings) == 1
        assert "test-master-1" in corpus.masters_by_id
        assert "test-master-2" in corpus.masters_by_id

    def test_masters_by_id_lookup(self, synthetic_plugin_root: Path) -> None:
        corpus = Corpus.from_plugin_clone(synthetic_plugin_root)
        assert corpus.masters_by_id["test-master-1"]["id"] == "test-master-1"

    def test_missing_masters_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "plugin" / "data").mkdir(parents=True)
        (tmp_path / "plugin" / "data" / "voicings.json").write_text('{"voicings": []}')
        with pytest.raises(FileNotFoundError, match="masters.json"):
            Corpus.from_plugin_clone(tmp_path)

    def test_missing_voicings_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "plugin" / "data").mkdir(parents=True)
        (tmp_path / "plugin" / "data" / "masters.json").write_text(
            '{"masters": [], "schemaNote": "x", "version": "x"}'
        )
        with pytest.raises(FileNotFoundError, match="voicings.json"):
            Corpus.from_plugin_clone(tmp_path)

    def test_malformed_masters_wrapper_raises(self, tmp_path: Path) -> None:
        (tmp_path / "plugin" / "data").mkdir(parents=True)
        # Top-level array instead of wrapper object — should fail.
        (tmp_path / "plugin" / "data" / "masters.json").write_text("[]")
        (tmp_path / "plugin" / "data" / "voicings.json").write_text('{"voicings": []}')
        with pytest.raises(ValueError, match="wrapper object"):
            Corpus.from_plugin_clone(tmp_path)

    def test_malformed_voicings_wrapper_raises(self, tmp_path: Path) -> None:
        (tmp_path / "plugin" / "data").mkdir(parents=True)
        (tmp_path / "plugin" / "data" / "masters.json").write_text(
            '{"masters": [], "schemaNote": "x", "version": "x"}'
        )
        (tmp_path / "plugin" / "data" / "voicings.json").write_text("[]")
        with pytest.raises(ValueError, match="wrapper object"):
            Corpus.from_plugin_clone(tmp_path)


class TestCorpusFromEnv:
    def test_missing_env_var_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ELLINGTON_PLUGIN_PATH", raising=False)
        with pytest.raises(RuntimeError, match="ELLINGTON_PLUGIN_PATH"):
            Corpus.from_env()

    def test_empty_env_var_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ELLINGTON_PLUGIN_PATH", "")
        with pytest.raises(RuntimeError, match="ELLINGTON_PLUGIN_PATH"):
            Corpus.from_env()


# ---------------------------------------------------------------------------
# Live-plugin integration — requires the plugin clone via env var
# ---------------------------------------------------------------------------


@pytest.mark.requires_plugin
class TestCorpusLiveCorpus:
    def test_load_full_corpus(self, plugin_clone_path: str) -> None:
        corpus = Corpus.from_plugin_clone(plugin_clone_path)
        # Per Investigation Fact Sheet Entity 3: 29 masters.
        assert len(corpus.masters) == 29
        # Per Investigation Fact Sheet Entity 4: 820 voicings.
        assert len(corpus.voicings) == 820

    def test_pat_martino_in_corpus(self, plugin_clone_path: str) -> None:
        corpus = Corpus.from_plugin_clone(plugin_clone_path)
        assert "pat-martino" in corpus.masters_by_id

    def test_benson_present_with_zero_principles(
        self, plugin_clone_path: str
    ) -> None:
        # Documents Fact Sheet Finding 2 — benson is systems[]-only.
        corpus = Corpus.from_plugin_clone(plugin_clone_path)
        benson = corpus.masters_by_id["benson"]
        principles = benson.get("principles") or []
        assert len(principles) == 0
