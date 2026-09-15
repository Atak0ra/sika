"""
application/dto_identity.py
==============================
DTOs pour le module Identity (onboarding, équipe, inscription des écoles).

Séparé de dto.py pour garder chaque fichier lisible et ciblé.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


# ── Commands ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignUpDirectorCommand:
    """Inscription d'un nouveau directeur (crée son compte sans école)."""
    username:   str
    password:   str
    first_name: str
    last_name:  str
    email:      str = ""


@dataclass(frozen=True)
class CreateSchoolCommand:
    """Le directeur crée son école après inscription. Génère son Membership(DIRECTOR)."""
    director_user_id: str
    school_name:      str
    city:             str
    country:          str = "SN"
    currency:         str = "XOF"
    director_display_name: str = ""   # rempli lors de l'activation automatique
    director_login:        str = ""   # idem


@dataclass(frozen=True)
class CreateCollaboratorCommand:
    """
    Le directeur crée directement le compte d'un collaborateur (secrétaire/économe).
    Pas d'email — le directeur saisit identifiant + mot de passe provisoire.
    """
    director_user_id: str
    school_id:        str
    username:         str
    password:         str
    first_name:       str
    last_name:        str
    role:             str   # "SECRETARY" | "ECONOME"


@dataclass(frozen=True)
class DeactivateCollaboratorCommand:
    """Le directeur désactive l'accès d'un collaborateur."""
    director_user_id: str
    school_id:        str
    membership_id:    str


@dataclass(frozen=True)
class RegisterSchoolCommand:
    """
    Soumission publique d'une demande d'inscription d'école.
    Aucun compte n'est créé à ce stade — statut PENDING.
    """
    school_name:        str
    city:               str
    country_code:       str
    manager_first_name: str
    manager_last_name:  str
    manager_email:      str
    manager_phone:      str = ""
    payment_methods:    tuple = ()
    mobile_operator:    str = ""
    mobile_number:      str = ""
    client_uuid:        str = ""


@dataclass(frozen=True)
class ActivateSchoolCommand:
    """Commande interne : activer un dossier PENDING et créer les entités."""
    registration_id: str
    dry_run:         bool = False


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class SignUpResult:
    success:       bool
    user_id:       Optional[str] = None
    username:      Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CreateSchoolResult:
    success:       bool
    school_id:     Optional[str] = None
    school_name:   Optional[str] = None
    membership_id: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CreateCollaboratorResult:
    success:       bool
    user_id:       Optional[str] = None
    username:      Optional[str] = None
    display_name:  Optional[str] = None
    role:          Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class RegisterSchoolResult:
    success:         bool
    registration_id: Optional[str] = None
    error_message:   Optional[str] = None
    already_exists:  bool = False


@dataclass
class ActivateSchoolResult:
    success:         bool
    registration_id: Optional[str] = None
    school_id:       Optional[str] = None
    school_name:     Optional[str] = None
    username:        Optional[str] = None
    temp_password:   Optional[str] = None
    manager_email:   Optional[str] = None
    email_sent:      bool = False
    dry_run:         bool = False
    error_message:   Optional[str] = None


@dataclass
class MembershipInfo:
    """DTO de lecture — informations affichables sur un membre de l'école."""
    membership_id: str
    user_id:       str
    display_name:  str
    login:         str
    role:          str
    role_label:    str
    role_badge:    str
    is_active:     bool
    joined_at:     str


@dataclass
class MySchoolsResult:
    """Les écoles accessibles à l'utilisateur connecté."""
    success:       bool
    memberships:   List[dict] = field(default_factory=list)
    error_message: Optional[str] = None

