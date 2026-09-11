"""
economat/templatetags/economat_tags.py
=========================================
Filtres Django custom pour l'affichage des montants en FCFA.

Usage dans les templates :
    {% load economat_tags %}
    {{ 150000|fcfa }}              → "150 000 F"
    {{ 150000|fcfa_long }}         → "150 000 FCFA"
    {{ 150000|spacemil }}          → "150 000"
    {{ 150000|amount_to_words }}   → "Cent cinquante mille francs CFA"
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


# ─ Montant en lettres (français) ──────────────────────────────────────────────

_UNITES = [
    "", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
    "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
    "dix-sept", "dix-huit", "dix-neuf",
]
_DIZAINES = [
    "", "", "vingt", "trente", "quarante", "cinquante",
    "soixante", "soixante", "quatre-vingt", "quatre-vingt",
]


def _below_thousand(n: int) -> str:
    """Convertit un entier 0–999 en lettres françaises."""
    if n == 0:
        return ""
    if n < 20:
        return _UNITES[n]
    if n < 100:
        d, u = divmod(n, 10)
        if d == 7 or d == 9:          # 70-79, 90-99 : soixante-dix / quatre-vingt-dix
            u += 10
        sep = "-" if u else ""
        et  = "-et-" if u == 1 and d in (2, 3, 4, 5, 6, 7) else sep
        return _DIZAINES[d] + (et + _UNITES[u] if u else ("s" if d == 8 else ""))
    c, reste = divmod(n, 100)
    if c == 1:
        cent = "cent"
    else:
        cent = _UNITES[c] + " cent"
    if reste:
        # "cent" perd le "s" quand il est suivi d'autres chiffres
        return cent + " " + _below_thousand(reste)
    return cent + ("s" if c > 1 else "")


def _int_to_fr(n: int) -> str:
    """Convertit un entier positif en lettres françaises (jusqu'à 999 999 999)."""
    if n == 0:
        return "zéro"
    parts = []
    milliards, n = divmod(n, 1_000_000_000)
    millions,  n = divmod(n, 1_000_000)
    milliers,  n = divmod(n, 1_000)

    def _mult(x: int) -> str:
        """Forme multiplicateur : 'cinq cent' (sans s) même si x == 500."""
        t = _below_thousand(x)
        # Supprime le 's' final de 'cents' et 'quatre-vingts' en position de multiplicateur
        if t.endswith("cents"):
            t = t[:-1]
        if t.endswith("vingts"):
            t = t[:-1]
        return t

    if milliards:
        parts.append(_mult(milliards) + " milliard" + ("s" if milliards > 1 else ""))
    if millions:
        parts.append(_mult(millions) + " million" + ("s" if millions > 1 else ""))
    if milliers:
        if milliers == 1:
            parts.append("mille")
        else:
            parts.append(_mult(milliers) + " mille")
    if n:
        parts.append(_below_thousand(n))

    return " ".join(p for p in parts if p)


@register.filter
def amount_to_words(value) -> str:
    """
    150000 → 'Cent cinquante mille francs CFA'
    Utilisé sur les reçus officiels.
    """
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    if n <= 0:
        return "zéro franc CFA"
    words = _int_to_fr(n)
    # Majuscule initiale
    words = words[0].upper() + words[1:]
    return f"{words} franc{'s' if n > 1 else ''} CFA"

