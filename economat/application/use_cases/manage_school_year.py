"""
application/use_cases/manage_school_year.py
=============================================
Use Cases de gestion du cycle de vie des années scolaires.

  - CreateSchoolYearUseCase   : créer une année (DRAFT), avec duplication optionnelle
  - ActivateSchoolYearUseCase : passer une année en ACTIVE (une seule à la fois)
  - CloseSchoolYearUseCase    : clôturer l'année active
"""
from __future__ import annotations

import uuid

from economat.application.dto import (
    ActivateSchoolYearCommand,
    CloseSchoolYearCommand,
    CreateSchoolYearCommand,
    SchoolYearResult,
)
from economat.application.ports.repositories import (
    SchoolRepository,
    SchoolYearRepository,
)
from economat.domain.school.entities import Class, Level, SchoolYear, SchoolYearStatus
from economat.domain.school.value_objects import (
    ClassId,
    LevelId,
    SchoolId,
    SchoolYearId,
)
from economat.domain.shared.errors import DomainError, EntityNotFoundError


class CreateSchoolYearUseCase:
    """Crée une nouvelle année scolaire (DRAFT).
    Si duplicate_from_year_id est fourni, copie la structure (niveaux + classes + tarifs).
    """
    def __init__(self, school_repo: SchoolRepository, year_repo: SchoolYearRepository):
        self._schools = school_repo
        self._years   = year_repo

    def execute(self, cmd: CreateSchoolYearCommand) -> SchoolYearResult:
        try:
            return self._execute(cmd)
        except DomainError as e:
            return SchoolYearResult(success=False, error_message=str(e))
        except Exception as e:
            return SchoolYearResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: CreateSchoolYearCommand) -> SchoolYearResult:
        if not cmd.label.strip():
            raise DomainError("Le label de l'année scolaire est obligatoire.")
        if cmd.end_date <= cmd.start_date:
            raise DomainError("La date de fin doit être après la date de début.")

        school = self._schools.find_by_id(SchoolId(cmd.school_id))
        if school is None:
            raise EntityNotFoundError(f"École introuvable (id={cmd.school_id}).")

        # Règle : si aucune année n'est déjà active, on active automatiquement.
        # L'activation manuelle n'a de sens que pour la transition d'une année à l'autre.
        no_active_year = self._years.find_active(SchoolId(cmd.school_id)) is None
        initial_status = SchoolYearStatus.ACTIVE if no_active_year else SchoolYearStatus.DRAFT

        new_year = SchoolYear(
            id=SchoolYearId(value=str(uuid.uuid4())),
            school_id=SchoolId(cmd.school_id),
            label=cmd.label.strip(),
            start_date=cmd.start_date,
            end_date=cmd.end_date,
            status=initial_status,
        )

        # Duplication de structure depuis une année précédente
        if cmd.duplicate_from_year_id:
            source = self._years.find_by_id(SchoolYearId(cmd.duplicate_from_year_id))
            if source is None:
                raise EntityNotFoundError("Année source introuvable pour la duplication.")
            _duplicate_structure(source, new_year)

        self._years.save(new_year)
        return SchoolYearResult(
            success=True, year_id=str(new_year.id),
            label=new_year.label, status=new_year.status.value,
        )


class ActivateSchoolYearUseCase:
    """Active une année scolaire (DRAFT → ACTIVE). Une seule active à la fois."""
    def __init__(self, school_repo: SchoolRepository, year_repo: SchoolYearRepository):
        self._schools = school_repo
        self._years   = year_repo

    def execute(self, cmd: ActivateSchoolYearCommand) -> SchoolYearResult:
        try:
            school = self._schools.find_by_id(SchoolId(cmd.school_id))
            if school is None:
                raise EntityNotFoundError("École introuvable.")

            # Vérifier qu'aucune autre année n'est déjà active
            current_active = self._years.find_active(SchoolId(cmd.school_id))
            if current_active and str(current_active.id) != cmd.year_id:
                raise DomainError(
                    f"L'année '{current_active.label}' est déjà active. "
                    "Clôturez-la avant d'en activer une autre."
                )

            year = self._years.find_by_id(SchoolYearId(cmd.year_id))
            if year is None:
                raise EntityNotFoundError("Année introuvable.")

            year.activate()
            self._years.save(year)
            return SchoolYearResult(success=True, year_id=str(year.id),
                                    label=year.label, status=year.status.value)
        except DomainError as e:
            return SchoolYearResult(success=False, error_message=str(e))
        except Exception as e:
            return SchoolYearResult(success=False, error_message=f"Erreur inattendue : {e}")


class CloseSchoolYearUseCase:
    """Clôture l'année active (ACTIVE → CLOSED). Irréversible."""
    def __init__(self, year_repo: SchoolYearRepository):
        self._years = year_repo

    def execute(self, cmd: CloseSchoolYearCommand) -> SchoolYearResult:
        try:
            year = self._years.find_by_id(SchoolYearId(cmd.year_id))
            if year is None:
                raise EntityNotFoundError("Année introuvable.")
            year.close()
            self._years.save(year)
            return SchoolYearResult(success=True, year_id=str(year.id),
                                    label=year.label, status=year.status.value)
        except DomainError as e:
            return SchoolYearResult(success=False, error_message=str(e))
        except Exception as e:
            return SchoolYearResult(success=False, error_message=f"Erreur inattendue : {e}")


def _duplicate_structure(source: SchoolYear, target: SchoolYear) -> None:
    """Copie les niveaux et classes de `source` dans `target` (nouveaux IDs).
    Les tarifs sont copiés à l'identique pour servir de base ; le directeur les ajuste ensuite.
    """
    for src_level in source.levels:
        new_level = Level(
            id=LevelId(value=str(uuid.uuid4())),
            name=src_level.name,
            school_year_id=target.id,
            annual_fee=src_level.annual_fee,
            payment_mode=src_level.payment_mode,
        )
        for src_class in src_level.classes:
            new_class = Class(
                id=ClassId(value=str(uuid.uuid4())),
                name=src_class.name,
                level_id=new_level.id,
                capacity=src_class.capacity,
            )
            new_level.add_class(new_class)
        target.add_level(new_level)
