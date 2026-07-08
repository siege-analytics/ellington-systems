"""Roster domain models.

Mirrors the export shape produced by the musescore4-chord-library-plugin
pipeline (see partner-agent handoff notes):

- masters.jsonl     -> Master
- usage_notes.jsonl -> UsageNote
- granularity_index.json -> GranularityBucket

Books are extracted from Master.books[] into their own table so that
UsageNote can FK to a canonical Book row.
"""

from __future__ import annotations

from django.db import models


GRANULARITY_LEVELS = [
    ("a", "harmonic-family"),
    ("b", "voicing-floor"),
    ("c", "omission-priority"),
    ("d", "color-tone-policy"),
    ("e", "substitution-rules"),
    ("f", "rhythmic-placement"),
    ("g", "voice-leading"),
    ("h", "idiom-application"),
    ("i", "other"),
]


class GranularityBucket(models.Model):
    level = models.CharField(max_length=1, primary_key=True)
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    role_count = models.PositiveIntegerField(default=0)
    sample_roles = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["level"]

    def __str__(self) -> str:
        return f"{self.level}: {self.name}"


class Master(models.Model):
    slug = models.SlugField(max_length=128, primary_key=True)
    display_name = models.CharField(max_length=255)
    bio_blurb = models.TextField(blank=True)
    lived = models.CharField(max_length=64, blank=True)
    instrument = models.CharField(max_length=128, blank=True)
    traditions = models.JSONField(default=list, blank=True)
    influenced = models.JSONField(default=list, blank=True)
    studied_with = models.JSONField(default=list, blank=True)
    bucket_distribution = models.JSONField(default=dict, blank=True)
    total_notes = models.PositiveIntegerField(default=0)
    principles_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name

    @property
    def has_notes(self) -> bool:
        return self.total_notes > 0

    def distribution_rows(self) -> list[dict]:
        # Ordered a-i, with human names + counts. Buckets not in the raw
        # distribution show as zero — templates render them consistently.
        rows = []
        dist = self.bucket_distribution or {}
        for level, name in GRANULARITY_LEVELS:
            count = int(dist.get(level, 0))
            rows.append({"level": level, "name": name, "count": count})
        return rows


class Book(models.Model):
    slug = models.SlugField(max_length=192, primary_key=True)
    title = models.CharField(max_length=512)
    master = models.ForeignKey(
        Master, on_delete=models.CASCADE, related_name="books"
    )
    note_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["master__display_name", "title"]

    def __str__(self) -> str:
        return f"{self.master.display_name} — {self.title}"


class UsageNote(models.Model):
    note_id = models.CharField(max_length=255, primary_key=True)
    master = models.ForeignKey(
        Master, on_delete=models.CASCADE, related_name="usage_notes"
    )
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name="usage_notes"
    )
    run_id = models.CharField(max_length=128, blank=True)
    chord_quality = models.CharField(max_length=128, blank=True)
    function_role = models.CharField(max_length=255, blank=True)
    granularity_level = models.CharField(
        max_length=1, choices=GRANULARITY_LEVELS, blank=True
    )
    granularity_name = models.CharField(max_length=64, blank=True)
    note_text = models.TextField(blank=True)
    source_principle_ids = models.JSONField(default=list, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    references = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["master__display_name", "book__title", "note_id"]
        indexes = [
            models.Index(fields=["granularity_level"]),
            models.Index(fields=["master", "granularity_level"]),
        ]

    def __str__(self) -> str:
        return self.note_id
