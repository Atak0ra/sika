import uuid
from django.db import models


class Transaction(models.Model):
    class Status(models.TextChoices):
        COMPLETED = "completed", "Completee"
        PENDING   = "pending",   "En attente"
        CANCELLED = "cancelled", "Annulee"
        SUSPENDED = "suspended", "Suspendue"

    id                  = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender_name         = models.CharField(max_length=200)
    receiver_name       = models.CharField(max_length=200)
    source_country      = models.CharField(max_length=100, db_index=True)
    destination_country = models.CharField(max_length=100, db_index=True)
    agent_name          = models.CharField(max_length=200, db_index=True)
    amount              = models.DecimalField(max_digits=14, decimal_places=2)
    commission          = models.DecimalField(max_digits=10, decimal_places=2)
    send_currency       = models.CharField(max_length=10)
    payout_currency     = models.CharField(max_length=10)
    exchange_rate       = models.FloatField()
    status              = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at          = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["status", "created_at"],                 name="idx_status_created"),
            models.Index(fields=["source_country","destination_country"], name="idx_countries"),
        ]

    def __str__(self):
        return f"{self.sender_name} -> {self.receiver_name} | {self.amount} {self.send_currency}"
