"""
application/ports/payment_gateway.py
=======================================
Port (interface) pour la passerelle de paiement Mobile Money du portail
parent. Une seule implémentation concrète tourne à la fois, choisie par
economat.composition.get_payment_gateway() :

  - FakePaymentGateway   (economat/infrastructure/payment/fake_gateway.py)
    → développement/tests, confirme automatiquement après un court délai.
  - CinetPayGateway      (economat/infrastructure/payment/cinetpay_gateway.py)
    → production, appelle réellement l'API CinetPay.

Cette abstraction isole tout le reste de l'application (use cases, vues)
du détail exact de l'API du fournisseur — un changement de fournisseur ne
touche qu'un seul fichier d'implémentation.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class GatewayPaymentStatus(str, Enum):
    """Statut d'un paiement côté passerelle."""
    PENDING  = "PENDING"   # en attente de confirmation par le parent
    ACCEPTED = "ACCEPTED"  # confirmé, l'argent a été débité
    REFUSED  = "REFUSED"   # refusé, annulé, ou expiré côté opérateur


@dataclass(frozen=True)
class GatewayInitiationResult:
    """Résultat de l'initiation d'un paiement auprès de la passerelle."""
    success: bool
    transaction_ref: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class GatewayWebhookEvent:
    """Événement décodé depuis un callback webhook de la passerelle."""
    transaction_ref: str
    status: GatewayPaymentStatus


class PaymentGateway(ABC):
    """Port : déclenche un paiement Mobile Money et interprète sa confirmation."""

    @abstractmethod
    def initiate_payment(
        self,
        phone: str,
        operator: str,
        amount_fcfa: int,
        description: str,
        notify_url: str,
    ) -> GatewayInitiationResult:
        """
        Déclenche le paiement : la passerelle pousse une demande de
        confirmation sur le téléphone du parent (USSD/appli opérateur).
        Ne bloque pas jusqu'à la confirmation — celle-ci arrive de façon
        asynchrone via un appel à `notify_url` (voir parse_webhook_status).
        """
        ...

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, headers: dict) -> bool:
        """
        Vérifie l'authenticité d'un callback webhook avant tout traitement.
        Doit retourner False pour tout webhook non authentifié — ne JAMAIS
        faire confiance à un webhook non vérifié pour valider un paiement.
        """
        ...

    @abstractmethod
    def parse_webhook_status(self, raw_body: bytes) -> GatewayWebhookEvent:
        """
        Décode le corps d'un webhook déjà vérifié en un événement exploitable.
        Ne doit être appelé qu'après verify_webhook_signature() == True.
        """
        ...
