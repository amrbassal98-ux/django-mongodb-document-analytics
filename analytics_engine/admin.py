"""Admin configuration for the analytics_engine app."""

from django.contrib import admin

from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Admin interface for managing Document records."""
    list_display = ("title", "file_type", "uploaded_at")
    list_filter = ("file_type", "uploaded_at")
    search_fields = ("title", "raw_text")
    ordering = ("-uploaded_at",)

    fieldsets = (
        (
            None,
            {
                "fields": ("title", "file_type", "raw_text"),
            },
        ),
        (
            "Analysis",
            {
                "classes": ("collapse",),
                "fields": ("analysis_metadata", "polymorphic_payload"),
            },
        ),
        (
            "Annotations",
            {
                "classes": ("collapse",),
                "fields": ("annotations",),
            },
        ),
    )

    readonly_fields = ("uploaded_at",)
