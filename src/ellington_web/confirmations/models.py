"""Pedagogue confirmation workflow models.

A Pedagogue is an invited guitar teacher who reviews the s5 classifications
of usage_notes. Their verdict on each note is a Confirmation row.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from ellington_web.roster.models import UsageNote


class Pedagogue(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pedagogue_profile",
    )
    display_name = models.CharField(max_length=255)
    credentials = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class Confirmation(models.Model):
    class Verdict(models.TextChoices):
        CONFIRM = "confirm", "Confirm classification"
        CORRECT = "correct", "Correct classification"
        NUANCE = "nuance", "Add nuance"
        REREVIEW = "rereview", "Flag for re-review"

    usage_note = models.ForeignKey(
        UsageNote, on_delete=models.CASCADE, related_name="confirmations"
    )
    pedagogue = models.ForeignKey(
        Pedagogue, on_delete=models.CASCADE, related_name="confirmations"
    )
    verdict = models.CharField(max_length=16, choices=Verdict.choices)
    corrected_granularity_level = models.CharField(
        max_length=1, blank=True,
        help_text="Only set when verdict=correct and the bucket should change.",
    )
    corrected_function_role = models.CharField(
        max_length=255, blank=True,
        help_text="Only set when verdict=correct and the role text should change.",
    )
    comment = models.TextField(
        blank=True,
        help_text="Free-form nuance or explanation. Required for nuance/rereview.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["usage_note", "pedagogue"],
                name="one_confirmation_per_pedagogue_per_note",
            ),
        ]
        indexes = [
            models.Index(fields=["verdict"]),
            models.Index(fields=["usage_note", "verdict"]),
        ]

    def __str__(self) -> str:
        return f"{self.pedagogue} → {self.usage_note} ({self.verdict})"
