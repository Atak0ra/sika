"""
application/use_cases/promote_class.py
========================================
USE CASE : PromoteClassUseCase
Réinscrit en masse les élèves d'une classe source vers une classe cible (nouvelle année).
Le directeur peut exclure des élèves individuellement.
"""
from __future__ import annotations
import datetime

from economat.application.dto import PromoteClassCommand, PromoteClassResult
from economat.application.ports.repositories import (
    EnrollmentRepository, SchoolYearRepository,
)
from economat.domain.enrollment.entities import Enrollment
from economat.domain.enrollment.value_objects import EnrollmentStatus
from economat.domain.school.value_objects import ClassId, SchoolYearId
from economat.domain.shared.errors import DomainError, EntityNotFoundError


class PromoteClassUseCase:
    def __init__(self, year_repo: SchoolYearRepository,
                 enrollment_repo: EnrollmentRepository) -> None:
        self._years       = year_repo
        self._enrollments = enrollment_repo

    def execute(self, cmd: PromoteClassCommand) -> PromoteClassResult:
        try:
            return self._execute(cmd)
        except DomainError as e:
            return PromoteClassResult(success=False, error_message=str(e))
        except Exception as e:
            return PromoteClassResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: PromoteClassCommand) -> PromoteClassResult:
        from_year = self._years.find_by_id(SchoolYearId(cmd.from_year_id))
        to_year   = self._years.find_by_id(SchoolYearId(cmd.to_year_id))

        if from_year is None or to_year is None:
            raise EntityNotFoundError("Année source ou cible introuvable.")
        if to_year.is_closed:
            raise DomainError("Impossible de réinscrire dans une année clôturée.")

        # Vérifier que la classe cible existe dans l'année cible
        target_class_id = ClassId(cmd.to_class_id)
        target_class    = to_year.get_class(target_class_id)  # lève EntityNotFoundError si absent
        target_level    = next((l for l in to_year.levels
                                if target_class.level_id == l.id), None)
        if target_level is None:
            raise EntityNotFoundError("Niveau cible introuvable dans l'année destination.")

        # Charger les inscriptions actives de la classe source
        source_enrollments = self._enrollments.find_by_class_and_year(
            ClassId(cmd.from_class_id), SchoolYearId(cmd.from_year_id)
        )

        excluded = set(cmd.excluded_student_ids)
        promoted = skipped = 0

        for src_enrollment in source_enrollments:
            if not src_enrollment.is_active():
                skipped += 1
                continue
            if str(src_enrollment.student_id) in excluded:
                skipped += 1
                continue

            # Vérifier qu'il n'y a pas déjà une inscription pour cet élève dans l'année cible
            existing = self._enrollments.find_by_student_and_year(
                src_enrollment.student_id, SchoolYearId(cmd.to_year_id)
            )
            if existing:
                skipped += 1
                continue

            new_enrollment = Enrollment(
                id=self._enrollments.next_id(),
                student_id=src_enrollment.student_id,
                school_id=src_enrollment.school_id,
                school_year_id=SchoolYearId(cmd.to_year_id),
                level_id=target_level.id,
                class_id=target_class_id,
                enrollment_date=datetime.date.today(),
                status=EnrollmentStatus.ACTIVE,
            )
            self._enrollments.save(new_enrollment)

            # Marquer l'ancienne inscription comme promue
            src_enrollment.mark_promoted()
            self._enrollments.save(src_enrollment)

            promoted += 1

        return PromoteClassResult(success=True, promoted_count=promoted, skipped_count=skipped)
