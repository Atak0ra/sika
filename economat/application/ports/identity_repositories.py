"""
application/ports/identity_repositories.py
============================================
Ports sortants — interfaces des dépôts Identity.

UserRepository  : accès aux comptes Django User (création, recherche).
MembershipRepository : gestion des memberships (liens User ↔ École ↔ Rôle).
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional

from economat.domain.identity.entities import Membership
from economat.domain.identity.value_objects import MembershipId, Role
from economat.domain.school.value_objects import SchoolId


class UserRepository(ABC):
    """Port sortant : gestion des comptes utilisateurs."""

    @abstractmethod
    def create_user(
        self,
        username: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
        email: str = "",
    ) -> str:
        """Crée un compte Django User. Retourne l'user_id (str)."""

    @abstractmethod
    def find_by_username(self, username: str) -> Optional[dict]:
        """Retourne un dict {id, username, first_name, last_name, email} ou None."""

    @abstractmethod
    def username_exists(self, username: str) -> bool:
        """Vérifie qu'un username est déjà pris."""

    @abstractmethod
    def set_password(self, user_id: str, new_password: str) -> None:
        """Change le mot de passe d'un utilisateur."""


class MembershipRepository(ABC):
    """Port sortant : gestion des memberships École ↔ Utilisateur."""

    @abstractmethod
    def find_by_id(self, membership_id: MembershipId) -> Optional[Membership]:
        pass

    @abstractmethod
    def find_by_user_and_school(
        self, user_id: str, school_id: SchoolId
    ) -> Optional[Membership]:
        """Retourne le Membership actif d'un user dans une école donnée, ou None."""

    @abstractmethod
    def find_by_user(self, user_id: str) -> List[Membership]:
        """Retourne tous les Memberships actifs d'un utilisateur (ses écoles)."""

    @abstractmethod
    def find_by_school(self, school_id: SchoolId) -> List[Membership]:
        """Retourne tous les membres d'une école."""

    @abstractmethod
    def save(self, membership: Membership) -> None:
        """Crée ou met à jour un Membership."""

    @abstractmethod
    def next_id(self) -> MembershipId:
        """Génère un nouvel identifiant unique."""

    @abstractmethod
    def count_directors(self, school_id: SchoolId) -> int:
        """Nombre de directeurs actifs dans l'école (invariant : doit rester >= 1)."""
