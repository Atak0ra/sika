"""
domain/payment/value_objects.py
=================================
Value Objects du sous-domaine Paiement.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PaymentId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("PaymentId ne peut pas être vide.")

    @classmethod
    def generate(cls) -> PaymentId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


class PaymentMethod(str, Enum):
    """Moyen de paiement utilisé par le parent."""
    ESPECES      = "ESPECES"       # Paiement en cash
    MOBILE_MONEY = "MOBILE_MONEY"  # Orange Money, Wave, MTN…
    VIREMENT     = "VIREMENT"      # Virement bancaire
    CHEQUE       = "CHEQUE"        # Chèque (rare mais possible)


class PaymentStatus(str, Enum):
    """Statut de paiement calculé pour un élève à une date donnée."""
    SOLDE     = "SOLDE"      # 100% des frais payés
    EN_COURS  = "EN_COURS"   # Paiements en cours, pas encore en retard
    EN_RETARD = "EN_RETARD"  # Une ou plusieurs échéances dépassées non couvertes
    NON_PAYE  = "NON_PAYE"   # Aucun paiement enregistré

    @property
    def label(self) -> str:
        labels = {
            PaymentStatus.SOLDE:     "Soldé",
            PaymentStatus.EN_COURS:  "En cours",
            PaymentStatus.EN_RETARD: "En retard",
            PaymentStatus.NON_PAYE:  "Non payé",
        }
        return labels[self]
