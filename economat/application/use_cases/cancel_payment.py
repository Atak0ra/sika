"""
application/use_cases/cancel_payment.py
=========================================
USE CASE : CancelPaymentUseCase — Acteur : Directeur uniquement.

Annule un paiement existant (state VALID → CANCELLED) avec un motif.
Règles :
  - Seul le Directeur peut annuler (guard_cancel_payment).
  - Un paiement déjà annulé ne peut pas l'être à nouveau.
  - Le paiement doit appartenir à l'école du directeur (sécurité IDOR).
  - Aucune modification des autres champs (montant, date, etc.) n'est possible.
"""
from __future__ import annotations

import logging

from economat.application.dto import CancelPaymentCommand, CancelPaymentResult
from economat.application.ports.repositories import PaymentRepository
from economat.application.ports.identity_repositories import MembershipRepository
from economat.domain.identity.value_objects import MembershipId
from economat.domain.payment.entities import PaymentState
from economat.domain.payment.value_objects import PaymentId
from economat.domain.school.value_objects import SchoolId
from economat.domain.shared.errors import DomainError, EntityNotFoundError

logger = logging.getLogger(__name__)


class CancelPaymentUseCase:
    def __init__(self, payment_repo: PaymentRepository,
                 membership_repo: MembershipRepository) -> None:
        self._payments   = payment_repo
        self._memberships = membership_repo

    def execute(self, cmd: CancelPaymentCommand) -> CancelPaymentResult:
        try:
            return self._execute(cmd)
        except EntityNotFoundError as e:
            return CancelPaymentResult(success=False, error_message=str(e))
        except DomainError as e:
            return CancelPaymentResult(success=False, error_message=str(e))
        except Exception as e:
            logger.exception("Erreur inattendue dans CancelPaymentUseCase")
            return CancelPaymentResult(
                success=False,
                error_message=f"Erreur inattendue : {type(e).__name__} — {e}",
            )

    def _execute(self, cmd: CancelPaymentCommand) -> CancelPaymentResult:
        # ── 1. Vérification du rôle ───────────────────────────────────────────
        membership = self._memberships.find_by_user_and_school(
            user_id=cmd.director_user_id,
            school_id=SchoolId(cmd.school_id),
        )
        if membership is None or not membership.is_active:
            raise EntityNotFoundError("Vous n'êtes pas membre de cette école.")
        membership.guard_cancel_payment()   # lève UnauthorizedError si pas DIRECTOR

        # ── 2. Chargement du paiement ─────────────────────────────────────────
        payment = self._payments.find_by_id(PaymentId(cmd.payment_id))
        if payment is None:
            raise EntityNotFoundError(
                f"Paiement introuvable (id={cmd.payment_id})."
            )

        # ── 3. Sécurité IDOR : le paiement appartient bien à l'école ─────────
        # On vérifie en ORM car le domaine Payment ne connaît pas l'école.
        from economat.infrastructure.models import PaymentModel as _PM
        belongs = _PM.objects.filter(
            pk=cmd.payment_id,
            enrollment__school_year__school_id=cmd.school_id,
        ).exists()
        if not belongs:
            raise EntityNotFoundError(
                "Paiement introuvable pour cette école."
            )

        # ── 4. Idempotence : déjà annulé → erreur explicite ──────────────────
        if payment.state == PaymentState.CANCELLED:
            raise DomainError("Ce paiement est déjà annulé.")

        # ── 5. Annulation domaine + persistance ───────────────────────────────
        payment.cancel(reason=cmd.reason.strip())
        self._payments.save(payment)

        return CancelPaymentResult(
            success=True,
            payment_id=str(payment.id),
            receipt_number=payment.receipt_number,
        )
