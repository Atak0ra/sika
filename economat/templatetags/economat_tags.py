"""
economat/templatetags/economat_tags.py
=========================================
Filtres Django custom pour l'affichage des montants en FCFA.

Usage dans les templates :
    {% load economat_tags %}
    {{ 150000|fcfa }}          → "150 000 F"
    {{ 150000|fcfa_long }}     → "150 000 FCFA"
    {{ 150000|spacemil }}      → "150 000"
"""

from django import template

register = template.Library()

_NBSP = "\u202f"   # espace fine insécable (norme typographique française pour les nombres)


def _format_int(value: int | str) -> str:
    """Formate un entier avec des espaces fines insécables comme séparateurs de milliers."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    # Formatage Python avec virgule puis remplacement
    return f"{n:,}".replace(",", _NBSP)


@register.filter
def spacemil(value) -> str:
    """150000 → '150 000' (espace insécable, sans devise)."""
    return _format_int(value)


@register.filter
def fcfa(value) -> str:
    """150000 → '150 000 F' (format court, typographie FCFA)."""
    return f"{_format_int(value)} F"


@register.filter
def fcfa_long(value) -> str:
    """150000 → '150 000 FCFA' (format long)."""
    return f"{_format_int(value)} FCFA"
