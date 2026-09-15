"""
domain/payment/value_objects.py
=================================
Value Objects du sous-domaine Paiement.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class PaymentId:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("PaymentId ne peut pas être vide.")

    @classmethod
    def generate(cls) -> PaymentId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


class PaymentMethod(str, Enum):
    """Moyen de paiement utilisé par le parent."""
    ESPECES      = "ESPECES"       # Paiement en cash
    MOBILE_MONEY = "MOBILE_MONEY"  # Orange Money, Wave, MTN…
    VIREMENT     = "VIREMENT"      # Virement bancaire
    CHEQUE       = "CHEQUE"        # Chèque (rare mais possible)


# Opérateurs Mobile Money disponibles par pays — utilisé pour proposer la bonne
# liste à l'économe / au portail selon le pays de l'école.
# Clé : code ISO alpha-2 (ex. "SN") — source de vérité = CountryModel en base.
# Ce dict sert de FALLBACK quand la base n'est pas disponible (tests unitaires
# purs, migrations, etc.).
_FALLBACK_MOBILE_OPERATORS: dict[str, list[str]] = {
    "SN": ["Orange Money", "Wave", "Free Money"],
    "CI": ["Orange Money", "MTN Mobile Money", "Moov Money", "Wave"],
    "TG": ["Flooz (Togocom)", "T-Money (Togocom)", "Wave"],
    "BJ": ["MTN Mobile Money", "Moov Money"],
    "GN": ["Orange Money", "MTN Mobile Money"],
}

DEFAULT_MOBILE_OPERATORS = ["Orange Money", "MTN Mobile Money", "Moov Money", "Wave"]


def mobile_operators_for_country(country) -> list[str]:
    """
    Retourne les opérateurs Mobile Money pour un pays donné.

    Accepte :
      - un CountryModel ORM (SchoolModel.country) → lit .mobile_operators directement
      - un code ISO string ("SN", "GN"…)
      - None → liste par défaut
    """
    # CountryModel instance directe
    if country is not None and hasattr(country, "mobile_operators"):
        ops = country.mobile_operators
        return ops if ops else DEFAULT_MOBILE_OPERATORS

    # Code ISO string — interroge la base, fallback dict si indisponible
    if isinstance(country, str) and country.strip():
        code = country.strip().upper()
        try:
            from economat.infrastructure.models import CountryModel
            obj = CountryModel.objects.filter(code=code).first()
            if obj and obj.mobile_operators:
                return obj.mobile_operators
        except Exception:  # noqa: BLE001
            pass
        return _FALLBACK_MOBILE_OPERATORS.get(code, DEFAULT_MOBILE_OPERATORS)

    return DEFAULT_MOBILE_OPERATORS


# Identité visuelle (monogramme + couleurs) de chaque opérateur — pour un
# sélecteur en cartes plutôt qu'un <select> brut, homogène avec les cartes
# "Moyen de paiement". Pas de vrai logo (droits de marque) : un monogramme
# dans la couleur associée à l'opérateur suffit à le reconnaître d'un coup d'œil.
MOBILE_OPERATOR_STYLES: dict[str, dict[str, str]] = {
    "Orange Money":      {"short": "OM",    "bg": "#fff4e6", "fg": "#e8590c"},
    "Wave":              {"short": "W",     "bg": "#e6f9fb", "fg": "#0aa8c2"},
    "Free Money":        {"short": "FM",    "bg": "#fdeaea", "fg": "#c0392b"},
    "MTN Mobile Money":  {"short": "MTN",   "bg": "#fff9db", "fg": "#a16207"},
    "Moov Money":        {"short": "Moov",  "bg": "#e7edff", "fg": "#2952cc"},
    "Flooz (Togocom)":   {"short": "Flooz", "bg": "#ffe8e0", "fg": "#d94f1e"},
    "T-Money (Togocom)": {"short": "T-Mo",  "bg": "#e3f2ff", "fg": "#1565c0"},
}

DEFAULT_OPERATOR_STYLE = {"short": "MM", "bg": "#f1f2f6", "fg": "#52556b"}


def mobile_operator_style(name: str) -> dict[str, str]:
    """Style (monogramme + couleurs) d'un opérateur, ou un style neutre par défaut."""
    return MOBILE_OPERATOR_STYLES.get(name, DEFAULT_OPERATOR_STYLE)


class PaymentStatus(str, Enum):
    """Statut de paiement calculé pour un élève à une date donnée."""
    SOLDE     = "SOLDE"      # 100% des frais payés
    EN_COURS  = "EN_COURS"   # Paiements en cours, pas encore en retard
    EN_RETARD = "EN_RETARD"  # Une ou plusieurs échéances dépassées non couvertes
    NON_PAYE  = "NON_PAYE"   # Aucun paiement enregistré

    @property
    def label(self) -> str:
        labels = {
            PaymentStatus.SOLDE:     "Soldé",
            PaymentStatus.EN_COURS:  "En cours",
            PaymentStatus.EN_RETARD: "En retard",
            PaymentStatus.NON_PAYE:  "Non payé",
        }
        return labels[self]
