from django.contrib import admin

from .models import Book, GranularityBucket, Master, UsageNote


@admin.register(GranularityBucket)
class GranularityBucketAdmin(admin.ModelAdmin):
    list_display = ("level", "name", "role_count")


@admin.register(Master)
class MasterAdmin(admin.ModelAdmin):
    list_display = ("slug", "display_name", "total_notes", "principles_count")
    search_fields = ("slug", "display_name")


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("slug", "title", "master", "note_count")
    list_filter = ("master",)
    search_fields = ("slug", "title")


@admin.register(UsageNote)
class UsageNoteAdmin(admin.ModelAdmin):
    list_display = (
        "note_id", "master", "book", "chord_quality", "function_role",
        "granularity_level",
    )
    list_filter = ("granularity_level", "master")
    search_fields = ("note_id", "chord_quality", "function_role", "note_text")
