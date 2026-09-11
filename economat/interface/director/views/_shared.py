"""
interface/director/views/_shared.py
=====================================
Helpers et contexte partagés entre toutes les vues directeur.

- base_context()   : construit le dict de contexte sidebar commun
                     (élimine la duplication ~12 vues + 1 requête DB par vue).
- _director_schools()
- _active_year()
- _sidebar_levels()

Sécurité :
  - base_context() utilise le `membership` déjà injecté par @require_membership
    → membership.role.value (enum Role(str,Enum)) = string "DIRECTOR"/"SECRETARY"
    → 0 requête supplémentaire pour le rôle.
  - Les lookups d'objets enfants (class, enrollment) doivent TOUJOURS inclure
    un filtre parent (school_year_id) pour empêcher l'IDOR (OWASP A01).
"""
from __future__ import annotations

from typing import Any

from economat.composition import get_list_memberships_query
from economat.domain.identity.entities import Membership
from economat.infrastructure.models import LevelModel, SchoolModel, SchoolYearModel


# ─ Helpers internes ──────────────────────────────────────────────────────────


def _director_schools(user):
    """Retourne les SchoolModel accessibles par l'utilisateur (DIRECTOR + SECRETARY)."""
    result = get_list_memberships_query().execute(user_id=str(user.pk))
    ids = [
        m["school_id"]
        for m in result.memberships
        if m["role"] in ("DIRECTOR", "SECRETARY")
    ]
    return SchoolModel.objects.filter(id__in=ids).order_by("name")


def _active_year(school_id: str):
    """Retourne l'année scolaire ACTIVE de l'école, ou None."""
    return SchoolYearModel.objects.filter(school_id=school_id, status="ACTIVE").first()


def _sidebar_levels(year) -> list:
    """
    Retourne [{level, classes}] pour la barre latérale de navigation.
    Utilise prefetch_related pour éviter le N+1 sur les classes.
    """
    if not year:
        return []
    levels_qs = (
        LevelModel.objects
        .filter(school_year_id=year.id)
        .prefetch_related("classes")
        .order_by("name")
    )
    return [
        {"level": lvl, "classes": lvl.classes.order_by("name")}
        for lvl in levels_qs
    ]


# ─ Contexte commun ────────────────────────────────────────────────────────────


def base_context(
    request,
    school,
    year,
    active_nav: str,
    *,
    membership: Membership | None = None,
    **extra: Any,
) -> dict:
    """
    Construit le dictionnaire de contexte commun à toutes les vues directeur.

    Avantages :
      - Élimine la duplication dans ~12 vues (school, school_year, all_years,
        sidebar_levels, schools, user_role).
      - Utilise `membership.role.value` (déjà injecté par @require_membership)
        au lieu de refaire une requête MembershipModel → économie 1 SQL/vue.
      - Accepte **extra pour les clés spécifiques à chaque vue.

    Args:
        request    : HttpRequest Django.
        school     : SchoolModel ou None.
        year       : SchoolYearModel ou None.
        active_nav : clé de navigation active (ex. "dashboard", "eleves"…).
        membership : entité Membership injectée par @require_membership (optionnel).
        **extra    : clés supplémentaires spécifiques à la vue.
    """
    # Rôle depuis le membership injecté (0 requête) — fallback DB uniquement
    # pour les vues sans @require_membership (ex. dashboard).
    if membership is not None:
        user_role = membership.role.value
    else:
        from economat.infrastructure.models import MembershipModel
        m = MembershipModel.objects.filter(user=request.user, is_active=True).first()
        user_role = m.role if m else ""

    ctx = {
        "school":          school,
        "school_year":     year,
        "active_nav":      active_nav,
        "schools":         _director_schools(request.user),
        "all_years": (
            SchoolYearModel.objects.filter(school_id=school.id).order_by("-label")
            if school else []
        ),
        "sidebar_levels":  _sidebar_levels(year),
        "user_role":       user_role,
    }
    ctx.update(extra)
    return ctx
