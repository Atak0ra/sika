"""
domain/shared/errors.py
=======================
Hiérarchie d'erreurs du domaine.

Règle d'or : ces exceptions ne dépendent d'AUCUN framework.
Elles représentent des violations de règles métier, pas des erreurs techniques.
"""


class DomainError(Exception):
    """Erreur racine du domaine économat. Toujours attrapée dans les use cases."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return self.message


# ── Erreurs d'entités ─────────────────────────────────────────────────────────

class EntityNotFoundError(DomainError):
    """Entité introuvable dans le dépôt (par exemple : élève inconnu)."""


class DuplicateEntityError(DomainError):
    """Tentative de création d'une entité qui existe déjà."""


# ── Erreurs monétaires ────────────────────────────────────────────────────────

class CurrencyMismatchError(DomainError):
    """Opération entre deux montants de devises différentes."""


class NegativeAmountError(DomainError):
    """Montant négatif interdit dans ce contexte."""


class ZeroAmountError(DomainError):
    """Montant nul interdit dans ce contexte."""


# ── Erreurs de règles métier ──────────────────────────────────────────────────

class PaymentAlreadyFullyPaidError(DomainError):
    """Tentative d'enregistrer un paiement sur un compte déjà soldé."""


class PaymentExceedsBalanceError(DomainError):
    """Le montant versé dépasse le reliquat dû."""


class InvalidPaymentScheduleError(DomainError):
    """Le barème de paiement configuré est invalide (ex. tranches ne couvrant pas le total)."""


class StudentNotInSchoolError(DomainError):
    """L'élève n'appartient pas à cette école."""


class ClassLevelMismatchError(DomainError):
    """La classe n'appartient pas au niveau indiqué."""
