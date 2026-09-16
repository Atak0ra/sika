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
    ALL     = "ALL"     # S'applique à tous les élèves de l'école (toutes classes)
    CLASSES = "CLASSES" # S'applique à une sélection de classes précises


@dataclass(frozen=True)
class FeeScope:
    """Portée d'une ligne de frais.

    scope_type : ALL     → class_ids est vide, s'applique à tous les élèves.
                 CLASSES → class_ids contient les ClassId.value concernés.

    La scolarité système utilise un FeeScope interne mais n'est pas modifiable
    via les formulaires manuels.
    """
    scope_type: FeeScopeType
    class_ids:  tuple = ()   # tuple[str] — vide si ALL

    def __post_init__(self) -> None:
        if self.scope_type == FeeScopeType.CLASSES and not self.class_ids:
            raise ValueError(
                "FeeScope CLASSES doit avoir au moins une classe."
            )

    def applies_to(self, class_id: Optional[str]) -> bool:
        """Retourne True si cette portée s'applique à l'enrollment (via sa classe)."""
        if self.scope_type == FeeScopeType.ALL:
            return True
        return class_id is not None and class_id in self.class_ids

    @classmethod
    def all_classes(cls) -> "FeeScope":
        """Portée globale — s'applique à tous les élèves."""
        return cls(scope_type=FeeScopeType.ALL)

    @classmethod
    def for_classes(cls, class_ids: list[str]) -> "FeeScope":
        """Portée sur une liste de classes précises."""
        if not class_ids:
            raise ValueError("for_classes requiert au moins une classe.")
        return cls(scope_type=FeeScopeType.CLASSES, class_ids=tuple(class_ids))

    # ── Helpers rétro-compat pour la scolarité système (mono-cible niveau) ──
    # Utilisés uniquement en interne pour les lignes is_system=True.

    @classmethod
    def for_level(cls, level_id: str) -> "FeeScope":
        """Portée système — marque la scolarité comme globale (ALL).
        Le lien réel niveau↔FeeItem est géré via la FK level sur FeeItemModel.
        """
        # Pour les lignes système on utilise ALL ; le niveau est stocké
        # directement sur FeeItemModel.level (FK) et n'est pas dans class_ids.
        return cls(scope_type=FeeScopeType.ALL)

    @classmethod
    def for_class(cls, class_id: str) -> "FeeScope":
        """Portée sur une seule classe (helper 1-élément)."""
        return cls.for_classes([class_id])

