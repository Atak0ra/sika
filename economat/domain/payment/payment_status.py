"""
domain/payment/payment_status.py
===================================
Service de domaine : PaymentStatusCalculator

Calcule le statut de paiement d'un élève en comparant :
  - Les échéances ATTENDUES (issues du barème PaymentSchedule du niveau).
  - Les paiements RÉELS enregistrés par l'économe.
  - La date d'évaluation (aujourd'hui par défaut).

Retourne un PaymentStatusResult avec :
  - status       : SOLDE / EN_COURS / EN_RETARD / NON_PAYE
  - total_due    : montant total attendu sur l'année
  - total_paid   : montant versé (paiements valides uniquement)
  - balance      : reste à payer (0 si soldé)
  - overdue      : montant des tranches échues non couvertes

C'est un SERVICE DE DOMAINE (stateless) : pas de DB, pur calcul sur les objets.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import List, Optional

from ..shared.value_objects import Money, Currency
from ..school.payment_schedule import PaymentSchedule
from .entities import Payment
from .value_objects import PaymentStatus


@dataclass(frozen=True)
class PaymentStatusResult:
    """Résultat du calcul de statut de paiement d'un élève."""
    status: PaymentStatus
    total_due: Money
    total_paid: Money
    balance: Money
    overdue_amount: Money
    next_installment_label: Optional[str] = None
    next_due_date: Optional[datetime.date] = None
    # ── Enrichissement BI ────────────────────────────────────────────────────
    oldest_overdue_date: Optional[datetime.date] = None   # date de la 1ʳᵉ échéance impayée
    days_late: int = 0                                     # jours de retard sur cette échéance

    @property
    def is_fully_paid(self) -> bool:
        return self.status == PaymentStatus.SOLDE

    @property
    def is_late(self) -> bool:
        return self.status == PaymentStatus.EN_RETARD

    def summary(self) -> str:
        lines = [
            f"Statut     : {self.status.label}",
            f"Total dû   : {self.total_due}",
            f"Payé       : {self.total_paid}",
            f"Reste      : {self.balance}",
        ]
        if self.overdue_amount.amount > 0:
            lines.append(f"En retard  : {self.overdue_amount}")
        if self.next_due_date:
            lines.append(f"Prochaine  : {self.next_installment_label} le {self.next_due_date}")
        return "\n".join(lines)


class PaymentStatusCalculator:
    """Service de domaine stateless — calcule le statut de paiement.

    Usage :
        result = PaymentStatusCalculator().calculate(schedule, payments)
    """

    def calculate(
        self,
        schedule: PaymentSchedule,
        payments: List[Payment],
        as_of: Optional[datetime.date] = None,
    ) -> PaymentStatusResult:
        """Calcule le statut de paiement à une date donnée.

        Args:
            schedule : barème d'échéances du niveau (PaymentSchedule).
            payments : liste des Payment enregistrés pour cet élève.
            as_of    : date d'évaluation (today par défaut).
        """
        today = as_of or datetime.date.today()
        currency = schedule.total_amount.currency

        # 1. Total versé = somme des paiements VALIDES uniquement
        total_paid = Money.zero(currency)
        for p in payments:
            if p.is_valid():
                total_paid = total_paid.add(p.amount)

        total_due = schedule.total_amount
        balance = total_due.subtract(total_paid) if total_paid <= total_due else Money.zero(currency)

        # 2. Cas soldé
        if balance.is_zero():
            return PaymentStatusResult(
                status=PaymentStatus.SOLDE,
                total_due=total_due, total_paid=total_paid,
                balance=balance, overdue_amount=Money.zero(currency),
            )

        # 3. Aucun paiement enregistré
        if total_paid.is_zero():
            first = schedule.installments[0]
            is_late = first.due_date <= today
            oldest_date = first.due_date if is_late else None
            days_late = (today - first.due_date).days if is_late else 0
            return PaymentStatusResult(
                status=PaymentStatus.EN_RETARD if is_late else PaymentStatus.NON_PAYE,
                total_due=total_due, total_paid=total_paid, balance=balance,
                overdue_amount=total_due if is_late else Money.zero(currency),
                next_installment_label=first.label,
                next_due_date=first.due_date,
                oldest_overdue_date=oldest_date,
                days_late=days_late,
            )

        # 4. Calcul du montant en retard + date de la 1ʳᵉ échéance impayée
        overdue, oldest_overdue_date = self._compute_overdue(schedule, total_paid, today)
        days_late = (today - oldest_overdue_date).days if oldest_overdue_date else 0

        # 5. Prochaine échéance future
        next_inst = next((i for i in schedule.installments if i.due_date > today), None)

        return PaymentStatusResult(
            status=PaymentStatus.EN_RETARD if overdue.amount > 0 else PaymentStatus.EN_COURS,
            total_due=total_due, total_paid=total_paid, balance=balance,
            overdue_amount=overdue,
            next_installment_label=next_inst.label if next_inst else None,
            next_due_date=next_inst.due_date if next_inst else None,
            oldest_overdue_date=oldest_overdue_date,
            days_late=days_late,
        )

    def _compute_overdue(
        self,
        schedule: PaymentSchedule,
        total_paid: Money,
        as_of: datetime.date,
    ) -> tuple:
        """Retourne (montant_en_retard, date_1ere_echeance_impayee).

        Algorithme : on couvre les échéances chronologiquement avec le crédit
        total_paid, et on note la date de la première échéance non couverte.
        """
        currency = total_paid.currency
        remaining_credit = total_paid.amount
        overdue_total = 0
        oldest_overdue_date: Optional[datetime.date] = None

        for inst in sorted(schedule.installments, key=lambda i: i.due_date):
            if inst.due_date > as_of:
                break
            covered = min(remaining_credit, inst.amount.amount)
            remaining_credit -= covered
            shortfall = inst.amount.amount - covered
            if shortfall > 0:
                overdue_total += shortfall
                if oldest_overdue_date is None:
                    oldest_overdue_date = inst.due_date

        return Money(overdue_total, currency), oldest_overdue_date
