from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from ellington_web.confirmations.mail import build_invite_url, send_invite_email
from ellington_web.confirmations.models import (
    Confirmation,
    Pedagogue,
    PedagogueInvite,
)
from ellington_web.roster.models import Book, GranularityBucket, Master, UsageNote


@pytest.fixture
def invite(db) -> PedagogueInvite:
    return PedagogueInvite.objects.create(
        email="teacher@example.com",
        display_name="Teacher T.",
        credentials="Berklee, 20 years teaching",
    )


@pytest.fixture
def note_scenario(db):
    GranularityBucket.objects.create(
        level="a", name="harmonic-family", description="Families of chords."
    )
    master = Master.objects.create(
        slug="ted-greene", display_name="Ted Greene", total_notes=1,
    )
    book = Book.objects.create(
        slug="ted-greene-chord-chemistry", title="Chord Chemistry", master=master,
    )
    note = UsageNote.objects.create(
        note_id="ted-greene__ted-greene-chord-chemistry__0001",
        master=master, book=book,
        chord_quality="Maj7", function_role="Tonic",
        granularity_level="a", granularity_name="harmonic-family",
        note_text="Ted treats Maj7 as a family.",
    )
    return {"master": master, "note": note}


def test_invite_defaults(invite: PedagogueInvite) -> None:
    assert invite.token
    assert len(invite.token) > 20
    assert invite.is_usable
    assert not invite.is_redeemed
    assert not invite.is_expired


def test_redeem_page_renders_for_valid_token(invite, client: Client) -> None:
    r = client.get(reverse("redeem_invite", args=[invite.token]))
    assert r.status_code == 200
    assert b"teacher@example.com" in r.content
    assert b"Teacher T." in r.content


def test_unknown_token_404s(client: Client, db) -> None:
    r = client.get(reverse("redeem_invite", args=["not-a-real-token"]))
    assert r.status_code == 404
    assert b"does not match" in r.content


def test_expired_invite_shows_expiry_page(invite, client: Client) -> None:
    invite.expires_at = timezone.now() - timedelta(days=1)
    invite.save(update_fields=["expires_at"])
    r = client.get(reverse("redeem_invite", args=[invite.token]))
    assert r.status_code == 410
    assert b"expired" in r.content


def test_already_redeemed_invite_shows_redeemed_page(
    invite, client: Client
) -> None:
    invite.redeemed_at = timezone.now()
    invite.save(update_fields=["redeemed_at"])
    r = client.get(reverse("redeem_invite", args=[invite.token]))
    assert r.status_code == 410
    assert b"already redeemed" in r.content


def test_successful_redemption_creates_user_and_pedagogue(
    invite, note_scenario, client: Client
) -> None:
    url = reverse("redeem_invite", args=[invite.token])
    r = client.post(url, {
        "username": "teachert",
        "password": "correct-horse-battery-staple",
        "password_confirm": "correct-horse-battery-staple",
    })
    assert r.status_code == 302
    assert r["Location"] == reverse("roster:master_list")

    User = get_user_model()
    user = User.objects.get(username="teachert")
    assert user.email == "teacher@example.com"
    pedagogue = Pedagogue.objects.get(user=user)
    assert pedagogue.display_name == "Teacher T."
    assert pedagogue.credentials == "Berklee, 20 years teaching"

    invite.refresh_from_db()
    assert invite.is_redeemed
    assert invite.redeemed_pedagogue == pedagogue

    # Should now be able to review a note.
    review_url = reverse(
        "confirmations:review_note",
        args=[note_scenario["master"].slug, note_scenario["note"].note_id],
    )
    r = client.post(review_url, {
        "verdict": "confirm",
        "corrected_granularity_level": "",
        "corrected_function_role": "",
        "comment": "",
    })
    assert r.status_code == 302
    assert Confirmation.objects.filter(pedagogue=pedagogue).count() == 1


def test_password_mismatch_rejects(invite, client: Client) -> None:
    url = reverse("redeem_invite", args=[invite.token])
    r = client.post(url, {
        "username": "teachert",
        "password": "correct-horse-battery-staple",
        "password_confirm": "wrong-passphrase-here",
    })
    assert r.status_code == 200
    assert b"Passwords do not match" in r.content
    assert not get_user_model().objects.filter(username="teachert").exists()
    invite.refresh_from_db()
    assert not invite.is_redeemed


def test_taken_username_rejects(invite, client: Client) -> None:
    get_user_model().objects.create_user("teachert", password="x")
    url = reverse("redeem_invite", args=[invite.token])
    r = client.post(url, {
        "username": "teachert",
        "password": "correct-horse-battery-staple",
        "password_confirm": "correct-horse-battery-staple",
    })
    assert r.status_code == 200
    assert b"already taken" in r.content
    invite.refresh_from_db()
    assert not invite.is_redeemed


def test_weak_password_rejects(invite, client: Client) -> None:
    url = reverse("redeem_invite", args=[invite.token])
    r = client.post(url, {
        "username": "teachert",
        "password": "abc12345",
        "password_confirm": "abc12345",
    })
    # Django's default MinimumLengthValidator (8) passes, but the whole
    # validator stack should reject "abc12345" as too common.
    assert r.status_code == 200
    invite.refresh_from_db()
    assert not invite.is_redeemed


def test_send_invite_email_dispatches(
    invite, settings, mailoutbox
) -> None:
    settings.ELLINGTON_PUBLIC_BASE_URL = "https://ellington.example.com"
    n = send_invite_email(invite, base_url=settings.ELLINGTON_PUBLIC_BASE_URL)
    assert n == 1
    assert len(mailoutbox) == 1
    msg = mailoutbox[0]
    assert msg.to == ["teacher@example.com"]
    expected_url = build_invite_url(
        invite, base_url="https://ellington.example.com"
    )
    assert expected_url in msg.body


def test_authenticated_non_pedagogue_cannot_confirm(
    note_scenario, client: Client
) -> None:
    # This is F1 from the previous PR's self-review — covering the
    # non-pedagogue-user path now that invite work exercises the same code.
    user = get_user_model().objects.create_user("randomuser", password="pw")
    client.force_login(user)
    url = reverse(
        "confirmations:review_note",
        args=[
            note_scenario["master"].slug,
            note_scenario["note"].note_id,
        ],
    )
    r = client.post(url, {"verdict": "confirm"})
    assert r.status_code == 302
    assert r["Location"].endswith(
        reverse("roster:master_detail", args=[note_scenario["master"].slug])
    )
    assert Confirmation.objects.count() == 0


@pytest.fixture
def mailoutbox(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail.outbox = []
    return mail.outbox
