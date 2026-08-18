"""Email helpers for the confirmations app.

Sends invitation links to prospective pedagogues. In dev this uses the
console email backend (see settings); in prod, configure Django's
EMAIL_BACKEND / EMAIL_HOST / etc. via environment.
"""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from .models import PedagogueInvite


def build_invite_url(invite: PedagogueInvite, *, base_url: str) -> str:
    return base_url.rstrip("/") + reverse("redeem_invite", args=[invite.token])


def send_invite_email(invite: PedagogueInvite, *, base_url: str) -> int:
    url = build_invite_url(invite, base_url=base_url)
    subject = "You're invited to review jazz-guitar teaching materials on Ellington"
    body = (
        f"Hi {invite.display_name},\n\n"
        f"Siege Analytics is asking guitar teachers to validate the way "
        f"we've classified passages from the corpus of jazz-guitar teaching "
        f"literature. You've been invited to set up an account.\n\n"
        f"Follow this link to create your login:\n\n"
        f"    {url}\n\n"
        f"The link expires {invite.expires_at:%Y-%m-%d %H:%M} UTC.\n\n"
        f"— Ellington"
    )
    return send_mail(
        subject=subject,
        message=body,
        from_email=getattr(
            settings, "DEFAULT_FROM_EMAIL", "no-reply@ellington.local"
        ),
        recipient_list=[invite.email],
        fail_silently=False,
    )
