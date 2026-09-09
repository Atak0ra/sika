"""
domain/student/entities.py
============================
Entité Student — IDENTITÉ PERMANENTE de l'élève.

REFONTE : Student n'a PLUS de classe, niveau ou statut.
Ces informations vivent dans l'entité Enrollment (liée à une année).

Student = la personne physique, qui vit à travers les années scolaires.
  - Awa était en CM1 en 2024 → Enrollment(2024-2025, CM1 A)
  - Awa est en CM2 en 2025  → Enrollment(2025-2026, CM2 A)
  - Student.id reste le même.
"""
from __future__ import annotations
import datetime
from dataclasses import dataclass
from typing import Optional

from ..school.value_objects import SchoolId
from .value_objects import StudentId, StudentName


@dataclass
class Student:
    """Identité permanente d'un élève.

    Attributes:
        id              : identifiant unique permanent.
        name            : nom complet (StudentName, immuable en pratique).
        school_id       : école d'appartenance (stable).
        date_of_birth   : date de naissance.
        photo_url       : lien photo optionnel (futur).
        notes           : remarques administratives permanentes.
    """
    id: StudentId
    name: StudentName
    school_id: SchoolId
    date_of_birth: Optional[datetime.date] = None
    notes: str = ""

    def __str__(self) -> str:
        return f"{self.name} (id={self.id})"
