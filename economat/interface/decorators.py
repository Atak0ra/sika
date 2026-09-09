"""
interface/decorators.py
=========================
Décorateurs de sécurité pour les vues de l'économat.

3 décorateurs complémentaires :
  @login_required         → Django natif (redirige vers login si non connecté)
  @require_membership     → Vérifie que l'utilisateur est membre de l'école
                            passée en paramètre d'URL (school_id).
                            Injecte `membership` dans kwargs de la vue.
                            Retourne 403 si non membre.
  @require_role(Role.X)   → Vérifie le rôle sur le membership déjà chargé.
                            Retourne 403 si rôle insuffisant.

Usage dans une vue :
    @login_required
    @require_membership
    def configure_pricing(request, school_id, membership=None):
        membership.guard_configure_pricing()  # lève 403 si pas DIRECTOR
        ...

    # OU plus concis :
    @login_required
    @require_role(Role.DIRECTOR)
    def configure_pricing(request, school_id, membership=None):
        ...
"""

from __future__ import annotations

import functools
from typing import Callable

from django.contrib.auth.decorators import login_required as _django_login_required
from django.http import HttpResponseForbidden

from economat.domain.identity.value_objects import Role


def require_membership(view_func: Callable) -> Callable:
    """
    Vérifie que l'utilisateur connecté est membre actif de l'école (school_id dans l'URL).
    Injecte `membership=<Membership>` dans les kwargs de la vue.
    Retourne HTTP 403 si non membre.

    Doit être utilisé APRÈS @login_required.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        school_id = kwargs.get("school_id") or (args[0] if args else None)
        if not school_id:
            return HttpResponseForbidden("Paramètre school_id manquant.")

        from economat.composition import get_membership_query
        membership = get_membership_query().execute(
            user_id=str(request.user.pk),
            school_id=school_id,
        )
        if membership is None or not membership.is_active:
            return HttpResponseForbidden(
                "Accès refusé : vous n'êtes pas membre de cette école."
            )
        kwargs["membership"] = membership
        return view_func(request, *args, **kwargs)
    return wrapper


def require_role(*roles: Role) -> Callable:
    """
    Décorateur de rôle — vérifie que le membership chargé a l'un des rôles requis.
    Doit être utilisé APRÈS @require_membership (qui injecte `membership`).

    Usage : @require_role(Role.DIRECTOR)
    """
    def decorator(view_func: Callable) -> Callable:
        @functools.wraps(view_func)
        def wrapper(request, *args, **kwargs):
            membership = kwargs.get("membership")
            if membership is None:
                return HttpResponseForbidden("Membership manquant (vérifiez l'ordre des décorateurs).")
            if membership.role not in roles:
                role_labels = " ou ".join(r.label for r in roles)
                return HttpResponseForbidden(
                    f"Accès refusé. Rôle requis : {role_labels}. "
                    f"Votre rôle : {membership.role.label}."
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# Alias pratique : combine login_required + require_membership en une seule ligne
def school_member_required(view_func: Callable) -> Callable:
    """Raccourci = @login_required + @require_membership."""
    return _django_login_required(require_membership(view_func))
