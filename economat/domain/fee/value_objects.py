"""
domain/fee/value_objects.py
==============================
Value Objects du sous-domaine Frais de scolarité.

FeeItemId    — identifiant UUID d'une ligne de frais.
FeeCategory  — catégorie de regroupement fournie par la plateforme (non configurable
               par l'école). Sert exclusivement à l'agrégation/reporting.
               La catégorie SCOLARITE est réservée aux lignes système.
FeeScope     — portée d'une ligne de frais : s'applique à un niveau (LEVEL)
               ou à une classe précise (CLASS).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ── Identifiant ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeeItemId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("FeeItemId ne peut pas être vide.")

    @classmethod
    def generate(cls) -> FeeItemId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


# ── Catégorie ─────────────────────────────────────────────────────────────────

class FeeCategory(str, Enum):
    """Catégorie de regroupement des lignes de frais.

    SCOLARITE est réservée : seules les lignes système (is_system=True) peuvent
    avoir cette catégorie. Elle ne doit pas apparaître dans les formulaires de
    création manuelle.
    """
    SCOLARITE   = "SCOLARITE"    # Écolage — ligne système, auto-générée par niveau
    CANTINE     = "CANTINE"      # Cantine scolaire
    TRANSPORT   = "TRANSPORT"    # Transport scolaire (car, ramassage…)
    SORTIES     = "SORTIES"      # Sorties scolaires (zoo, musée…)
    SPORT       = "SPORT"        # Activités sportives / tenues de sport
    FOURNITURES = "FOURNITURES"  # Fournitures scolaires
    AUTRE       = "AUTRE"        # Tout autre frais non catégorisé

    @property
    def label(self) -> str:
        labels = {
            FeeCategory.SCOLARITE:   "Scolarité",
            FeeCategory.CANTINE:     "Cantine",
            FeeCategory.TRANSPORT:   "Transport scolaire",
            FeeCategory.SORTIES:     "Sorties scolaires",
            FeeCategory.SPORT:       "Activités sportives",
            FeeCategory.FOURNITURES: "Fournitures scolaires",
            FeeCategory.AUTRE:       "Autre",
        }
        return labels[self]

    @classmethod
    def manual_choices(cls) -> list[tuple[str, str]]:
        """Retourne les catégories disponibles pour la création manuelle (SCOLARITE exclue)."""
        return [
            (c.value, c.label)
            for c in cls
            if c != cls.SCOLARITE
        ]


# ── Portée ────────────────────────────────────────────────────────────────────

class FeeScopeType(str, Enum):
    """Type de portée d'une ligne de frais."""
    LEVEL = "LEVEL"   # S'applique à tous les élèves d'un niveau
    CLASS = "CLASS"   # S'applique uniquement aux élèves d'une classe précise


@dataclass(frozen=True)
class FeeScope:
    """Portée d'une ligne de frais.

    scope_type : LEVEL → target_id est un LevelId.value
                 CLASS → target_id est un ClassId.value
    """
    scope_type: FeeScopeType
    target_id: str           # LevelId.value ou ClassId.value selon scope_type

    def __post_init__(self) -> None:
        if not self.target_id or not self.target_id.strip():
            raise ValueError("FeeScope.target_id ne peut pas être vide.")

    def applies_to(self, level_id: str, class_id: Optional[str]) -> bool:
        """Retourne True si cette portée s'applique à l'enrollment décrit."""
        if self.scope_type == FeeScopeType.LEVEL:
            return self.target_id == level_id
        # CLASS : s'applique si la classe correspond
        return class_id is not None and self.target_id == class_id

    @classmethod
    def for_level(cls, level_id: str) -> FeeScope:
        return cls(scope_type=FeeScopeType.LEVEL, target_id=level_id)

    @classmethod
    def for_class(cls, class_id: str) -> FeeScope:
        return cls(scope_type=FeeScopeType.CLASS, target_id=class_id)
