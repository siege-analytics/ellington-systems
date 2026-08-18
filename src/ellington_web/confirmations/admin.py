from django.contrib import admin

from .models import Confirmation, Pedagogue


@admin.register(Pedagogue)
class PedagogueAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "created_at")
    search_fields = ("display_name", "user__username", "user__email")


@admin.register(Confirmation)
class ConfirmationAdmin(admin.ModelAdmin):
    list_display = ("usage_note", "pedagogue", "verdict", "created_at")
    list_filter = ("verdict", "pedagogue")
    search_fields = ("usage_note__note_id", "comment")
