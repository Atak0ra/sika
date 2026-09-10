"""
application/use_cases/record_payment.py — REFONTE (passe par Enrollment).
"""
from __future__ import annotations

from economat.application.dto import RecordPaymentCommand, RecordPaymentResult
from economat.application.ports.repositories import (
    EnrollmentRepository, PaymentRepository, SchoolYearRepository, StudentRepository,
)
from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.payment_status import PaymentStatusCalculator
from economat.domain.payment.value_objects import PaymentMethod
from economat.domain.school.value_objects import SchoolYearId
from economat.domain.shared.errors import DomainError, EntityNotFoundError, ZeroAmountError
from economat.domain.shared.value_objects import Money
from economat.domain.student.value_objects import StudentId


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
            return RecordPaymentResult(success=False, error_message=f"Erreur inattendue : {type(e).__name__} — {e}")

    def _execute(self, cmd: RecordPaymentCommand) -> RecordPaymentResult:
        if cmd.amount_fcfa <= 0:
            raise ZeroAmountError("Le montant doit être supérieur à 0 FCFA.")

        # 1. Charger l'élève
        student_id = StudentId(value=cmd.student_id)
        student    = self._students.find_by_id(student_id)
        if student is None:
            raise EntityNotFoundError(f"Élève introuvable (id={cmd.student_id}).")

        # 2. Charger l'année scolaire
        year_id = SchoolYearId(cmd.year_id)
        year    = self._years.find_by_id(year_id)
        if year is None:
            raise EntityNotFoundError("Année scolaire introuvable.")
        if year.is_closed:
            raise DomainError("Impossible d'enregistrer un paiement sur une année clôturée.")

        # 3. Charger l'Enrollment de cet élève pour cette année
        enrollment = self._enrollments.find_by_student_and_year(student_id, year_id)
        if enrollment is None:
            raise EntityNotFoundError(
                f"{student.name.full_name} n'est pas inscrit(e) pour l'année {year.label}."
            )
        if not enrollment.is_active():
            raise DomainError(f"L'inscription de {student.name.full_name} est inactive.")

        # 4. Charger le niveau pour le barème
        level = year.get_level(enrollment.level_id)
        schedule = level.get_payment_schedule(year.start_date)

        # 5. Paiements existants pour cet enrollment
        existing = self._payments.find_by_enrollment(enrollment.id)

        # 6. Construire l'entité Payment
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
            state=PaymentState.VALID,
            notes=cmd.notes,
        )

        # 7. Calcul du nouveau statut
        status_result = self._calculator.calculate(
            schedule=schedule, payments=existing + [payment],
            as_of=cmd.payment_date,
        )

        # 8. Persistance
        self._payments.save(payment)

        # Infos classe/niveau pour le reçu
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
