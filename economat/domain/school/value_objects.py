"""
domain/school/value_objects.py
================================
Value Objects d'identité pour le sous-domaine École.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass

def _uid(): return str(uuid.uuid4())

@dataclass(frozen=True)
class SchoolId:
    value: str
    def __post_init__(self):
        if not self.value or not self.value.strip(): raise ValueError("SchoolId vide.")
    @classmethod
    def generate(cls): return cls(value=_uid())
    def __str__(self): return self.value

@dataclass(frozen=True)
class SchoolYearId:
    """ID unique d'une année scolaire (UUID). Le label '2024-2025' est sur l'entité."""
    value: str
    def __post_init__(self):
        if not self.value or not self.value.strip(): raise ValueError("SchoolYearId vide.")
    @classmethod
    def generate(cls): return cls(value=_uid())
    def __str__(self): return self.value

@dataclass(frozen=True)
class LevelId:
    value: str
    def __post_init__(self):
        if not self.value or not self.value.strip(): raise ValueError("LevelId vide.")
    @classmethod
    def generate(cls): return cls(value=_uid())
    def __str__(self): return self.value

@dataclass(frozen=True)
class ClassId:
    value: str
    def __post_init__(self):
        if not self.value or not self.value.strip(): raise ValueError("ClassId vide.")
    @classmethod
    def generate(cls): return cls(value=_uid())
    def __str__(self): return self.value

@dataclass(frozen=True)
class PaymentScheduleId:
    value: str
    def __post_init__(self):
        if not self.value or not self.value.strip(): raise ValueError("PaymentScheduleId vide.")
    @classmethod
    def generate(cls): return cls(value=_uid())
    def __str__(self): return self.value
