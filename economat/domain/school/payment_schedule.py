"""
domain/school/payment_schedule.py
====================================
PaymentSchedule — la politique de paiement d'un niveau scolaire.

Concepts :
- PaymentMode : UNIQUE, MENSUEL, TRANCHES (3 tranches fixes).
- ExpectedInstallment : une échéance attendue (montant + date d'échéance).
- PaymentSchedule : génère les échéances à partir d'un total et d'un mode.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import List

from ..shared.value_objects import Money
from ..shared.errors import InvalidPaymentScheduleError


class PaymentMode(str, Enum):
    """Mode de paiement d'un niveau scolaire."""
    UNIQUE   = "UNIQUE"    # Paiement intégral à l'inscription
    MENSUEL  = "MENSUEL"   # Mensualités lissées sur l'année scolaire (10 mois)
    TRANCHES = "TRANCHES"  # 3 tranches : 40% + 30% + 30%


@dataclass(frozen=True)
class ExpectedInstallment:
    """Une échéance attendue.

    Attributes:
        label              : libellé humain ("Tranche 1", "Octobre"…).
        amount             : montant attendu (Money).
        due_date           : date limite de paiement.
        installment_number : numéro d'ordre (1, 2, 3…).
    """
    label: str
    amount: Money
    due_date: datetime.date
    installment_number: int


class PaymentSchedule:
    """Politique de paiement d'un niveau : génère les échéances attendues."""

    def __init__(
        self,
        mode: PaymentMode,
        total_amount: Money,
        installments: List[ExpectedInstallment],
    ) -> None:
        self._mode = mode
        self._total_amount = total_amount
        self._installments = installments
        self._validate()

    def _validate(self) -> None:
        """Invariant : la somme des tranches doit égaler le montant total."""
        if not self._installments:
            raise InvalidPaymentScheduleError("Un barème doit avoir au moins une échéance.")
        actual_total = Money.zero(self._total_amount.currency)
        for inst in self._installments:
            actual_total = actual_total.add(inst.amount)
        if actual_total != self._total_amount:
            raise InvalidPaymentScheduleError(
                f"La somme des échéances ({actual_total}) ≠ montant total ({self._total_amount})."
            )

    @property
    def mode(self) -> PaymentMode:
        return self._mode

    @property
    def total_amount(self) -> Money:
        return self._total_amount

    @property
    def installments(self) -> List[ExpectedInstallment]:
        return list(self._installments)  # copie défensive

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def for_unique(cls, total: Money, due_date: datetime.date) -> PaymentSchedule:
        """Paiement en une seule fois, dû à la date d'inscription."""
        inst = ExpectedInstallment("Paiement unique", total, due_date, 1)
        return cls(mode=PaymentMode.UNIQUE, total_amount=total, installments=[inst])

    @classmethod
    def for_tranches(cls, total: Money, school_year_start: datetime.date) -> PaymentSchedule:
        """3 tranches : 40% à l'inscription, 30% à J+3 mois, 30% à J+6 mois."""
        t1 = total.percentage(40)
        t3 = total.percentage(30)
        t2_amount = total.subtract(t1).subtract(t3)  # absorbe l'arrondi
        t2_date = _add_months(school_year_start, 3)
        t3_date = _add_months(school_year_start, 6)
        installments = [
            ExpectedInstallment("Tranche 1 (40%)", t1, school_year_start, 1),
            ExpectedInstallment("Tranche 2 (30%)", t2_amount, t2_date, 2),
            ExpectedInstallment("Tranche 3 (30%)", t3, t3_date, 3),
        ]
        return cls(mode=PaymentMode.TRANCHES, total_amount=total, installments=installments)

    @classmethod
    def for_mensuel(
        cls,
        total: Money,
        school_year_start: datetime.date,
        nb_months: int = 10,
    ) -> PaymentSchedule:
        """Mensualités lissées sur nb_months mois. Le dernier mois absorbe l'arrondi."""
        if nb_months < 1:
            raise InvalidPaymentScheduleError("Le nombre de mois doit être >= 1.")
        monthly_base = Money(total.amount // nb_months, total.currency)
        remainder = total.subtract(monthly_base.multiply(nb_months))
        months_fr = ["Octobre", "Novembre", "Décembre", "Janvier", "Février",
                     "Mars", "Avril", "Mai", "Juin", "Juillet"]
        installments: List[ExpectedInstallment] = []
        for i in range(nb_months):
            due = _add_months(school_year_start, i)
            label = months_fr[i] if i < len(months_fr) else f"Mois {i + 1}"
            amount = monthly_base.add(remainder) if i == nb_months - 1 else monthly_base
            installments.append(ExpectedInstallment(label, amount, due, i + 1))
        return cls(mode=PaymentMode.MENSUEL, total_amount=total, installments=installments)


# ── Utilitaire de date ────────────────────────────────────────────────────────

def _add_months(d: datetime.date, months: int) -> datetime.date:
    """Ajoute un nombre de mois à une date (gère le dépassement d'année)."""
    import calendar
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)
