"""
domain/identity/entities.py
==============================
Entité Membership — lien entre un Utilisateur, une École et un Rôle.

C'est le cœur du système multi-tenant et des permissions.

Règles métier :
- Un Membership lie un user (user_id str), une école (school_id) et un rôle.
- Les permissions sont des MÉTHODES du domaine (pas des bits ORM).
  → Le use case n'appelle jamais `if user.groups.filter(...)`.
  → Il appelle `membership.can_configure_pricing()`.
- Un seul DIRECTOR par école (invariant vérifié à la création dans le use case).
- Un Membership peut être désactivé (is_active=False) sans être supprimé.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

from ..school.value_objects import SchoolId
from ..shared.errors import DomainError
from .value_objects import MembershipId, Role


class UnauthorizedError(DomainError):
    """Action non autorisée pour ce rôle dans cette école."""


class NotSchoolMemberError(DomainError):
    """L'utilisateur n'est pas membre de cette école."""


@dataclass
class Membership:
    """
    Lien User ↔ École ↔ Rôle.

    C'est l'entité centrale du multi-tenant et du contrôle d'accès.

    Attributes:
        id          : identifiant unique du membership.
        user_id     : ID de l'utilisateur Django (str, pas de FK directe dans le domaine).
        school_id   : école concernée.
        role        : rôle de l'utilisateur dans cette école.
        is_active   : False = compte suspendu (ne peut plus se connecter à l'école).
        created_by  : user_id du directeur qui a créé ce membership.
        joined_at   : date d'acceptation / création.
        display_name: nom d'affichage du collaborateur (prénom + nom).
        login       : identifiant de connexion (username Django).
    """
    id:           MembershipId
    user_id:      str
    school_id:    SchoolId
    role:         Role
    display_name: str
    login:        str
    is_active:    bool = True
    created_by:   Optional[str] = None
    joined_at:    datetime.date = field(default_factory=datetime.date.today)

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise ValueError("Le nom d'affichage ne peut pas être vide.")
        if not self.login.strip():
            raise ValueError("Le login ne peut pas être vide.")

    # ── Permissions métier ────────────────────────────────────────────────────
    # La source de vérité des droits est ICI dans le domaine,
    # pas dans les groupes/permissions Django.

    def can_record_payment(self) -> bool:
        """Tous les rôles actifs peuvent saisir un paiement."""
        return self.is_active

    def can_register_student(self) -> bool:
        """Directeur et Secrétaire peuvent inscrire un élève."""
        return self.is_active and self.role in (Role.DIRECTOR, Role.SECRETARY)

    def can_configure_pricing(self) -> bool:
        """Seul le Directeur peut modifier les tarifs."""
        return self.is_active and self.role == Role.DIRECTOR

    def can_manage_team(self) -> bool:
        """Seul le Directeur peut créer/désactiver des collaborateurs."""
        return self.is_active and self.role == Role.DIRECTOR

    def can_view_dashboard(self) -> bool:
        """Le dashboard stats est réservé au Directeur."""
        return self.is_active and self.role == Role.DIRECTOR

    def can_use_chat(self) -> bool:
        """Le chat IA est réservé au Directeur."""
        return self.is_active and self.role == Role.DIRECTOR

    def can_manage_structure(self) -> bool:
        """Directeur et Secrétaire peuvent créer/modifier niveaux et classes."""
        return self.is_active and self.role in (Role.DIRECTOR, Role.SECRETARY)

    def can_cancel_payment(self) -> bool:
        """Seul le Directeur peut annuler un paiement."""
        return self.is_active and self.role == Role.DIRECTOR

    # ── Guards (lèvent des exceptions DomainError) ────────────────────────────

    def guard_configure_pricing(self) -> None:
        if not self.can_configure_pricing():
            raise UnauthorizedError(
                f"Seul le directeur peut modifier les tarifs "
                f"(vous êtes : {self.role.label})."
            )

    def guard_manage_team(self) -> None:
        if not self.can_manage_team():
            raise UnauthorizedError(
                f"Seul le directeur peut gérer l'équipe "
                f"(vous êtes : {self.role.label})."
            )

    def guard_register_student(self) -> None:
        if not self.can_register_student():
            raise UnauthorizedError(
                f"Vous n'avez pas le droit d'inscrire un élève "
                f"(vous êtes : {self.role.label})."
            )

    def guard_manage_structure(self) -> None:
        """Lève UnauthorizedError si l'utilisateur ne peut pas créer niveaux/classes."""
        if not self.can_manage_structure():
            raise UnauthorizedError(
                f"Seuls le directeur et la secrétaire peuvent gérer la structure "
                f"(niveaux, classes). Vous êtes : {self.role.label}."
            )

    def guard_cancel_payment(self) -> None:
        """Lève UnauthorizedError si l'utilisateur ne peut pas annuler un paiement."""
        if not self.can_cancel_payment():
            raise UnauthorizedError(
                f"Seul le directeur peut annuler un paiement "
                f"(vous êtes : {self.role.label})."
            )

    def guard_record_payment(self) -> None:
        """Lève UnauthorizedError si l'utilisateur ne peut pas saisir un paiement."""
        if not self.can_record_payment():
            raise UnauthorizedError(
                "Votre compte est inactif, vous ne pouvez pas saisir de paiement."
            )

    # ── Comportements ─────────────────────────────────────────────────────────

    def deactivate(self) -> None:
        """Suspend l'accès de ce collaborateur à l'école."""
        if self.role == Role.DIRECTOR:
            raise DomainError(
                "Impossible de désactiver le directeur de l'école. "
                "Transférez d'abord la direction à un autre utilisateur."
            )
        self.is_active = False

    def reactivate(self) -> None:
        self.is_active = True

    def __str__(self) -> str:
        status = "actif" if self.is_active else "inactif"
        return f"{self.display_name} ({self.role.label}) — {status}"
