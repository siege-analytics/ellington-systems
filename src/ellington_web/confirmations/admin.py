from django.contrib import admin, messages
from django.utils.html import format_html

from .mail import build_invite_url, send_invite_email
from .models import Confirmation, Pedagogue, PedagogueInvite


@admin.register(Pedagogue)
class PedagogueAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at")
    search_fields = ("display_name", "user__username", "user__email")


@admin.register(Confirmation)
class ConfirmationAdmin(admin.ModelAdmin):
    list_display = ("usage_note", "pedagogue", "verdict", "created_at")
    list_filter = ("verdict", "pedagogue")
    search_fields = ("usage_note__note_id", "comment")


@admin.action(description="Email the invite link to the invitee")
def resend_invite_email(modeladmin, request, queryset):
    from django.conf import settings
    base_url = getattr(
        settings, "ELLINGTON_PUBLIC_BASE_URL", "http://localhost:8000"
    )
    sent = 0
    skipped = 0
    for invite in queryset:
        if not invite.is_usable:
            skipped += 1
            continue
        send_invite_email(invite, base_url=base_url)
        sent += 1
    if sent:
        messages.success(request, f"Sent {sent} invite email(s).")
    if skipped:
        messages.warning(
            request,
            f"Skipped {skipped} invite(s) that were already redeemed or expired.",
        )


@admin.register(PedagogueInvite)
class PedagogueInviteAdmin(admin.ModelAdmin):
    list_display = (
        "email", "display_name", "created_at", "expires_at",
        "redeemed_at", "invited_by",
    )
    readonly_fields = (
        "token", "created_at", "redeemed_at", "redeemed_pedagogue",
        "redemption_url",
    )
    search_fields = ("email", "display_name")
    actions = [resend_invite_email]

    def redemption_url(self, obj) -> str:
        if not obj.pk:
            return "(save first to generate)"
        from django.conf import settings
        base = getattr(
            settings, "ELLINGTON_PUBLIC_BASE_URL", "http://localhost:8000"
        )
        url = build_invite_url(obj, base_url=base)
        return format_html('<a href="{}">{}</a>', url, url)
    redemption_url.short_description = "Redemption URL"

    def save_model(self, request, obj, form, change):
        if not obj.pk and obj.invited_by_id is None:
            obj.invited_by = request.user
        super().save_model(request, obj, form, change)
