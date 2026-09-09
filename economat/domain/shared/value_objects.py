"""
domain/shared/value_objects.py
================================
Value Objects transverses : Money et Currency.

Principes DDD appliqués :
- Immuabilité totale via __slots__ + propriétés en lecture seule.
- Égalité par valeur (pas par identité référentielle).
- Le domaine ne connaît pas SQLite, Django, ni décimaux à virgule flottante.
- Le FCFA (XOF) n'a PAS de décimales → on stocke des entiers (1 FCFA = 1 unité).
  Exemple : 25 000 FCFA → Money(25_000, Currency.XOF)
"""

from __future__ import annotations
from enum import Enum
from .errors import CurrencyMismatchError, NegativeAmountError


class Currency(str, Enum):
    """Devises supportées. Étend str pour sérialisation JSON/ORM transparente."""
    XOF = "XOF"   # Franc CFA BCEAO (Afrique de l'Ouest) — 0 décimale
    XAF = "XAF"   # Franc CFA BEAC (Afrique Centrale)    — 0 décimale
    EUR = "EUR"   # Euro — 2 décimales (futur)
    USD = "USD"   # Dollar américain — 2 décimales (futur)

    @property
    def decimal_places(self) -> int:
        return 0 if self in (Currency.XOF, Currency.XAF) else 2

    @property
    def symbol(self) -> str:
        return {Currency.XOF: "FCFA", Currency.XAF: "FCFA",
                Currency.EUR: "€", Currency.USD: "$"}[self]


class Money:
    """Value Object monétaire — immuable, comparable, opérable.

    Stocké en entier pour éviter les erreurs de flottants.
    Pour XOF/XAF : 1 unité = 1 FCFA (pas de centime).

    Usage :
        frais  = Money(75_000, Currency.XOF)
        acompte = Money(25_000, Currency.XOF)
        reste  = frais - acompte   # Money(50_000, XOF)
        str(frais)                 # "75 000 FCFA"
    """

    __slots__ = ("_amount", "_currency")

    def __init__(self, amount: int, currency: Currency) -> None:
        if not isinstance(amount, int):
            raise TypeError(
                f"Money.amount doit être un entier (reçu {type(amount).__name__}). "
                "Pour XOF, 25 000 FCFA = Money(25_000, Currency.XOF)."
            )
        if amount < 0:
            raise NegativeAmountError(
                f"Un montant monétaire ne peut pas être négatif (reçu {amount})."
            )
        if not isinstance(currency, Currency):
            raise TypeError(f"currency doit être une instance de Currency.")
        object.__setattr__(self, "_amount", amount)
        object.__setattr__(self, "_currency", currency)

    # ── Immuabilité ───────────────────────────────────────────────────────────

    def __setattr__(self, key: str, value: object) -> None:  # type: ignore[override]
        raise AttributeError("Money est immuable.")

    # ── Propriétés ────────────────────────────────────────────────────────────

    @property
    def amount(self) -> int:
        return self._amount

    @property
    def currency(self) -> Currency:
        return self._currency

    # ── Égalité & comparaison ─────────────────────────────────────────────────

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        return self._amount == other._amount and self._currency == other._currency

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))

    def __lt__(self, other: Money) -> bool:
        self._guard_currency(other)
        return self._amount < other._amount

    def __le__(self, other: Money) -> bool:
        self._guard_currency(other)
        return self._amount <= other._amount

    def __gt__(self, other: Money) -> bool:
        self._guard_currency(other)
        return self._amount > other._amount

    def __ge__(self, other: Money) -> bool:
        self._guard_currency(other)
        return self._amount >= other._amount

    # ── Opérations arithmétiques ──────────────────────────────────────────────

    def add(self, other: Money) -> Money:
        """Additionne deux montants de la même devise. Retourne un nouveau Money."""
        self._guard_currency(other)
        return Money(self._amount + other._amount, self._currency)

    def subtract(self, other: Money) -> Money:
        """Soustrait. Retourne un nouveau Money (>= 0)."""
        self._guard_currency(other)
        result = self._amount - other._amount
        if result < 0:
            raise NegativeAmountError(
                f"Soustraction impossible : {self} - {other} = {result} FCFA négatif."
            )
        return Money(result, self._currency)

    def multiply(self, factor: int | float) -> Money:
        """Multiplie par un facteur. Arrondi à l'entier le plus proche."""
        if factor < 0:
            raise NegativeAmountError(f"Le facteur multiplicatif ne peut pas être négatif ({factor}).")
        return Money(round(self._amount * factor), self._currency)

    def is_zero(self) -> bool:
        return self._amount == 0

    def percentage(self, pct: float) -> Money:
        """Calcule un pourcentage du montant. Ex : frais.percentage(30) → 30% des frais."""
        if not (0 <= pct <= 100):
            raise ValueError(f"Le pourcentage doit être entre 0 et 100 (reçu {pct}).")
        return Money(round(self._amount * pct / 100), self._currency)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _guard_currency(self, other: Money) -> None:
        if self._currency != other._currency:
            raise CurrencyMismatchError(
                f"Impossible d'opérer entre {self._currency.value} et "
                f"{other._currency.value}. Convertissez d'abord."
            )

    # ── Représentation ────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"Money(amount={self._amount}, currency={self._currency.value!r})"

    def __str__(self) -> str:
        # Format local Afrique de l'Ouest : séparateur milliers = espace insécable
        formatted = f"{self._amount:,}".replace(",", "\u202f")
        return f"{formatted} {self._currency.symbol}"

    # ── Factories ─────────────────────────────────────────────────────────────

    @classmethod
    def zero(cls, currency: Currency = Currency.XOF) -> Money:
        return cls(0, currency)

    @classmethod
    def of_xof(cls, amount: int) -> Money:
        """Factory courte pour le FCFA : Money.of_xof(25_000)."""
        return cls(amount, Currency.XOF)
