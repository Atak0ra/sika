"""
domain/enrollment/entities.py
================================
Entité Enrollment — l'inscription d'un élève dans une classe pour UNE année scolaire.

C'est l'entité pivot qui relie :
  Student (identité permanente)
    → Class (de cette année)
    → SchoolYear
    → Payment[] (rattachés à cet Enrollment)

Règles métier :
- Un élève ne peut avoir qu'une seule inscription ACTIVE par année et par école.
- Les paiements sont liés à l'Enrollment, pas directement à l'élève.
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass, field
from typing import Optional

from ..school.value_objects import ClassId, LevelId, SchoolId, SchoolYearId
from ..student.value_objects import StudentId
from .value_objects import EnrollmentId, EnrollmentStatus


@dataclass
class Enrollment:
    id: EnrollmentId
    student_id: StudentId
    school_id: SchoolId
    school_year_id: SchoolYearId
    level_id: LevelId
    class_id: ClassId
    enrollment_date: datetime.date
    status: EnrollmentStatus = EnrollmentStatus.ACTIVE
    notes: str = ""
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

    def __post_init__(self):
        pass  # La validation de date est gérée côté formulaire/use case

    def deactivate(self, reason: str = "") -> None:
        self.status = EnrollmentStatus.INACTIVE
        if reason:
            self.notes = f"[INACTIF] {reason}" + (f" — {self.notes}" if self.notes else "")

    def mark_promoted(self) -> None:
        """Marque l'inscription comme terminée (passage en année suivante)."""
        self.status = EnrollmentStatus.PROMOTED

    def is_active(self) -> bool:
        return self.status == EnrollmentStatus.ACTIVE

    def __str__(self) -> str:
        return f"Enrollment({self.student_id} → class={self.class_id} [{self.status.value}])"
