"""
application/ports/registration_repository.py
==============================================
Port sortant — interface du dépôt SchoolRegistration.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional
import uuid


class SchoolRegistrationRepository(ABC):

    @abstractmethod
    def create(
        self,
        *,
        client_uuid: Optional[str],
        school_name: str,
        city: str,
        country_code: Optional[str],
        manager_first_name: str,
        manager_last_name: str,
        manager_email: str,
        manager_phone: str,
        payment_methods: list,
        mobile_operator: str,
        mobile_number: str,
    ) -> str:
        """Persiste une nouvelle demande PENDING. Retourne l'id (UUID str)."""

    @abstractmethod
    def get(self, registration_id: str) -> Optional[dict]:
        """
        Retourne un dict avec tous les champs ou None si introuvable.
        Clés : id, client_uuid, school_name, city, country_code, currency,
               mobile_operators (list), payment_provider,
               manager_first_name, manager_last_name, manager_email, manager_phone,
               payment_methods, mobile_operator, mobile_number,
               status, notes, created_at.
        """

    @abstractmethod
    def list_pending(self) -> List[dict]:
        """Retourne toutes les demandes en statut PENDING, triées par date."""

    @abstractmethod
    def mark_activated(
        self,
        registration_id: str,
        school_id: str,
        user_id: str,
    ) -> None:
        """Passe le statut à ACTIVATED et renseigne created_school / activated_user / activated_at."""

    @abstractmethod
    def find_by_client_uuid(self, client_uuid: str) -> Optional[dict]:
        """Recherche par clé d'idempotence. Retourne le dict ou None."""

    @abstractmethod
    def email_has_pending(self, email: str) -> bool:
        """True si un dossier PENDING existe déjà pour cet email de gérant."""
