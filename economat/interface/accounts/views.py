"""
interface/accounts/views.py
=============================
Vues du module Accounts.

Auto-inscription publique SUPPRIMÉE.
Le superuser crée les directeurs depuis /admin/.
Chaque utilisateur se connecte sur /eco/login/ avec son identifiant fourni.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from economat.application.dto_identity import CreateCollaboratorCommand
from economat.composition import (
    get_create_collaborator_use_case,
    get_list_memberships_query,
)
from economat.infrastructure.models import MembershipModel, SchoolModel
from economat.interface.decorators import require_membership
from economat.infrastructure.models import SchoolYearModel
from .forms import CreateCollaboratorForm, LoginForm


# ── Connexion / Déconnexion ───────────────────────────────────────────────────

def login_view(request):
    """Page de connexion pour tous les rôles (directeur, secrétaire, économe)."""
    if request.user.is_authenticated:
        return redirect("economat:school_selector")
    form  = LoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user:
            login(request, user)
            return redirect(request.GET.get("next") or "economat:school_selector")
        error = "Identifiant ou mot de passe incorrect."
    return render(request, "economat/accounts/login.html",
                  {"form": form, "error": error, "page_title": "Connexion"})


def logout_view(request):
    logout(request)
    return redirect("economat:login")


# ── Sélecteur d'école (après connexion) ───────────────────────────────────────────

@login_required
def school_selector(request):
    """
    Après connexion, redirige l'utilisateur vers son espace.
    - 1 école   → redirection directe selon le rôle
    - N écoles  → page de sélection
    - 0 école   → message d'erreur (le superuser doit rattacher l'utilisateur)
    """
    result      = get_list_memberships_query().execute(user_id=str(request.user.pk))
    memberships = result.memberships if result.success else []

    if not memberships:
        # Pas d'auto-inscription : contacter le superuser
        return render(request, "economat/accounts/no_school.html", {
            "page_title": "Aucune école",
        })

    if len(memberships) == 1:
        m = memberships[0]
        return _redirect_for_role(m["role"], m["school_id"])

    # Plusieurs écoles → page de sélection
    return render(request, "economat/accounts/school_selector.html",
                  {"memberships": memberships, "page_title": "Choisir une école"})


# ── Gestion de l'équipe (DIRECTOR uniquement) ────────────────────────────────────

@login_required
@require_membership
def team(request, school_id: str, membership=None):
    """Liste des membres + formulaire de création de collaborateur."""
    from economat.domain.shared.errors import DomainError
    from django.http import HttpResponseForbidden
    try:
        membership.guard_manage_team()
    except DomainError as e:
        return HttpResponseForbidden(str(e))

    school      = SchoolModel.objects.get(pk=school_id)
    members_orm = (MembershipModel.objects
                   .select_related("user")
                   .filter(school_id=school_id)
                   .order_by("role", "display_name"))
    form = CreateCollaboratorForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cmd = CreateCollaboratorCommand(
            director_user_id=str(request.user.pk),
            school_id=school_id,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            role=form.cleaned_data["role"],
        )
        result = get_create_collaborator_use_case().execute(cmd)
        if result.success:
            messages.success(
                request,
                f"Compte créé — {result.display_name} | "
                f"Identifiant : {result.username}",
            )
            return redirect("economat:team", school_id=school_id)
        messages.error(request, result.error_message)

    return render(request, "economat/accounts/team.html", {
        "school": school,
        # schools supprimé (non utilisé dans ces vues)
        "active_nav": "equipe",
        "school_year": SchoolYearModel.objects.filter(school_id=school_id, status="ACTIVE").first(),
        "members": members_orm,
        "form": form,
        "current_membership": membership,
        "page_title": f"Équipe — {school.name}",
    })


@login_required
@require_membership
def toggle_collaborator(request, school_id: str, member_id: str, membership=None):
    """Active / désactive un collaborateur (POST, DIRECTOR uniquement)."""
    if request.method != "POST":
        return redirect("economat:team", school_id=school_id)
    from economat.domain.shared.errors import DomainError
    try:
        membership.guard_manage_team()
        target = MembershipModel.objects.get(pk=member_id, school_id=school_id)
        if target.role == "DIRECTOR":
            messages.error(request, "Impossible de désactiver le directeur.")
        else:
            target.is_active = not target.is_active
            target.save(update_fields=["is_active"])
            action = "activé" if target.is_active else "désactivé"
            messages.success(request, f"Compte {action} : {target.display_name}.")
    except DomainError as e:
        messages.error(request, str(e))
    except MembershipModel.DoesNotExist:
        messages.error(request, "Collaborateur introuvable.")
    return redirect("economat:team", school_id=school_id)


# ── Helper ─────────────────────────────────────────────────────────────────────────────

def _redirect_for_role(role: str, school_id: str):
    """Redirige vers l'espace métier selon le rôle."""
    if role == "DIRECTOR":
        return redirect("economat:director_dashboard")
    if role == "SECRETARY":
        return redirect("economat:director_dashboard")
    # Économe → interface encaissement uniquement
    return redirect("economat:econome_dashboard")


# ── Profil utilisateur ────────────────────────────────────────────────────────

@login_required
def profile(request):
    """Affiche et met à jour le profil (nom, prénom, email)."""
    from economat.composition import get_user_repository
    from .forms import ProfileForm

    user_repo  = get_user_repository()
    memberships = MembershipModel.objects.select_related("school").filter(
        user=request.user, is_active=True
    ).order_by("role")

    initial = {
        "first_name": request.user.first_name,
        "last_name":  request.user.last_name,
        "email":      request.user.email,
    }
    form = ProfileForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        user_repo.update_profile(
            user_id    = str(request.user.pk),
            first_name = form.cleaned_data["first_name"],
            last_name  = form.cleaned_data["last_name"],
            email      = form.cleaned_data["email"] or "",
        )
        # Rafraîchir le user en session
        request.user.first_name = form.cleaned_data["first_name"]
        request.user.last_name  = form.cleaned_data["last_name"]
        request.user.email      = form.cleaned_data["email"] or ""
        messages.success(request, "✅ Profil mis à jour.")
        return redirect("economat:profile")

    return render(request, "economat/accounts/profile.html", {
        "form":        form,
        "memberships": memberships,
        "page_title":  "Mon profil",
    })


@login_required
def change_password(request):
    """Changement de mot de passe avec vérification de l'ancien."""
    from django.contrib.auth import update_session_auth_hash
    from economat.composition import get_user_repository
    from .forms import ChangePasswordForm

    user_repo = get_user_repository()
    form = ChangePasswordForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        old_pw = form.cleaned_data["old_password"]
        if not user_repo.verify_password(str(request.user.pk), old_pw):
            form.add_error("old_password", "Mot de passe actuel incorrect.")
        else:
            user_repo.set_password(
                user_id      = str(request.user.pk),
                new_password = form.cleaned_data["new_password1"],
            )
            # Maintenir la session active après le changement
            update_session_auth_hash(request, request.user)
            messages.success(request, "✅ Mot de passe modifié avec succès.")
            return redirect("economat:profile")

    return render(request, "economat/accounts/change_password.html", {
        "form":       form,
        "page_title": "Changer le mot de passe",
    })
