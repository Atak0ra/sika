"""
domain/student/value_objects.py
=================================
Value Objects du sous-domaine Étudiant.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class StudentId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("StudentId ne peut pas être vide.")

    @classmethod
    def generate(cls) -> StudentId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class StudentName:
    """Nom complet d'un élève (prénom + nom). Immuable."""
    first_name: str
    last_name: str

    def __post_init__(self) -> None:
        if not self.first_name.strip():
            raise ValueError("Le prénom ne peut pas être vide.")
        if not self.last_name.strip():
            raise ValueError("Le nom de famille ne peut pas être vide.")

    @property
    def full_name(self) -> str:
        return f"{self.first_name.strip()} {self.last_name.strip().upper()}"

    def __str__(self) -> str:
        return self.full_name
