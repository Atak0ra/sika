"""
domain/school/entities.py
===========================
NOUVEAU MODÈLE : l'Année Scolaire est la racine temporelle.

Hiérarchie :
  School (identité stable : nom, ville, devise)
    └── SchoolYear ("2024-2025", ACTIVE | CLO^TURE'E)
          ├── Level (CM2 — tarif + mode de paiement pour CETTE année)
          │     └── Class (CM2 A)
          └── SchoolYear contient la réf. au seuil de tolérance

Règles métier :
- Une école peut avoir plusieurs années scolaires, UNE seule ACTIVE à la fois.
- Niveaux et classes appartiennent à une année précise (tarifaire isolé).
- La clôture d'une année est irréversible.
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ..shared.value_objects import Money, Currency
from ..shared.errors import (
    ClassLevelMismatchError, DuplicateEntityError, EntityNotFoundError, DomainError
)
from .value_objects import ClassId, LevelId, SchoolId, SchoolYearId
from .payment_schedule import PaymentMode, PaymentSchedule


class SchoolYearStatus(str, Enum):
    DRAFT    = "DRAFT"    # En préparation, pas encore ouverte
    ACTIVE   = "ACTIVE"   # Année en cours
    CLOSED   = "CLOSED"   # Clôturée, données en lecture seule


@dataclass
class Class:
    id: ClassId
    name: str
    level_id: LevelId
    capacity: int = 40

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Le nom de la classe ne peut pas être vide.")
        if self.capacity < 1:
            raise ValueError("La capacité doit être >= 1.")


@dataclass
class Level:
    """Niveau scolaire pour UNE année précise, avec son propre tarif."""
    id: LevelId
    name: str
    school_year_id: SchoolYearId
    annual_fee: Money
    payment_mode: PaymentMode
    nb_months: int = 10              # Pertinent si payment_mode == MENSUEL
    classes: List[Class] = field(default_factory=list)

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Le nom du niveau ne peut pas être vide.")
        if self.nb_months < 1:
            raise ValueError("Le nombre de mois doit être >= 1.")

    def get_payment_schedule(self, year_start: datetime.date) -> PaymentSchedule:
        if self.payment_mode == PaymentMode.UNIQUE:
            return PaymentSchedule.for_unique(self.annual_fee, year_start)
        elif self.payment_mode == PaymentMode.TRANCHES:
            return PaymentSchedule.for_tranches(self.annual_fee, year_start)
        return PaymentSchedule.for_mensuel(self.annual_fee, year_start, nb_months=self.nb_months)

    def add_class(self, klass: Class) -> None:
        if klass.level_id != self.id:
            raise ClassLevelMismatchError(
                f"La classe '{klass.name}' n'appartient pas au niveau '{self.name}'."
            )
        if any(c.id == klass.id for c in self.classes):
            raise DuplicateEntityError(f"La classe {klass.id} existe déjà.")
        self.classes.append(klass)

    def find_class(self, class_id: ClassId) -> Optional[Class]:
        return next((c for c in self.classes if c.id == class_id), None)


@dataclass
class SchoolYear:
    """Année scolaire — racine temporelle de toute la configuration.

    Contient les niveaux, classes et tarifs applicables pour cette année.
    Un seul SchoolYear peut être ACTIVE par école à un instant donné.
    """
    id: SchoolYearId
    school_id: SchoolId
    label: str          # ex. "2024-2025"
    start_date: datetime.date
    end_date: datetime.date
    status: SchoolYearStatus = SchoolYearStatus.DRAFT
    levels: List[Level] = field(default_factory=list)

    def __post_init__(self):
        if not self.label.strip():
            raise ValueError("Le label de l'année scolaire ne peut pas être vide.")
        if self.end_date <= self.start_date:
            raise ValueError("La date de fin doit être après la date de début.")

    @property
    def is_active(self) -> bool:
        return self.status == SchoolYearStatus.ACTIVE

    @property
    def is_closed(self) -> bool:
        return self.status == SchoolYearStatus.CLOSED

    def activate(self) -> None:
        if self.status == SchoolYearStatus.CLOSED:
            raise DomainError("Une année clôturée ne peut pas être réactivée.")
        self.status = SchoolYearStatus.ACTIVE

    def close(self) -> None:
        if self.status != SchoolYearStatus.ACTIVE:
            raise DomainError("Seule une année ACTIVE peut être clôturée.")
        self.status = SchoolYearStatus.CLOSED

    def add_level(self, level: Level) -> None:
        if self.is_closed:
            raise DomainError("Impossible de modifier une année clôturée.")
        if level.school_year_id != self.id:
            raise ValueError(f"Le niveau '{level.name}' n'appartient pas à cette année.")
        if any(l.id == level.id for l in self.levels):
            raise DuplicateEntityError(f"Le niveau {level.id} existe déjà.")
        self.levels.append(level)

    def get_level(self, level_id: LevelId) -> Level:
        lv = next((l for l in self.levels if l.id == level_id), None)
        if lv is None:
            raise EntityNotFoundError(f"Niveau {level_id} introuvable.")
        return lv

    def get_class(self, class_id: ClassId) -> Class:
        for level in self.levels:
            klass = level.find_class(class_id)
            if klass:
                return klass
        raise EntityNotFoundError(f"Classe {class_id} introuvable dans l'année {self.label}.")

    def configure_level_pricing(
        self, level_id: LevelId, annual_fee: Money, payment_mode: PaymentMode,
        nb_months: int = 10,
    ) -> None:
        if self.is_closed:
            raise DomainError("Impossible de modifier une année clôturée.")
        level = self.get_level(level_id)
        level.annual_fee = annual_fee
        level.payment_mode = payment_mode
        level.nb_months = nb_months

    def __str__(self) -> str:
        return f"{self.label} ({self.status.value})"


@dataclass
class School:
    """Identité stable de l'école. Contient les années scolaires.

    La configuration (niveaux, tarifs) vit dans SchoolYear, pas ici.
    """
    id: SchoolId
    name: str
    city: str
    country: str = "SN"   # code ISO alpha-2 (ex. "SN", "GN")
    currency: Currency = Currency.XOF
    tolerance_days: int = 30
    school_years: List[SchoolYear] = field(default_factory=list)

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Le nom de l'école ne peut pas être vide.")

    @property
    def active_year(self) -> Optional[SchoolYear]:
        """Retourne l'année scolaire active, ou None."""
        return next((y for y in self.school_years if y.is_active), None)

    def add_school_year(self, year: SchoolYear) -> None:
        if year.school_id != self.id:
            raise ValueError("Cette année n'appartient pas à cette école.")
        if any(y.id == year.id for y in self.school_years):
            raise DuplicateEntityError("Cette année scolaire existe déjà.")
        if any(y.label == year.label for y in self.school_years):
            raise DuplicateEntityError(f"Une année '{year.label}' existe déjà.")
        self.school_years.append(year)

    def activate_year(self, year_id: SchoolYearId) -> None:
        """Règle : une seule année ACTIVE à la fois."""
        for y in self.school_years:
            if y.is_active and y.id != year_id:
                raise DomainError(
                    f"L'année '{y.label}' est déjà active. Clôturez-la avant d'en activer une autre."
                )
        year = self.get_year(year_id)
        year.activate()

    def get_year(self, year_id: SchoolYearId) -> SchoolYear:
        y = next((y for y in self.school_years if y.id == year_id), None)
        if y is None:
            raise EntityNotFoundError(f"Année {year_id} introuvable.")
        return y

    def __str__(self) -> str:
        return f"{self.name} ({self.city})"
