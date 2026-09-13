"""
domain/payment/entities.py
============================
Entité Payment — enregistrement d'un encaissement.

REFONTE : Payment est lié à un Enrollment (pas directement à l'élève).
L'année scolaire est implicite via l'Enrollment.
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from enum import Enum

from ..shared.value_objects import Money
from ..shared.errors import ZeroAmountError
from ..student.value_objects import StudentId
from ..enrollment.value_objects import EnrollmentId
from .value_objects import PaymentId, PaymentMethod


class PaymentState(str, Enum):
    VALID     = "VALID"
    PENDING   = "PENDING"    # créé côté portail parent, en attente de confirmation du paiement Mobile Money
    CANCELLED = "CANCELLED"


@dataclass
class Payment:
    id: PaymentId
    enrollment_id: EnrollmentId   # ← lié à l'Enrollment (année + classe + élève)
    student_id: StudentId          # dénormalisé pour les requêtes rapides
    amount: Money
    payment_date: datetime.date
    method: PaymentMethod
    receipt_number: str
    recorded_by: str
    state: PaymentState = PaymentState.VALID
    notes: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def __post_init__(self):
        if self.amount.is_zero():
            raise ZeroAmountError("Un paiement doit avoir un montant > 0 FCFA.")
        if self.payment_date > datetime.date.today():
            raise ValueError("La date de paiement ne peut pas être dans le futur.")
        if not self.receipt_number.strip():
            raise ValueError("Le numéro de reçu ne peut pas être vide.")
        if not self.recorded_by.strip():
            raise ValueError("Le nom de l'économe ne peut pas être vide.")

    def cancel(self, reason: str = "") -> None:
        self.state = PaymentState.CANCELLED
        if reason:
            self.notes = f"[ANNULÉ] {reason}" + (f" — {self.notes}" if self.notes else "")

    def confirm(self) -> None:
        """Transition PENDING → VALID : le paiement en ligne est confirmé par la passerelle."""
        self.state = PaymentState.VALID

    def is_valid(self) -> bool:
        return self.state == PaymentState.VALID

    def __str__(self) -> str:
        return f"{self.receipt_number} | {self.amount} | {self.payment_date}"
