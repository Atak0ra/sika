"""
application/use_cases/list_payable_items.py
=============================================
USE CASE : ListPayableItemsUseCase
Acteurs : Économe (dropdown guichet) / Parent (dashboard mobile)

Pour un élève inscrit dans l'année active, retourne la liste complète
des lignes de frais dues avec, pour chacune, le montant attendu, déjà
payé (paiements VALID) et le reste à payer.

Toujours en tête : la ligne scolarité (système, dérivée du niveau).
Puis les FeeItem manuels applicables (scope LEVEL ou CLASS).
"""
from __future__ import annotations
import datetime
from typing import List, Optional

from economat.application.dto import PayableLine, PayableItemsResult
from economat.application.ports.repositories import (
    EnrollmentRepository, FeeItemRepository, PaymentRepository,
    SchoolYearRepository, StudentRepository,
)
from economat.domain.fee.value_objects import FeeCategory
from economat.domain.payment.payment_status import PaymentStatusCalculator
from economat.domain.school.value_objects import SchoolYearId
from economat.domain.shared.errors import EntityNotFoundError
from economat.domain.student.value_objects import StudentId


class ListPayableItemsUseCase:
    def __init__(
        self,
        student_repo: StudentRepository,
        year_repo: SchoolYearRepository,
        enrollment_repo: EnrollmentRepository,
        payment_repo: PaymentRepository,
        fee_item_repo: FeeItemRepository,
    ) -> None:
        self._students    = student_repo
        self._years       = year_repo
        self._enrollments = enrollment_repo
        self._payments    = payment_repo
        self._fees        = fee_item_repo
        self._calc        = PaymentStatusCalculator()

    def execute(
        self,
        student_id: str,
        year_id: str,
        as_of: Optional[datetime.date] = None,
    ) -> PayableItemsResult:
        try:
            return self._execute(student_id, year_id, as_of or datetime.date.today())
        except EntityNotFoundError as e:
            return PayableItemsResult(success=False, error_message=str(e))
        except Exception as e:
            return PayableItemsResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(
        self, student_id: str, year_id: str, as_of: datetime.date
    ) -> PayableItemsResult:
        yid  = SchoolYearId(year_id)
        sid  = StudentId(value=student_id)
        year = self._years.find_by_id(yid)
        if year is None:
            raise EntityNotFoundError("Année scolaire introuvable.")
        enrollment = self._enrollments.find_by_student_and_year(sid, yid)
        if enrollment is None:
            raise EntityNotFoundError("Élève non inscrit pour cette année.")
        level = year.get_level(enrollment.level_id)
        lines: List[PayableLine] = []

        # ── 1. Ligne scolarité (système) ──────────────────────────────────────
        system_fee = self._fees.find_system_for_level(enrollment.level_id, yid)
        if system_fee is not None:
            schedule = level.get_payment_schedule(year.start_date)
            scol_payments = self._payments.find_by_fee_item(system_fee.id)
            scol_valid = [p for p in scol_payments
                          if p.is_valid() and str(p.enrollment_id) == str(enrollment.id)]
            total_paid_scol = sum(p.amount.amount for p in scol_valid)
            sr = self._calc.calculate(schedule, scol_valid, as_of=as_of)
            lines.append(PayableLine(
                fee_item_id=str(system_fee.id),
                name="Scolarité",
                category=FeeCategory.SCOLARITE.value,
                category_label=FeeCategory.SCOLARITE.label,
                amount_due=schedule.total_amount.amount,
                amount_paid=total_paid_scol,
                remaining=sr.balance.amount,
                payment_mode=level.payment_mode.value,
                is_system=True,
                is_mandatory=True,
                next_due_label=sr.next_installment_label,
                next_due_date=sr.next_due_date.isoformat() if sr.next_due_date else None,
                payment_status=sr.status.value,
            ))

        # ── 2. Lignes manuelles applicables ──────────────────────────────────
        fee_items = self._fees.find_applicable_to_enrollment(
            yid, enrollment.class_id,
        )
        for fee in fee_items:
            if fee.is_system:
                continue
            item_payments = self._payments.find_by_fee_item(fee.id)
            item_valid = [p for p in item_payments
                          if p.is_valid() and str(p.enrollment_id) == str(enrollment.id)]
            schedule = fee.get_payment_schedule(year.start_date, class_id=str(enrollment.class_id))
            sr = self._calc.calculate(schedule, item_valid, as_of=as_of)
            total_paid_item = sum(p.amount.amount for p in item_valid)
            lines.append(PayableLine(
                fee_item_id=str(fee.id),
                name=fee.name,
                category=fee.category.value,
                category_label=fee.category.label,
                amount_due=schedule.total_amount.amount,
                amount_paid=total_paid_item,
                remaining=sr.balance.amount,
                payment_mode=fee.payment_mode.value,
                is_system=False,
                is_mandatory=fee.is_mandatory,
                next_due_label=sr.next_installment_label,
                next_due_date=sr.next_due_date.isoformat() if sr.next_due_date else None,
                payment_status=sr.status.value,
            ))

        total_due       = sum(ln.amount_due  for ln in lines)
        total_paid      = sum(ln.amount_paid for ln in lines)
        total_remaining = sum(ln.remaining   for ln in lines)
        return PayableItemsResult(
            success=True, lines=lines,
            total_due=total_due, total_paid=total_paid, total_remaining=total_remaining,
        )

