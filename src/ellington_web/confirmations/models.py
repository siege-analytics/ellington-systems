"""Pedagogue confirmation workflow models.

A Pedagogue is an invited guitar teacher who reviews the s5 classifications
of usage_notes. Their verdict on each note is a Confirmation row.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from ellington_web.roster.models import UsageNote


INVITE_TOKEN_BYTES = 32
INVITE_DEFAULT_TTL_DAYS = 14


def _new_invite_token() -> str:
    return secrets.token_urlsafe(INVITE_TOKEN_BYTES)


def _default_invite_expiry():
    return timezone.now() + timedelta(days=INVITE_DEFAULT_TTL_DAYS)


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


class PedagogueInvite(models.Model):
    """Single-use invitation that redeems into a Pedagogue + User pair.

    Issued from the admin (or a mgmt command). Redemption is a public URL
    that verifies the token, creates a Django auth user + Pedagogue row,
    marks the invite redeemed, and logs the invitee in.
    """

    token = models.CharField(
        max_length=128, unique=True, default=_new_invite_token, editable=False
    )
    email = models.EmailField()
    display_name = models.CharField(max_length=255)
    credentials = models.TextField(
        blank=True,
        help_text="Optional biographical / credential text carried onto the Pedagogue.",
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="pedagogue_invites_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_invite_expiry)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    redeemed_pedagogue = models.OneToOneField(
        Pedagogue,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="redeemed_from_invite",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["email"])]

    def __str__(self) -> str:
        return f"invite<{self.email}>"

    @property
    def is_redeemed(self) -> bool:
        return self.redeemed_at is not None

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return not self.is_redeemed and not self.is_expired
