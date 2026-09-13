"""
infrastructure/payment/fake_gateway.py
=========================================
Implémentation factice de PaymentGateway — pour le développement et les
tests, sans dépendre d'un compte marchand CinetPay actif.

Toute transaction initiée réussit immédiatement (transaction_ref généré).
La confirmation (webhook) doit être simulée explicitement via
`simulate_confirmation()` — rien ne se confirme tout seul, pour permettre
de tester aussi bien le chemin "accepté" que "refusé" dans les tests
d'intégration du parcours parent.

Activé via la variable d'environnement PAYMENT_GATEWAY=fake (voir
config/settings.py et economat.composition.get_payment_gateway()).
"""
from __future__ import annotations

import json
import uuid

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)


class FakePaymentGateway(PaymentGateway):
    """Passerelle factice — aucun appel réseau, aucune dépendance externe."""

    # Secret partagé arbitraire, pour exercer verify_webhook_signature()
    # avec une vraie vérification (et pas un simple "return True").
    SHARED_SECRET = "fake-shared-secret-dev-only"

    def initiate_payment(
        self, phone: str, operator: str, amount_fcfa: int,
        description: str, notify_url: str,
    ) -> GatewayInitiationResult:
        transaction_ref = f"FAKE-{uuid.uuid4().hex[:12]}"
        return GatewayInitiationResult(success=True, transaction_ref=transaction_ref)

    def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool:
        return headers.get("X-Fake-Signature") == self.SHARED_SECRET

    def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent:
        data = json.loads(raw_body)
        return GatewayWebhookEvent(
            transaction_ref=data["transaction_ref"],
            status=GatewayPaymentStatus(data["status"]),
        )

    def simulate_confirmation(
        self, transaction_ref: str, accepted: bool,
    ) -> tuple[bytes, dict]:
        """
        Construit (body, headers) tel que CinetPay les enverrait pour
        confirmer ou refuser une transaction. Réservé aux tests/démo — ne
        fait pas partie du port PaymentGateway (CinetPayGateway n'a pas
        cette méthode, elle n'a pas de sens en production).
        """
        status = GatewayPaymentStatus.ACCEPTED if accepted else GatewayPaymentStatus.REFUSED
        body = json.dumps({"transaction_ref": transaction_ref, "status": status.value}).encode()
        headers = {"X-Fake-Signature": self.SHARED_SECRET}
        return body, headers
