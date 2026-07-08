"""Load the pipeline corpus export into the Ellington DB.

Expects three files, produced by the musescore4-chord-library-plugin
pipeline agent:

- granularity_index.json  (9 buckets a-i)
- masters.jsonl           (34 masters, one per line)
- usage_notes.jsonl       (1,784 notes, one per line, full narratives)

Idempotent: uses stable slugs / note_ids as PKs, so re-runs upsert rather
than duplicate. Missing bucket letters, empty distributions, and 0-note
masters are all valid input states — the pipeline agent flagged 8 masters
as "lessons pending" and this loader must not choke on them.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ellington_web.roster.models import (
    GRANULARITY_LEVELS,
    Book,
    GranularityBucket,
    Master,
    UsageNote,
)


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                yield json.loads(raw)
            except json.JSONDecodeError as exc:
                raise CommandError(
                    f"{path.name} line {lineno}: {exc}"
                ) from exc


class Command(BaseCommand):
    help = "Load masters, books, usage notes, and granularity buckets."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "corpus_dir",
            type=Path,
            help="Directory containing the three export files.",
        )
        parser.add_argument(
            "--masters-file", default="masters.jsonl",
            help="Filename inside corpus_dir. Default: masters.jsonl",
        )
        parser.add_argument(
            "--notes-file", default="usage_notes.jsonl",
            help="Filename inside corpus_dir. Default: usage_notes.jsonl",
        )
        parser.add_argument(
            "--index-file", default="granularity_index.json",
            help="Filename inside corpus_dir. Default: granularity_index.json",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and validate but roll back the transaction.",
        )

    def handle(self, *args, **opts) -> None:
        corpus_dir: Path = opts["corpus_dir"]
        if not corpus_dir.is_dir():
            raise CommandError(f"Not a directory: {corpus_dir}")

        index_path = corpus_dir / opts["index_file"]
        masters_path = corpus_dir / opts["masters_file"]
        notes_path = corpus_dir / opts["notes_file"]
        for p in (index_path, masters_path, notes_path):
            if not p.is_file():
                raise CommandError(f"Missing required file: {p}")

        with transaction.atomic():
            n_buckets = self._load_buckets(index_path)
            n_masters, n_books = self._load_masters(masters_path)
            n_notes = self._load_notes(notes_path)
            if opts["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run — rolled back."))

        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded: {n_buckets} buckets, {n_masters} masters, "
                f"{n_books} books, {n_notes} usage notes."
            )
        )

    def _load_buckets(self, path: Path) -> int:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        bucket_name_map = dict(GRANULARITY_LEVELS)
        count = 0
        for level, name in GRANULARITY_LEVELS:
            entry = data.get(level, {}) if isinstance(data, dict) else {}
            GranularityBucket.objects.update_or_create(
                level=level,
                defaults={
                    "name": entry.get("name") or bucket_name_map[level],
                    "description": entry.get("description", ""),
                    "role_count": entry.get("role_count", 0),
                    "sample_roles": entry.get("sample_roles", []),
                },
            )
            count += 1
        return count

    def _load_masters(self, path: Path) -> tuple[int, int]:
        master_count = 0
        book_count = 0
        for row in _iter_jsonl(path):
            slug = row["slug"]
            master, _ = Master.objects.update_or_create(
                slug=slug,
                defaults={
                    "display_name": row.get("display_name", slug),
                    "bio_blurb": row.get("bio_blurb", "") or "",
                    "lived": row.get("lived", "") or "",
                    "instrument": row.get("instrument", "") or "",
                    "traditions": row.get("traditions", []) or [],
                    "influenced": row.get("influenced", []) or [],
                    "studied_with": row.get("studied_with", []) or [],
                    "bucket_distribution": row.get("bucket_distribution", {}) or {},
                    "total_notes": row.get("total_notes", 0) or 0,
                    "principles_count": row.get("principles_count", 0) or 0,
                },
            )
            master_count += 1
            for book in row.get("books", []) or []:
                Book.objects.update_or_create(
                    slug=book["slug"],
                    defaults={
                        "title": book.get("title", book["slug"]),
                        "master": master,
                    },
                )
                book_count += 1
        return master_count, book_count

    def _load_notes(self, path: Path) -> int:
        count = 0
        book_note_counts: dict[str, int] = {}
        for row in _iter_jsonl(path):
            master_slug = row["master_slug"]
            book_slug = row["book_slug"]
            try:
                master = Master.objects.get(pk=master_slug)
            except Master.DoesNotExist as exc:
                raise CommandError(
                    f"Unknown master '{master_slug}' referenced by note "
                    f"{row.get('note_id')}"
                ) from exc
            book, _ = Book.objects.get_or_create(
                slug=book_slug,
                defaults={
                    "title": row.get("book_title", book_slug),
                    "master": master,
                },
            )
            UsageNote.objects.update_or_create(
                note_id=row["note_id"],
                defaults={
                    "master": master,
                    "book": book,
                    "run_id": row.get("run_id", "") or "",
                    "chord_quality": row.get("chord_quality", "") or "",
                    "function_role": row.get("function_role", "") or "",
                    "granularity_level": row.get("granularity_level", "") or "",
                    "granularity_name": row.get("granularity_name", "") or "",
                    "note_text": row.get("note_text", "") or "",
                    "source_principle_ids": row.get("source_principle_ids", []) or [],
                    "provenance": row.get("provenance", {}) or {},
                    "references": row.get("references", []) or [],
                },
            )
            book_note_counts[book_slug] = book_note_counts.get(book_slug, 0) + 1
            count += 1

        for slug, n in book_note_counts.items():
            Book.objects.filter(pk=slug).update(note_count=n)
        return count
