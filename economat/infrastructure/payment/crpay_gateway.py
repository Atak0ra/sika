"""
infrastructure/payment/crpay_gateway.py
=========================================
Implémentation de PaymentGateway pour l'API CRPay — utilisée quand
l'école est en Guinée Conakry (SchoolModel.country == "Guinée Conakry").

Auth : login JWT via POST /api/v0/auth/login/ (email + password). Le
token access (valide 2 h) est caché en mémoire de l'instance ; le token
refresh (7 j) permet de le renouveler sans redonner le mot de passe.
Les credentials sont lus depuis os.environ.

Flux :
  1. initiate_payment → POST /api/v0/transactions/
     Payload : {amount, purpose, customer_phone, customer_email}
     La réponse contient uuid (utilisé comme transaction_ref).
  2. poll_status      → GET /api/v0/transactions/{uuid}/
     Mappe status "SUCCESS"→ACCEPTED, "FAILED/CANCELLED"→REFUSED,
     autres→PENDING.

Variables d'environnement requises :
  CRPAY_BASE_URL  — ex. http://139.84.238.185:8000
  CRPAY_EMAIL     — email du compte marchand CRPay
  CRPAY_PASSWORD  — mot de passe du compte marchand CRPay
"""
from __future__ import annotations

import logging
import os
import time

import requests

from economat.application.ports.payment_gateway import (
    GatewayInitiationResult,
    GatewayPaymentStatus,
    GatewayWebhookEvent,
    PaymentGateway,
)

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, GatewayPaymentStatus] = {
    "success":   GatewayPaymentStatus.ACCEPTED,
    "failed":    GatewayPaymentStatus.REFUSED,
    "failure":   GatewayPaymentStatus.REFUSED,
    "cancelled": GatewayPaymentStatus.REFUSED,
    "refused":   GatewayPaymentStatus.REFUSED,
    "expired":   GatewayPaymentStatus.REFUSED,
    "pending":   GatewayPaymentStatus.PENDING,
}


class CRPayGateway(PaymentGateway):
    """Passerelle CRPay — Guinée Conakry (Orange Money GN, MTN Mobile Money)."""

    # Durée de vie du token access CRPay (2 h = 7200 s, on rafraîchit à 110 min)
    _TOKEN_TTL = 6600

    def __init__(self) -> None:
        self._base_url = os.environ.get("CRPAY_BASE_URL", "").rstrip("/")
        self._email = os.environ.get("CRPAY_EMAIL", "")
        self._password = os.environ.get("CRPAY_PASSWORD", "")

        missing = [
            var for var, val in (
                ("CRPAY_BASE_URL", self._base_url),
                ("CRPAY_EMAIL", self._email),
                ("CRPAY_PASSWORD", self._password),
            ) if not val
        ]
        if missing:
            raise EnvironmentError(
                f"Variables d'environnement CRPay manquantes : {missing}. "
                "Vérifiez votre .env."
            )

        self._access_token: str = ""
        self._refresh_token: str = ""
        self._token_expiry: float = 0.0  # timestamp UNIX

    def _get_token(self) -> str:
        """Retourne un access token valide (login ou refresh si expiré)."""
        now = time.monotonic()
        if self._access_token and now < self._token_expiry:
            return self._access_token

        # Tenter un refresh si on a un refresh_token
        if self._refresh_token:
            try:
                return self._do_refresh()
            except Exception:  # noqa: BLE001
                pass  # fallback sur un login complet

        return self._do_login()

    def _do_login(self) -> str:
        url = f"{self._base_url}/api/v0/auth/login/"
        resp = requests.post(
            url,
            json={"email": self._email, "password": self._password},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access"]
        self._refresh_token = data.get("refresh", "")
        self._token_expiry = time.monotonic() + self._TOKEN_TTL
        logger.info("CRPay login successful")
        return self._access_token

    def _do_refresh(self) -> str:
        url = f"{self._base_url}/api/v0/auth/refresh/"
        resp = requests.post(
            url,
            json={"refresh": self._refresh_token},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access"]
        self._token_expiry = time.monotonic() + self._TOKEN_TTL
        logger.info("CRPay token refreshed")
        return self._access_token

    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
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
        url = f"{self._base_url}/api/v0/transactions/"
        payload = {
            "amount": amount_fcfa,
            "purpose": description,
            "customer_phone": phone,
            "customer_email": "",
        }
        logger.info("CRPay initiate_payment — phone=%s amount=%s", phone, amount_fcfa)
        try:
            resp = requests.post(url, headers=self._auth_headers(), json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            logger.info("CRPay initiate_payment response: %s", data)
        except (requests.RequestException, ValueError) as exc:
            logger.error("CRPay initiate_payment error: %s", exc)
            return GatewayInitiationResult(success=False, error_message=str(exc))

        txn_uuid = data.get("uuid") or data.get("reference")
        if not txn_uuid:
            msg = data.get("message") or data.get("detail") or "Erreur CRPay inconnue."
            return GatewayInitiationResult(success=False, error_message=msg)

        return GatewayInitiationResult(success=True, transaction_ref=str(txn_uuid))

    def poll_status(self, transaction_ref: str) -> GatewayWebhookEvent:
        """Interroge GET /api/v0/transactions/{uuid}/."""
        url = f"{self._base_url}/api/v0/transactions/{transaction_ref}/"
        logger.info("CRPay poll_status — ref=%s", transaction_ref)
        try:
            resp = requests.get(url, headers=self._auth_headers(), timeout=30)
            resp.raise_for_status()
            data = resp.json()
            logger.info("CRPay poll_status response: %s", data)
        except (requests.RequestException, ValueError) as exc:
            logger.error("CRPay poll_status error: %s", exc)
            return GatewayWebhookEvent(
                transaction_ref=transaction_ref,
                status=GatewayPaymentStatus.PENDING,
            )

        raw_status = str(data.get("status", "pending")).lower()
        status = _STATUS_MAP.get(raw_status, GatewayPaymentStatus.PENDING)
        return GatewayWebhookEvent(transaction_ref=transaction_ref, status=status)

