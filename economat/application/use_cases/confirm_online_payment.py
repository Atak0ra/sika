"""
application/use_cases/confirm_online_payment.py
====================================================
USE CASE : ConfirmOnlinePaymentUseCase — Acteur : événement de passerelle.

Applique la confirmation (ou le refus) d'un paiement en ligne PENDING.
Peut être utilisé si une passerelle envoie un callback push.
Pour le flux principal (polling), voir poll_online_payment.py.

Idempotent : un même transaction_ref reçu plusieurs fois ne déclenche la
transition qu'une seule fois.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from economat.application.ports.payment_gateway import GatewayPaymentStatus, GatewayWebhookEvent
from economat.application.ports.repositories import PaymentRepository
from economat.domain.payment.value_objects import PaymentId

logger = logging.getLogger(__name__)


@dataclass
class ConfirmOnlinePaymentResult:
    success: bool
    error_message: str = ""


class ConfirmOnlinePaymentUseCase:
    def __init__(self, payment_repo: PaymentRepository) -> None:
        self._payments = payment_repo

    def execute(self, event: GatewayWebhookEvent) -> ConfirmOnlinePaymentResult:
        try:
            return self._execute(event)
        except Exception as e:  # noqa: BLE001
            logger.exception("Erreur inattendue dans ConfirmOnlinePaymentUseCase")
            return ConfirmOnlinePaymentResult(
                success=False, error_message=f"Erreur inattendue : {type(e).__name__} — {e}",
            )

    def _execute(self, event: GatewayWebhookEvent) -> ConfirmOnlinePaymentResult:
        from economat.infrastructure.models import PaymentModel as _PM
        orm = _PM.objects.filter(
            gateway_transaction_ref=event.transaction_ref, channel="PORTAIL_PARENT",
        ).first()
        if orm is None:
            return ConfirmOnlinePaymentResult(
                success=False, error_message=f"Transaction inconnue : {event.transaction_ref}",
            )

        # ── Idempotence : déjà traité, ne pas re-transitionner ────────────────
        if orm.state != "PENDING":
            return ConfirmOnlinePaymentResult(success=True)

        payment = self._payments.find_by_id(PaymentId(str(orm.id)))
        if payment is None:
            return ConfirmOnlinePaymentResult(success=False, error_message="Paiement introuvable.")

        if event.status == GatewayPaymentStatus.ACCEPTED:
            payment.confirm()
        else:
            payment.cancel(reason="Paiement Mobile Money refusé ou annulé par l'opérateur.")

        self._payments.save(payment)
        return ConfirmOnlinePaymentResult(success=True)
