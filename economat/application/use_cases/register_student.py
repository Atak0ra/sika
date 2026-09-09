"""
application/use_cases/register_student.py
==========================================
USE CASE : RegisterStudentUseCase
Crée l'identité Student (si nouvelle) ET l'Enrollment dans l'année active.
"""
from __future__ import annotations
import datetime

from economat.application.dto import RegisterStudentCommand, RegisterStudentResult
from economat.application.ports.repositories import (
    EnrollmentRepository, SchoolYearRepository, StudentRepository,
)
from economat.domain.enrollment.entities import Enrollment
from economat.domain.enrollment.value_objects import EnrollmentStatus
from economat.domain.school.value_objects import ClassId, LevelId, SchoolId, SchoolYearId
from economat.domain.shared.errors import DomainError, DuplicateEntityError, EntityNotFoundError
from economat.domain.student.entities import Student
from economat.domain.student.value_objects import StudentId, StudentName


class RegisterStudentUseCase:
    def __init__(self, student_repo: StudentRepository,
                 year_repo: SchoolYearRepository,
                 enrollment_repo: EnrollmentRepository) -> None:
        self._students    = student_repo
        self._years       = year_repo
        self._enrollments = enrollment_repo

    def execute(self, cmd: RegisterStudentCommand) -> RegisterStudentResult:
        try:
            return self._execute(cmd)
        except DomainError as e:
            return RegisterStudentResult(success=False, error_message=str(e))
        except Exception as e:
            return RegisterStudentResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: RegisterStudentCommand) -> RegisterStudentResult:
        year_id   = SchoolYearId(cmd.year_id)
        school_id = SchoolId(cmd.school_id)

        # 1. Vérifier que l'année scolaire est active ou DRAFT
        year = self._years.find_by_id(year_id)
        if year is None:
            raise EntityNotFoundError(f"Année scolaire introuvable.")
        if year.is_closed:
            raise DomainError("Impossible d'inscrire un élève dans une année clôturée.")

        # 2. Vérifier classe + niveau
        level = year.get_level(LevelId(cmd.level_id))
        klass = level.find_class(ClassId(cmd.class_id))
        if klass is None:
            raise EntityNotFoundError(f"Classe introuvable dans ce niveau.")

        # 3. Créer l'identité Student
        if not cmd.first_name.strip() or not cmd.last_name.strip():
            raise DomainError("Le prénom et le nom sont obligatoires.")

        student = Student(
            id=self._students.next_id(),
            name=StudentName(first_name=cmd.first_name.strip(), last_name=cmd.last_name.strip()),
            school_id=school_id,
            date_of_birth=cmd.date_of_birth,
            notes=cmd.notes,
        )
        self._students.save(student)

        # 4. Créer l'Enrollment
        enrollment = Enrollment(
            id=self._enrollments.next_id(),
            student_id=student.id,
            school_id=school_id,
            school_year_id=year_id,
            level_id=level.id,
            class_id=klass.id,
            enrollment_date=cmd.enrollment_date or datetime.date.today(),
            status=EnrollmentStatus.ACTIVE,
            notes=cmd.notes,
        )
        self._enrollments.save(enrollment)

        return RegisterStudentResult(
            success=True, student_id=str(student.id),
            enrollment_id=str(enrollment.id),
            student_name=student.name.full_name,
            class_name=klass.name, level_name=level.name,
        )
