"""
application/dto_identity.py
==============================
DTOs pour le module Identity (onboarding, équipe).

Séparé de dto.py pour garder chaque fichier lisible et ciblé.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional


# ── Commands ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignUpDirectorCommand:
    """Inscription d'un nouveau directeur (crée son compte sans école)."""
    username:   str       # identifiant de connexion
    password:   str       # mot de passe (en clair, sera hashé)
    first_name: str
    last_name:  str
    email:      str = ""


@dataclass(frozen=True)
class CreateSchoolCommand:
    """Le directeur crée son école après inscription. Génère son Membership(DIRECTOR)."""
    director_user_id: str   # user_id du directeur connecté
    school_name:      str
    city:             str
    country:          str = "SN"   # code ISO alpha-2 (ex. "SN", "GN")
    currency:         str = "XOF"


@dataclass(frozen=True)
class CreateCollaboratorCommand:
    """
    Le directeur crée directement le compte d'un collaborateur (secrétaire/économe).
    Pas d'email — le directeur saisit identifiant + mot de passe provisoire.
    """
    director_user_id: str   # user_id du directeur qui crée
    school_id:        str   # école dans laquelle ajouter le collaborateur
    username:         str   # identifiant de connexion du collaborateur
    password:         str   # mot de passe provisoire (en clair)
    first_name:       str
    last_name:        str
    role:             str   # "SECRETARY" | "ECONOME"


@dataclass(frozen=True)
class DeactivateCollaboratorCommand:
    """Le directeur désactive l'accès d'un collaborateur."""
    director_user_id: str
    school_id:        str
    membership_id:    str


# ── Results ───────────────────────────────────────────────────────────────────

@dataclass
class SignUpResult:
    success:      bool
    user_id:      Optional[str] = None
    username:     Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CreateSchoolResult:
    success:      bool
    school_id:    Optional[str] = None
    school_name:  Optional[str] = None
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
    success:     bool
    memberships: List[dict] = field(default_factory=list)
    error_message: Optional[str] = None
