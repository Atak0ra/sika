"""
domain/enrollment/value_objects.py
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class EnrollmentId:
    value: str
    def __post_init__(self):
        if not self.value or not self.value.strip():
            raise ValueError("EnrollmentId vide.")
    @classmethod
    def generate(cls): return cls(value=str(uuid.uuid4()))
    def __str__(self): return self.value


class EnrollmentStatus(str, Enum):
    ACTIVE   = "ACTIVE"    # Élève inscrit et présent cette année
    INACTIVE = "INACTIVE"  # Désactivé en cours d'année (départ, transfert)
    PROMOTED = "PROMOTED"  # Réinscrit l'année suivante (terminé)
