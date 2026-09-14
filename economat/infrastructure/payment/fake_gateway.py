"""
infrastructure/payment/fake_gateway.py
=========================================
Implémentation factice de PaymentGateway — pour le développement et les
tests, sans dépendre d'un compte marchand Samirpay ou CRPay actif.

Toute transaction initiée réussit immédiatement (transaction_ref généré).
Le statut retourné par poll_status() est contrôlé via simulate_status() —
rien ne se confirme tout seul, pour permettre de tester aussi bien le
chemin "accepté" que "refusé" dans les tests d'intégration du parcours
parent.

Utilisée automatiquement pour tout pays autre que "Sénégal" et
"Guinée Conakry" (voir economat.composition.get_payment_gateway()).
"""
from __future__ import annotations

import uuid

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)


class FakePaymentGateway(PaymentGateway):
    """Passerelle factice — aucun appel réseau, aucune dépendance externe."""

    def __init__(self) -> None:
        # Statuts simulés : transaction_ref → GatewayPaymentStatus.
        # Par défaut PENDING ; appeler simulate_status() pour changer.
        self._statuses: dict[str, GatewayPaymentStatus] = {}

    def initiate_payment(
        self, phone: str, operator: str, amount_fcfa: int,
        description: str, notify_url: str,
    ) -> GatewayInitiationResult:
        transaction_ref = f"FAKE-{uuid.uuid4().hex[:12]}"
        self._statuses[transaction_ref] = GatewayPaymentStatus.PENDING
        return GatewayInitiationResult(success=True, transaction_ref=transaction_ref)

    def poll_status(self, transaction_ref: str) -> GatewayWebhookEvent:
        """Retourne le statut simulé (PENDING par défaut)."""
        status = self._statuses.get(transaction_ref, GatewayPaymentStatus.PENDING)
        return GatewayWebhookEvent(transaction_ref=transaction_ref, status=status)

    def simulate_status(
        self, transaction_ref: str, accepted: bool,
    ) -> None:
        """
        Définit le statut que poll_status() retournera pour cette
        transaction. Réservé aux tests/démo — ne fait pas partie du port
        PaymentGateway (les vrais gateways n'ont pas cette méthode).
        """
        self._statuses[transaction_ref] = (
            GatewayPaymentStatus.ACCEPTED if accepted else GatewayPaymentStatus.REFUSED
        )
