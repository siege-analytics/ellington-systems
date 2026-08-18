"""End-to-end test for the load_corpus management command.

Uses a synthetic fixture that mimics the shape the pipeline agent
committed to producing: masters.jsonl, usage_notes.jsonl, and
granularity_index.json.
"""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from ellington_web.confirmations.models import Confirmation, Pedagogue  # noqa: F401
from ellington_web.roster.models import (
    Book,
    GranularityBucket,
    Master,
    UsageNote,
)


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    (tmp_path / "granularity_index.json").write_text(
        json.dumps({
            "a": {"name": "harmonic-family", "description": "Chord families.",
                    "role_count": 12, "sample_roles": ["I-IV-V", "ii-V"]},
            "e": {"name": "substitution-rules", "description": "Substitutions.",
                    "role_count": 30, "sample_roles": []},
        })
    )
    (tmp_path / "masters.jsonl").write_text("\n".join([
        json.dumps({
            "slug": "ted-greene",
            "display_name": "Ted Greene",
            "bio_blurb": "American jazz guitarist and educator.",
            "lived": "1946–2005",
            "instrument": "guitar",
            "traditions": ["jazz", "chord-melody"],
            "influenced": ["mick-goodrick"],
            "studied_with": [],
            "bucket_distribution": {"a": 50, "e": 34, "d": 20},
            "total_notes": 104,
            "principles_count": 40,
            "books": [
                {"slug": "ted-greene-chord-chemistry", "title": "Chord Chemistry"},
            ],
        }),
        json.dumps({
            "slug": "martin-taylor",
            "display_name": "Martin Taylor",
            "bio_blurb": "Scottish jazz guitarist.",
            "bucket_distribution": {},
            "total_notes": 0,
            "principles_count": 0,
            "books": [{"slug": "martin-taylor-solo-jazz", "title": "Solo Jazz"}],
        }),
    ]))
    (tmp_path / "usage_notes.jsonl").write_text("\n".join([
        json.dumps({
            "note_id": "ted-greene__ted-greene-chord-chemistry__0001",
            "master_slug": "ted-greene",
            "book_slug": "ted-greene-chord-chemistry",
            "book_title": "Chord Chemistry",
            "run_id": "run-42",
            "chord_quality": "Maj7",
            "function_role": "Tonic prolongation over ii-V-I",
            "granularity_level": "a",
            "granularity_name": "harmonic-family",
            "note_text": "Ted treats the Maj7 as a family and rotates voicings...",
            "source_principle_ids": ["p-17"],
            "provenance": {"page": 42},
            "references": [],
        }),
        json.dumps({
            "note_id": "ted-greene__ted-greene-chord-chemistry__0002",
            "master_slug": "ted-greene",
            "book_slug": "ted-greene-chord-chemistry",
            "book_title": "Chord Chemistry",
            "chord_quality": "7alt",
            "function_role": "Dominant substitution",
            "granularity_level": "e",
            "granularity_name": "substitution-rules",
            "note_text": "Alt-dominant with tritone sub as a default.",
        }),
    ]))
    return tmp_path


@pytest.mark.django_db
def test_load_corpus_populates_all_tables(corpus_dir: Path) -> None:
    out = StringIO()
    call_command("load_corpus", str(corpus_dir), stdout=out)

    assert GranularityBucket.objects.count() == 9  # all 9 levels present
    a = GranularityBucket.objects.get(pk="a")
    assert a.name == "harmonic-family"
    assert a.description == "Chord families."

    assert Master.objects.count() == 2
    ted = Master.objects.get(pk="ted-greene")
    assert ted.total_notes == 104
    assert ted.has_notes is True
    assert ted.bucket_distribution == {"a": 50, "e": 34, "d": 20}

    pending = Master.objects.get(pk="martin-taylor")
    assert pending.has_notes is False

    assert Book.objects.count() == 2
    cc = Book.objects.get(pk="ted-greene-chord-chemistry")
    assert cc.note_count == 2

    assert UsageNote.objects.count() == 2
    n1 = UsageNote.objects.get(
        pk="ted-greene__ted-greene-chord-chemistry__0001"
    )
    assert n1.granularity_level == "a"
    assert "family" in n1.note_text
    assert n1.master_id == "ted-greene"


@pytest.mark.django_db
def test_load_corpus_is_idempotent(corpus_dir: Path) -> None:
    out = StringIO()
    call_command("load_corpus", str(corpus_dir), stdout=out)
    call_command("load_corpus", str(corpus_dir), stdout=out)
    assert Master.objects.count() == 2
    assert UsageNote.objects.count() == 2
    assert Book.objects.count() == 2


@pytest.mark.django_db
def test_load_corpus_dry_run_rolls_back(corpus_dir: Path) -> None:
    out = StringIO()
    call_command("load_corpus", str(corpus_dir), "--dry-run", stdout=out)
    assert Master.objects.count() == 0
    assert UsageNote.objects.count() == 0


@pytest.fixture
def corpus_with_orphan_note(corpus_dir: Path) -> Path:
    # Append a note that references a master_slug not present in
    # masters.jsonl. Mirrors the real bill-carter/brent-greenan/coker
    # pipeline export bug we hit against live data.
    notes = (corpus_dir / "usage_notes.jsonl").read_text().splitlines()
    notes.append(json.dumps({
        "note_id": "bill-carter__complete-fingerstyle-jazz-guitar__0001",
        "master_slug": "bill-carter",
        "book_slug": "complete-fingerstyle-jazz-guitar",
        "book_title": "Complete Fingerstyle Jazz Guitar",
        "chord_quality": "Maj7",
        "function_role": "Tonic",
        "granularity_level": "a",
        "granularity_name": "harmonic-family",
        "note_text": "Bill treats Maj7 as tonic anchor.",
    }))
    (corpus_dir / "usage_notes.jsonl").write_text("\n".join(notes))
    return corpus_dir


@pytest.mark.django_db
def test_load_corpus_stubs_orphan_masters_by_default(
    corpus_with_orphan_note: Path,
) -> None:
    out = StringIO()
    call_command("load_corpus", str(corpus_with_orphan_note), stdout=out)
    bill = Master.objects.get(pk="bill-carter")
    assert bill.display_name == "Bill Carter"
    assert bill.total_notes == 1
    assert bill.bucket_distribution == {"a": 1}
    assert "Stubbed" in out.getvalue()


@pytest.mark.django_db
def test_load_corpus_strict_mode_fails_on_orphan(
    corpus_with_orphan_note: Path,
) -> None:
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="Unknown master 'bill-carter'"):
        call_command(
            "load_corpus", str(corpus_with_orphan_note),
            "--strict", stdout=StringIO(),
        )
