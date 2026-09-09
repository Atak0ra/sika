from django.contrib import admin
from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "sender_name",
        "receiver_name",
        "source_country",
        "destination_country",
        "amount",
        "send_currency",
        "commission",
        "status",
        "agent_name",
        "created_at",
    )
    list_filter = ("status", "source_country", "destination_country", "send_currency")
    search_fields = ("sender_name", "receiver_name", "agent_name")
    date_hierarchy = "created_at"
    readonly_fields = ("id",)
    ordering = ("-created_at",)
