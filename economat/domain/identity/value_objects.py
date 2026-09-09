"""
domain/identity/value_objects.py
==================================
Value Objects du sous-domaine Identity.

- Role   : les 3 rôles possibles dans une école
- Email  : adresse email validée (VO immuable)
- MembershipId : identifiant typé d'un membership
"""

from __future__ import annotations
import re
import uuid
from dataclasses import dataclass
from enum import Enum


class Role(str, Enum):
    """Rôle d'un utilisateur dans une école précise."""
    DIRECTOR   = "DIRECTOR"    # Directeur : tous les droits sur son école
    SECRETARY  = "SECRETARY"   # Secrétaire : inscriptions + lecture
    ECONOME    = "ECONOME"     # Économe : saisie des paiements uniquement

    @property
    def label(self) -> str:
        return {
            Role.DIRECTOR:  "Directeur",
            Role.SECRETARY: "Secrétaire",
            Role.ECONOME:   "Économe",
        }[self]

    @property
    def badge_color(self) -> str:
        """Couleur CSS Tailwind pour le badge d'affichage."""
        return {
            Role.DIRECTOR:  "bg-navy-50 text-navy-700 border border-navy-100",
            Role.SECRETARY: "bg-[#f0f7f3] text-[#166534] border border-[#bfe0cc]",
            Role.ECONOME:   "bg-gray-100 text-gray-700 border border-gray-200",
        }[self]


@dataclass(frozen=True)
class Email:
    """Adresse e-mail validée — Value Object immuable."""
    value: str

    _PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    def __post_init__(self) -> None:
        v = self.value.strip().lower()
        if not v:
            raise ValueError("L'adresse e-mail ne peut pas être vide.")
        if not self._PATTERN.match(v):
            raise ValueError(f"Adresse e-mail invalide : {v!r}")
        # normalise en minuscules
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MembershipId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("MembershipId ne peut pas être vide.")

    @classmethod
    def generate(cls) -> MembershipId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value
