"""
infrastructure/payment/samirpay_gateway.py
============================================
Implémentation de PaymentGateway pour l'API Samirpay — utilisée quand
l'école est au Sénégal (SchoolModel.country == "Sénégal").

Auth : deux headers statiques X-API-KEY et X-SECRET-KEY lus depuis
os.environ (SAMIR_API_KEY / SAMIR_SECRET_KEY). Aucun token JWT à gérer.

Flux :
  1. initiate_payment → POST {BASE}/api/tiers/initPayment
     Payload : {orderId, amount, telephone}
  2. poll_status      → GET {BASE}/api/tiers/payments/{ref}/status
     Mappe le statut Samirpay vers GatewayPaymentStatus.

Variables d'environnement requises :
  SAMIR_API_BASE_URL  — ex. https://api.samirpay.com/api/account/v1
  SAMIR_API_KEY       — clé API Samirpay
  SAMIR_SECRET_KEY    — clé secrète Samirpay
"""
from __future__ import annotations

import logging
import os
import uuid

import requests

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, GatewayPaymentStatus] = {
    "success":    GatewayPaymentStatus.ACCEPTED,
    "successful": GatewayPaymentStatus.ACCEPTED,
    "accepted":   GatewayPaymentStatus.ACCEPTED,
    "failed":     GatewayPaymentStatus.REFUSED,
    "failure":    GatewayPaymentStatus.REFUSED,
    "refused":    GatewayPaymentStatus.REFUSED,
    "cancelled":  GatewayPaymentStatus.REFUSED,
    "expired":    GatewayPaymentStatus.REFUSED,
    "pending":    GatewayPaymentStatus.PENDING,
    "initiated":  GatewayPaymentStatus.PENDING,
}



class SamirPayGateway(PaymentGateway):
    """Passerelle Samirpay — Sénégal (Orange Money, Wave, Free Money)."""

    def __init__(self) -> None:
        self._base_url = os.environ.get("SAMIR_API_BASE_URL", "").rstrip("/")
        self._api_key = os.environ.get("SAMIR_API_KEY", "")
        self._secret_key = os.environ.get("SAMIR_SECRET_KEY", "")

        missing = [
            var for var, val in (
                ("SAMIR_API_BASE_URL", self._base_url),
                ("SAMIR_API_KEY", self._api_key),
                ("SAMIR_SECRET_KEY", self._secret_key),
            ) if not val
        ]
        if missing:
            raise EnvironmentError(
                f"Variables d'environnement Samirpay manquantes : {missing}. "
                "Vérifiez votre .env."
            )

    def _headers(self) -> dict:
        return {
            "X-API-KEY": self._api_key,
            "X-SECRET-KEY": self._secret_key,
            "Content-Type": "application/json",
        }

    def initiate_payment(
        self,
        phone: str,
        operator: str,
        amount_fcfa: int,
        description: str,
        notify_url: str,
    ) -> GatewayInitiationResult:
        order_id = f"SUKULU-{uuid.uuid4().hex[:16]}"
        url = f"{self._base_url}/api/tiers/initPayment"
        payload = {
            "orderId": order_id,
            "amount": f"{amount_fcfa:.0f}",
            "telephone": phone,
        }
        logger.info("Samirpay initiate_payment — orderId=%s phone=%s amount=%s",
                    order_id, phone, amount_fcfa)
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Samirpay initiate_payment response: %s", data)
        except (requests.RequestException, ValueError) as exc:
            logger.error("Samirpay initiate_payment error: %s", exc)
            return GatewayInitiationResult(success=False, error_message=str(exc))

        success_flag = (
            data.get("success") is True
            or str(data.get("status", "")).lower() in ("success", "initiated", "pending")
        )
        if not success_flag:
            msg = data.get("message") or data.get("error") or "Erreur Samirpay inconnue."
            logger.warning("Samirpay initiate_payment failed: %s", msg)
            return GatewayInitiationResult(success=False, error_message=msg)

        return GatewayInitiationResult(success=True, transaction_ref=order_id)

    def poll_status(self, transaction_ref: str) -> GatewayWebhookEvent:
        """Interroge GET {BASE}/api/tiers/payments/{order_id}/status."""
        url = f"{self._base_url}/api/tiers/payments/{transaction_ref}/status"
        logger.info("Samirpay poll_status — ref=%s", transaction_ref)
        try:
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Samirpay poll_status response: %s", data)
        except (requests.RequestException, ValueError) as exc:
            logger.error("Samirpay poll_status error: %s", exc)
            return GatewayWebhookEvent(
                transaction_ref=transaction_ref,
                status=GatewayPaymentStatus.PENDING,
            )

        raw_status = (
            data.get("status")
            or data.get("transactionStatus")
            or data.get("data", {}).get("status", "pending")
        )
        status = _STATUS_MAP.get(str(raw_status).lower(), GatewayPaymentStatus.PENDING)
        return GatewayWebhookEvent(transaction_ref=transaction_ref, status=status)
