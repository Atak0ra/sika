"""
application/ports/payment_gateway.py
=======================================
Port (interface) pour la passerelle de paiement Mobile Money du portail
parent. Une seule implémentation concrète tourne à la fois, choisie par
economat.composition.get_payment_gateway(country) selon le pays de l'école :

  - FakePaymentGateway   (economat/infrastructure/payment/fake_gateway.py)
    → développement/tests, confirme via poll_status() sans appel réseau.
  - SamirPayGateway      (economat/infrastructure/payment/samirpay_gateway.py)
    → Sénégal : API Samirpay (X-API-KEY / X-SECRET-KEY).
  - CRPayGateway         (economat/infrastructure/payment/crpay_gateway.py)
    → Guinée Conakry : API CRPay (JWT login email/password).

Cette abstraction isole tout le reste de l'application (use cases, vues)
du détail exact de l'API du fournisseur — un changement de fournisseur ne
touche qu'un seul fichier d'implémentation.

Flux de confirmation : Samirpay et CRPay confirment par polling de statut
(pas par webhook push). L'endpoint JSON /payer/statut/<id>/ appelle
poll_status() à chaque interrogation JS depuis l'écran d'attente, ce qui
déclenche la confirmation idempotente du paiement.
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
    """Événement de statut (issu du polling) de la passerelle."""
    transaction_ref: str
    status: GatewayPaymentStatus


class PaymentGateway(ABC):
    """Port : déclenche un paiement Mobile Money et interroge son statut."""

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
        Ne bloque pas jusqu'à la confirmation — celle-ci est obtenue de
        façon asynchrone via poll_status().

        Le paramètre notify_url est conservé pour compatibilité (certaines
        passerelles peuvent l'utiliser pour envoyer un callback), mais la
        confirmation officielle passe toujours par poll_status().
        """
        ...

    @abstractmethod
    def poll_status(self, transaction_ref: str) -> GatewayWebhookEvent:
        """
        Interroge la passerelle pour connaître le statut actuel d'une
        transaction. Appelé périodiquement depuis l'endpoint de statut
        (/payer/statut/<id>/) afin de confirmer ou annuler un paiement
        PENDING. Doit être idempotent (plusieurs appels pour la même
        transaction ne causent pas d'effet de bord côté passerelle).
        """
        ...
