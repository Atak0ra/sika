"""
infrastructure/payment/cinetpay_gateway.py
=============================================
Implémentation de PaymentGateway contre l'API CinetPay v2.

Sécurité du webhook : plutôt que de faire confiance au contenu brut du
POST reçu sur notify_url (qui pourrait être falsifié par un tiers qui
devine l'URL), on ne retient du webhook QUE la référence de transaction
(cpm_trans_id), et on revérifie le statut réel via un appel
serveur-à-serveur authentifié (apikey/site_id) à /v2/payment/check. C'est
cet appel authentifié, et non le contenu du POST entrant, qui fait foi.

⚠️ À valider contre un compte sandbox CinetPay réel avant mise en
production — les noms de champs exacts de la réponse JSON peuvent avoir
évolué depuis la rédaction de ce fichier. Voir le commentaire de la classe
Task 19 dans docs/superpowers/plans/2026-09-13-parent-payment-portal.md.
"""
from __future__ import annotations

import uuid

import requests

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)

_BASE_URL = "https://api-checkout.cinetpay.com/v2"

# Statuts renvoyés par CinetPay → notre enum interne.
_STATUS_MAP = {
    "ACCEPTED": GatewayPaymentStatus.ACCEPTED,
    "REFUSED":  GatewayPaymentStatus.REFUSED,
    "PENDING":  GatewayPaymentStatus.PENDING,
}


class CinetPayGateway(PaymentGateway):
    def __init__(self, api_key: str, site_id: str, secret_key: str) -> None:
        self._api_key = api_key
        self._site_id = site_id
        self._secret_key = secret_key

    def initiate_payment(
        self, phone: str, operator: str, amount_fcfa: int,
        description: str, notify_url: str,
    ) -> GatewayInitiationResult:
        transaction_ref = f"SUKULU-{uuid.uuid4().hex[:16]}"
        payload = {
            "apikey": self._api_key,
            "site_id": self._site_id,
            "transaction_id": transaction_ref,
            "amount": amount_fcfa,
            "currency": "XOF",
            "description": description,
            "notify_url": notify_url,
            "channels": "MOBILE_MONEY",
            "customer_phone_number": phone,
        }
        try:
            resp = requests.post(f"{_BASE_URL}/payment", json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            return GatewayInitiationResult(success=False, error_message=str(e))

        if data.get("code") not in ("201", "00"):
            return GatewayInitiationResult(
                success=False, error_message=data.get("message", "Erreur CinetPay inconnue."),
            )

        return GatewayInitiationResult(success=True, transaction_ref=transaction_ref)

    def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool:
        """
        CinetPay identifie l'appelant par cpm_site_id dans le corps du
        webhook. On rejette tout webhook qui ne correspond pas à NOTRE
        site_id — la confirmation réelle du statut vient ensuite de
        l'appel authentifié /v2/payment/check dans parse_webhook_status(),
        jamais du contenu brut de ce POST.
        """
        import json
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, TypeError):
            return False
        return str(data.get("cpm_site_id", "")) == str(self._site_id)

    def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent:
        import json
        data = json.loads(raw_body)
        transaction_ref = data["cpm_trans_id"]

        check_payload = {
            "apikey": self._api_key, "site_id": self._site_id,
            "transaction_id": transaction_ref,
        }
        resp = requests.post(f"{_BASE_URL}/payment/check", json=check_payload, timeout=15)
        resp.raise_for_status()
        check_data = resp.json()
        status_str = check_data.get("data", {}).get("status", "PENDING")

        return GatewayWebhookEvent(
            transaction_ref=transaction_ref,
            status=_STATUS_MAP.get(status_str, GatewayPaymentStatus.PENDING),
        )
