"""
application/use_cases/poll_online_payment.py
==============================================
USE CASE : PollOnlinePaymentUseCase — Acteur : endpoint de statut (/payer/statut/<id>/).

Interroge la passerelle de paiement pour connaître le statut actuel d'un
paiement PENDING, puis applique la transition (PENDING → VALID ou CANCELLED)
si la passerelle confirme ou refuse.

Idempotent : si le paiement n'est plus PENDING (déjà VALID ou CANCELLED),
aucune action n'est effectuée. Un paiement PENDING dont la passerelle
répond encore PENDING reste inchangé.

Ce use case est appelé par la vue `status` à chaque poll JS de l'écran
d'attente, offrant un retour temps-réel au parent sans nécessiter de
webhook entrant.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from economat.application.ports.payment_gateway import GatewayPaymentStatus, PaymentGateway
from economat.application.ports.repositories import PaymentRepository
from economat.domain.payment.value_objects import PaymentId

logger = logging.getLogger(__name__)


@dataclass
class PollOnlinePaymentResult:
    success: bool
    new_state: str = ""      # "PENDING", "VALID", "CANCELLED"
    error_message: str = ""


class PollOnlinePaymentUseCase:
    def __init__(self, payment_repo: PaymentRepository, gateway: PaymentGateway) -> None:
        self._payments = payment_repo
        self._gateway = gateway

    def execute(self, payment_id: str) -> PollOnlinePaymentResult:
        try:
            return self._execute(payment_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erreur inattendue dans PollOnlinePaymentUseCase")
            return PollOnlinePaymentResult(
                success=False,
                error_message=f"Erreur inattendue : {type(exc).__name__} — {exc}",
            )

    def _execute(self, payment_id: str) -> PollOnlinePaymentResult:
        from economat.infrastructure.models import PaymentModel as _PM
        orm = _PM.objects.filter(pk=payment_id, channel="PORTAIL_PARENT").first()
        if orm is None:
            return PollOnlinePaymentResult(
                success=False, error_message="Paiement introuvable."
            )

        # Idempotence : déjà résolu, rien à faire
        if orm.state != "PENDING":
            return PollOnlinePaymentResult(success=True, new_state=orm.state)

        # Pas de référence externe → impossible de poller
        if not orm.gateway_transaction_ref:
            return PollOnlinePaymentResult(success=True, new_state="PENDING")

        event = self._gateway.poll_status(orm.gateway_transaction_ref)

        if event.status == GatewayPaymentStatus.PENDING:
            return PollOnlinePaymentResult(success=True, new_state="PENDING")

        # Transition : charger l'agrégat domaine, appliquer la règle
        payment = self._payments.find_by_id(PaymentId(str(orm.id)))
        if payment is None:
            return PollOnlinePaymentResult(
                success=False, error_message="Paiement introuvable en repository."
            )

        if event.status == GatewayPaymentStatus.ACCEPTED:
            payment.confirm()
            new_state = "VALID"
        else:
            payment.cancel(reason="Paiement Mobile Money refusé ou annulé par l'opérateur.")
            new_state = "CANCELLED"

        self._payments.save(payment)
        logger.info("PollOnlinePayment: %s → %s", payment_id, new_state)
        return PollOnlinePaymentResult(success=True, new_state=new_state)
