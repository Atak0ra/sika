"""
application/use_cases/record_payment.py
=========================================
USE CASE : RecordPaymentUseCase — Acteur : Économe / Directeur

Supporte le mode offline :
  - client_uuid fourni + déjà en base → idempotent (pas de doublon)
  - receipt_number fourni (généré côté client) → utilisé tel quel
  - Sinon : fallback génération serveur classique
"""
from __future__ import annotations

import logging

from economat.application.dto import RecordPaymentCommand, RecordPaymentResult
from economat.application.ports.repositories import (
    EnrollmentRepository,
    PaymentRepository,
    SchoolYearRepository,
    StudentRepository,
)
from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.payment_status import PaymentStatusCalculator
from economat.domain.payment.value_objects import PaymentMethod
from economat.domain.school.value_objects import SchoolYearId
from economat.domain.shared.errors import (
    DomainError,
    EntityNotFoundError,
    ZeroAmountError,
)
from economat.domain.shared.value_objects import Money
from economat.domain.student.value_objects import StudentId

logger = logging.getLogger(__name__)


class RecordPaymentUseCase:
    def __init__(self, student_repo: StudentRepository,
                 year_repo: SchoolYearRepository, enrollment_repo: EnrollmentRepository,
                 payment_repo: PaymentRepository) -> None:
        self._students    = student_repo
        self._years       = year_repo
        self._enrollments = enrollment_repo
        self._payments    = payment_repo
        self._calculator  = PaymentStatusCalculator()

    def execute(self, cmd: RecordPaymentCommand) -> RecordPaymentResult:
        try:
            return self._execute(cmd)
        except ZeroAmountError as e:
            return RecordPaymentResult(success=False, error_message=str(e))
        except EntityNotFoundError as e:
            return RecordPaymentResult(success=False, error_message=str(e))
        except DomainError as e:
            return RecordPaymentResult(success=False, error_message=str(e))
        except Exception as e:
            logger.exception("Erreur inattendue dans RecordPaymentUseCase")
            return RecordPaymentResult(
                success=False,
                error_message=f"Erreur inattendue : {type(e).__name__} — {e}",
            )

    def _execute(self, cmd: RecordPaymentCommand) -> RecordPaymentResult:
        # ── Idempotence offline ───────────────────────────────────────────────
        # Si client_uuid déjà en base : paiement déjà enregistré, on retourne
        # le résultat original sans rien re-créer.
        if cmd.client_uuid:
            from economat.infrastructure.models import PaymentModel as _PM
            existing_pm = (
                _PM.objects
                .select_related("student")
                .filter(client_uuid=cmd.client_uuid)
                .first()
            )
            if existing_pm:
                return RecordPaymentResult(
                    success=True,
                    payment_id=str(existing_pm.id),
                    receipt_number=existing_pm.receipt_number,
                    student_name=(
                        f"{existing_pm.student.first_name} "
                        f"{existing_pm.student.last_name.upper()}"
                    ),
                    amount_paid=existing_pm.amount,
                    new_balance=None,
                    payment_status="already_synced",
                    class_name="", level_name="",
                )

        if cmd.amount_fcfa <= 0:
            raise ZeroAmountError("Le montant doit être supérieur à 0 FCFA.")

        student_id = StudentId(value=cmd.student_id)
        student    = self._students.find_by_id(student_id)
        if student is None:
            raise EntityNotFoundError(f"Élève introuvable (id={cmd.student_id}).")

        year_id = SchoolYearId(cmd.year_id)
        year    = self._years.find_by_id(year_id)
        if year is None:
            raise EntityNotFoundError("Année scolaire introuvable.")
        if year.is_closed:
            raise DomainError("Impossible d'enregistrer un paiement sur une année clôturée.")

        enrollment = self._enrollments.find_by_student_and_year(student_id, year_id)
        if enrollment is None:
            raise EntityNotFoundError(
                f"{student.name.full_name} n'est pas inscrit(e) pour l'année {year.label}."
            )
        if not enrollment.is_active():
            raise DomainError(f"L'inscription de {student.name.full_name} est inactive.")

        level    = year.get_level(enrollment.level_id)
        schedule = level.get_payment_schedule(year.start_date)
        existing = self._payments.find_by_enrollment(enrollment.id)

        # Numéro de reçu : client (déterministe offline) ou fallback serveur
        if cmd.receipt_number:
            receipt = cmd.receipt_number
        else:
            receipt_n = self._payments.last_receipt_number(student.school_id) + 1
            receipt   = f"REC-{student.school_id.value[:8].upper()}-{receipt_n:04d}"

        payment = Payment(
            id=self._payments.next_id(),
            enrollment_id=enrollment.id,
            student_id=student_id,
            amount=Money.of_xof(cmd.amount_fcfa),
            payment_date=cmd.payment_date,
            method=PaymentMethod(cmd.method),
            receipt_number=receipt,
            recorded_by=cmd.recorded_by,
            state=PaymentState(cmd.initial_state),
            notes=cmd.notes,
        )

        status_result = self._calculator.calculate(
            schedule=schedule, payments=existing + [payment],
            as_of=cmd.payment_date,
        )

        self._payments.save(payment)

        # Champs hors domaine (paid_by, client_uuid, installment_label)
        from economat.infrastructure.models import PaymentModel as _PM2
        extra: dict = {}
        if cmd.paid_by:            extra["paid_by"]           = cmd.paid_by.strip()
        if cmd.client_uuid:        extra["client_uuid"]       = cmd.client_uuid
        if cmd.installment_label:  extra["installment_label"] = cmd.installment_label
        if cmd.mobile_operator:    extra["mobile_operator"]   = cmd.mobile_operator.strip()
        if cmd.mobile_number:      extra["mobile_number"]     = cmd.mobile_number.strip()
        if cmd.channel:            extra["channel"]           = cmd.channel
        if cmd.gateway_transaction_ref:
            extra["gateway_transaction_ref"] = cmd.gateway_transaction_ref
        if cmd.fee_item_id:        extra["fee_item_id"]       = cmd.fee_item_id
        if extra:
            _PM2.objects.filter(pk=payment.id.value).update(**extra)

        klass = level.find_class(enrollment.class_id)
        return RecordPaymentResult(
            success=True, payment_id=str(payment.id),
            receipt_number=receipt, student_name=student.name.full_name,
            amount_paid=cmd.amount_fcfa,
            new_balance=status_result.balance.amount,
            payment_status=status_result.status.value,
            class_name=klass.name if klass else "",
            level_name=level.name,
        )
