from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from ellington_web.roster.models import GranularityBucket, Master, UsageNote

from .forms import ConfirmationForm
from .models import Confirmation, Pedagogue


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
