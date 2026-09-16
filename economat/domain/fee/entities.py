"""
domain/fee/entities.py
========================
Entité FeeItem — poste de frais de scolarité.

Un FeeItem représente une ligne de frais créée pour une année scolaire :
  - les lignes SYSTEME (is_system=True, category=SCOLARITE) sont générées
    automatiquement à partir du tarif de chaque niveau et ne peuvent jamais
    être créées ni supprimées manuellement.
  - les lignes MANUELLES sont créées par le directeur / la secrétaire /
    l'économe (nom libre, catégorie choisie parmi manual_choices()).

Règles métier :
  - Un FeeItem système NE peut pas être créé via le use case CreateFeeItemUseCase.
  - Un FeeItem manuel NE peut pas avoir la catégorie SCOLARITE.
  - Le montant est toujours > 0 pour les lignes manuelles.
  - Un FeeItem inactif (is_active=False) n'apparaît plus dans les listes
    « à payer » mais ses paiements passés restent valides.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from ..school.payment_schedule import PaymentMode, PaymentSchedule
from ..school.value_objects import LevelId, SchoolYearId
from ..shared.errors import DomainError, ZeroAmountError
from ..shared.value_objects import Money
from .value_objects import FeeCategory, FeeItemId, FeeScope


@dataclass
class FeeItem:
    """Ligne de frais de scolarité pour UNE année scolaire.

    Attributes:
        id              : identifiant unique (UUID).
        school_year_id  : année scolaire de rattachement.
        name            : libellé libre (ex. « Cantine trimestre 1 », « Zoo »).
        category        : catégorie de regroupement (pour le reporting).
        amount          : montant total de la ligne (Money).
                          Pour les lignes système SCOLARITE, ce montant est
                          synchronisé avec Level.annual_fee par l'infrastructure
                          — ne pas le modifier directement.
        scope           : portée (niveau entier ou classe précise).
        payment_mode    : UNIQUE, MENSUEL ou TRANCHES.
        nb_months       : nombre de mensualités (pertinent si MENSUEL).
        is_mandatory    : True → le parent NE peut pas refuser ce poste.
        is_active       : False → ligne archivée, n'apparaît plus « à payer ».
        is_system       : True → ligne scolarité auto-générée, non modifiable.
        created_at      : horodatage de création.
    """
    id: FeeItemId
    school_year_id: SchoolYearId
    name: str
    category: FeeCategory
    amount: Money
    scope: FeeScope
    payment_mode: PaymentMode = PaymentMode.UNIQUE
    nb_months: int = 10
    is_mandatory: bool = True
    is_active: bool = True
    is_system: bool = False
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Le nom de la ligne de frais ne peut pas être vide.")
        if self.amount.is_zero() and not self.is_system:
            raise ZeroAmountError("Le montant d'une ligne de frais doit être > 0.")
        if self.is_system and self.category != FeeCategory.SCOLARITE:
            raise DomainError(
                "Une ligne système doit obligatoirement avoir la catégorie SCOLARITE."
            )
        if not self.is_system and self.category == FeeCategory.SCOLARITE:
            raise DomainError(
                "La catégorie SCOLARITE est réservée aux lignes système "
                "(générées automatiquement depuis le tarif du niveau)."
            )
        if self.nb_months < 1:
            raise ValueError("Le nombre de mois doit être >= 1.")

    # ── Méthodes métier ───────────────────────────────────────────────────────

    def applies_to(self, level_id: str, class_id: str | None) -> bool:
        """Retourne True si cette ligne s'applique à l'enrollment décrit."""
        return self.scope.applies_to(level_id, class_id)

    def get_payment_schedule(self, year_start: datetime.date) -> PaymentSchedule:
        """Génère l'échéancier attendu pour cette ligne, identique au mécanisme Level."""
        if self.payment_mode == PaymentMode.UNIQUE:
            return PaymentSchedule.for_unique(self.amount, year_start)
        elif self.payment_mode == PaymentMode.TRANCHES:
            return PaymentSchedule.for_tranches(self.amount, year_start)
        return PaymentSchedule.for_mensuel(self.amount, year_start, nb_months=self.nb_months)

    def deactivate(self) -> None:
        """Archive la ligne : elle n'apparaît plus « à payer » pour les nouveaux paiements."""
        if self.is_system:
            raise DomainError(
                "Impossible de désactiver une ligne système (scolarité). "
                "Modifiez le tarif du niveau à la place."
            )
        self.is_active = False

    def __str__(self) -> str:
        return f"{self.name} [{self.category.label}] — {self.amount}"
