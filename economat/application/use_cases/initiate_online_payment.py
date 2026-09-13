"""
application/use_cases/initiate_online_payment.py
====================================================
USE CASE : InitiateOnlinePaymentUseCase — Acteur : parent, sans compte.

Point d'entrée du paiement en ligne. Résout l'élève par (école, matricule)
en match exact, initie le paiement auprès de la passerelle Mobile Money, et
si la passerelle répond favorablement, délègue la création du paiement
PENDING/PORTAIL_PARENT à RecordPaymentUseCase (réutilisation — voir Task 5).

Sécurité : ne renvoie jamais un message différent selon que l'école existe,
le matricule existe, ou appartient à une autre école — toujours le même
message générique, pour ne pas transformer ce endpoint en oracle de
recherche.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from economat.application.dto import RecordPaymentCommand
from economat.application.ports.payment_gateway import PaymentGateway
from economat.application.use_cases.record_payment import RecordPaymentUseCase
from economat.composition import get_school_year_repo

logger = logging.getLogger(__name__)

GENERIC_NOT_FOUND = "École ou matricule introuvable."


@dataclass
class InitiateOnlinePaymentCommand:
    school_id: str
    matricule: str
    amount_fcfa: int
    mobile_operator: str
    mobile_number: str
    notify_url: str


@dataclass
class InitiateOnlinePaymentResult:
    success: bool
    payment_id: str | None = None
    error_message: str = ""


class InitiateOnlinePaymentUseCase:
    def __init__(self, record_payment_use_case: RecordPaymentUseCase, gateway: PaymentGateway) -> None:
        self._record_payment = record_payment_use_case
        self._gateway = gateway

    def execute(self, cmd: InitiateOnlinePaymentCommand) -> InitiateOnlinePaymentResult:
        try:
            return self._execute(cmd)
        except Exception as e:  # noqa: BLE001
            logger.exception("Erreur inattendue dans InitiateOnlinePaymentUseCase")
            return InitiateOnlinePaymentResult(
                success=False, error_message=f"Erreur inattendue : {type(e).__name__} — {e}",
            )

    def _execute(self, cmd: InitiateOnlinePaymentCommand) -> InitiateOnlinePaymentResult:
        if cmd.amount_fcfa <= 0:
            return InitiateOnlinePaymentResult(success=False, error_message="Montant invalide.")

        # ── 1. Résolution élève par matricule (match exact, hors-domaine —
        # matricule n'est pas un champ du domaine Student, cf. register_student.py) ──
        from economat.infrastructure.models import StudentModel
        student_orm = StudentModel.objects.filter(
            school_id=cmd.school_id, matricule=cmd.matricule,
        ).first()
        if student_orm is None:
            return InitiateOnlinePaymentResult(success=False, error_message=GENERIC_NOT_FOUND)

        # ── 2. Année scolaire active de l'école ───────────────────────────────
        from economat.domain.school.value_objects import SchoolId
        year_repo = get_school_year_repo()
        active_year = year_repo.find_active(SchoolId(cmd.school_id))
        if active_year is None:
            return InitiateOnlinePaymentResult(
                success=False,
                error_message="Aucune année scolaire active pour cette école.",
            )

        # ── 3. Initiation auprès de la passerelle ─────────────────────────────
        gateway_result = self._gateway.initiate_payment(
            phone=cmd.mobile_number,
            operator=cmd.mobile_operator,
            amount_fcfa=cmd.amount_fcfa,
            description=f"Frais de scolarité — {student_orm.first_name} {student_orm.last_name}",
            notify_url=cmd.notify_url,
        )
        if not gateway_result.success:
            return InitiateOnlinePaymentResult(
                success=False,
                error_message=gateway_result.error_message or "Le paiement n'a pas pu être initié.",
            )

        # ── 4. Création du paiement PENDING (réutilise RecordPaymentUseCase) ──
        import datetime
        record_cmd = RecordPaymentCommand(
            student_id=str(student_orm.id),
            year_id=str(active_year.id),
            amount_fcfa=cmd.amount_fcfa,
            payment_date=datetime.date.today(),
            method="MOBILE_MONEY",
            recorded_by="Portail parent",
            initial_state="PENDING",
            channel="PORTAIL_PARENT",
            gateway_transaction_ref=gateway_result.transaction_ref,
            mobile_operator=cmd.mobile_operator,
            mobile_number=cmd.mobile_number,
        )
        record_result = self._record_payment.execute(record_cmd)
        if not record_result.success:
            return InitiateOnlinePaymentResult(success=False, error_message=record_result.error_message)

        return InitiateOnlinePaymentResult(success=True, payment_id=record_result.payment_id)
