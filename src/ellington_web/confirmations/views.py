from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ellington_web.roster.models import GranularityBucket, Master, UsageNote

from .forms import ConfirmationForm, InviteRedemptionForm
from .models import Confirmation, Pedagogue, PedagogueInvite


def _pedagogue_for(request: HttpRequest) -> Pedagogue | None:
    if not request.user.is_authenticated:
        return None
    return Pedagogue.objects.filter(user=request.user).first()


@login_required
def review_master(request: HttpRequest, master_slug: str) -> HttpResponse:
    master = get_object_or_404(Master, pk=master_slug)
    notes = master.usage_notes.annotate(
        confirmed_count=Count("confirmations", filter=~Q(confirmations=None)),
    ).order_by("book__title", "note_id")
    return render(
        request,
        "confirmations/review_master.html",
        {"master": master, "notes": notes},
    )


@login_required
def review_note(
    request: HttpRequest, master_slug: str, note_id: str
) -> HttpResponse:
    master = get_object_or_404(Master, pk=master_slug)
    note = get_object_or_404(UsageNote, pk=note_id, master=master)
    pedagogue = _pedagogue_for(request)
    if pedagogue is None:
        messages.error(
            request,
            "Only invited pedagogues can submit confirmations. "
            "Ask an admin to link a Pedagogue profile to your account.",
        )
        return redirect("roster:master_detail", slug=master.slug)

    existing = Confirmation.objects.filter(
        usage_note=note, pedagogue=pedagogue
    ).first()

    if request.method == "POST":
        form = ConfirmationForm(request.POST, instance=existing)
        if form.is_valid():
            confirmation = form.save(commit=False)
            confirmation.usage_note = note
            confirmation.pedagogue = pedagogue
            confirmation.save()
            messages.success(request, f"Recorded verdict for {note.note_id}.")
            next_note = _next_unreviewed(master, pedagogue, after=note.note_id)
            if next_note is not None:
                return redirect(
                    "confirmations:review_note",
                    master_slug=master.slug,
                    note_id=next_note.note_id,
                )
            return redirect("confirmations:review_master", master_slug=master.slug)
    else:
        form = ConfirmationForm(instance=existing)

    bucket = None
    if note.granularity_level:
        bucket = GranularityBucket.objects.filter(
            level=note.granularity_level
        ).first()

    return render(
        request,
        "confirmations/review_note.html",
        {
            "master": master,
            "note": note,
            "bucket": bucket,
            "form": form,
            "existing": existing,
        },
    )


def _next_unreviewed(
    master: Master, pedagogue: Pedagogue, after: str
) -> UsageNote | None:
    return (
        master.usage_notes.exclude(confirmations__pedagogue=pedagogue)
        .filter(note_id__gt=after)
        .order_by("note_id")
        .first()
    )


def redeem_invite(request: HttpRequest, token: str) -> HttpResponse:
    """Public view: accept a one-time invite token, create User+Pedagogue.

    On success, log the new user in and redirect to the master roster so
    they can start reviewing. On any error (bad token, expired, already
    redeemed, form-invalid) render the same page with an explanation.
    """
    invite = PedagogueInvite.objects.filter(token=token).first()
    if invite is None:
        return render(
            request, "confirmations/invite_error.html",
            {"reason": "unknown"}, status=404,
        )
    if invite.is_redeemed:
        return render(
            request, "confirmations/invite_error.html",
            {"reason": "redeemed", "invite": invite}, status=410,
        )
    if invite.is_expired:
        return render(
            request, "confirmations/invite_error.html",
            {"reason": "expired", "invite": invite}, status=410,
        )

    if request.method == "POST":
        form = InviteRedemptionForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Re-lock the invite row to make double-redemption a hard
                # error under concurrent requests rather than silently
                # binding two users to the same invite.
                locked = PedagogueInvite.objects.select_for_update().get(
                    pk=invite.pk
                )
                if locked.is_redeemed:
                    messages.error(
                        request, "This invite was just redeemed by another session."
                    )
                    return redirect("redeem_invite", token=token)
                user = get_user_model().objects.create_user(
                    username=form.cleaned_data["username"],
                    email=invite.email,
                    password=form.cleaned_data["password"],
                )
                pedagogue = Pedagogue.objects.create(
                    user=user,
                    display_name=invite.display_name,
                    credentials=invite.credentials,
                )
                locked.redeemed_at = timezone.now()
                locked.redeemed_pedagogue = pedagogue
                locked.save(update_fields=["redeemed_at", "redeemed_pedagogue"])
            login(request, user)
            messages.success(
                request,
                f"Welcome, {pedagogue.display_name}. Pick a master to start reviewing.",
            )
            return redirect("roster:master_list")
    else:
        form = InviteRedemptionForm()

    return render(
        request, "confirmations/redeem_invite.html",
        {"invite": invite, "form": form},
    )
