"""
interface/accounts/views.py
=============================
Vues du module Accounts.

Auto-inscription publique SUPPRIMÉE.
Le superuser crée les directeurs depuis /admin/.
Chaque utilisateur se connecte sur /eco/login/ avec son identifiant fourni.
"""
from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from economat.application.dto_identity import CreateCollaboratorCommand, RegisterSchoolCommand
from economat.composition import (
    get_create_collaborator_use_case,
    get_list_memberships_query,
    get_register_school_use_case,
    get_user_repository,
)
from economat.domain.shared.errors import DomainError
from economat.infrastructure.models import (
    MembershipModel,
    SchoolModel,
    SchoolYearModel,
)
from economat.interface.decorators import require_membership

from .forms import ChangePasswordForm, CreateCollaboratorForm, LoginForm, PotentialCustomerForm, ProfileForm, SchoolRegistrationForm

# ── Connexion / Déconnexion ───────────────────────────────────────────────────

def login_view(request):
    """Page de connexion pour tous les rôles (directeur, secrétaire, économe)."""
    if request.user.is_authenticated:
        return redirect("economat:school_selector")
    form  = LoginForm(request.POST or None)
    error = None
    if request.method == "POST" and form.is_valid():
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password"]
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            # ── Génère le verifier offline après connexion en ligne réussie ──
            # Le verifier PBKDF2 dédié est stocké en base et retourné au client
            # via /eco/offline-credential/ (appelé par auth-offline.js).
            # Ne bloque JAMAIS la connexion même en cas d'échec.
            try:
                from economat.infrastructure.auth.offline_credential_service import (
                    save_offline_credential,
                )
                save_offline_credential(user, password)
            except Exception:
                pass
            return redirect(request.GET.get("next") or "economat:school_selector")
        error = "Identifiant ou mot de passe incorrect."
    return render(request, "economat/accounts/login.html",
                  {"form": form, "error": error, "page_title": "Connexion"})


def logout_view(request):
    logout(request)
    return redirect("economat:landing")


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
        return redirect("economat:secretary_dashboard")
    # Économe → interface encaissement uniquement
    return redirect("economat:econome_dashboard")


# ── Profil utilisateur ────────────────────────────────────────────────────────

@login_required
def profile(request):
    """Affiche et met à jour le profil (nom, prénom, email)."""
    from economat.infrastructure.models import LevelModel

    user_repo  = get_user_repository()
    memberships = MembershipModel.objects.select_related("school").filter(
        user=request.user, is_active=True
    ).order_by("role")

    # Contexte sidebar : on prend la première école active de l'utilisateur
    first_membership = memberships.first()
    school = first_membership.school if first_membership else None
    school_year = (
        SchoolYearModel.objects.filter(school_id=school.id, status="ACTIVE").first()
        if school else None
    )
    all_years = (
        SchoolYearModel.objects.filter(school_id=school.id).order_by("-label")
        if school else []
    )
    sidebar_levels = []
    if school_year:
        levels_qs = (LevelModel.objects
                     .filter(school_year_id=school_year.id)
                     .prefetch_related("classes")
                     .order_by("name"))
        sidebar_levels = [{"level": lvl, "classes": lvl.classes.order_by("name")} for lvl in levels_qs]

    user_role = first_membership.role if first_membership else ""

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
        "form":           form,
        "memberships":    memberships,
        "page_title":     "Mon profil",
        # Contexte sidebar
        "school":         school,
        "school_year":    school_year,
        "all_years":      all_years,
        "sidebar_levels": sidebar_levels,
        "user_role":      user_role,
        "active_nav":     "profil",
    })


@login_required
def change_password(request):
    """Changement de mot de passe avec vérification de l'ancien."""
    from economat.infrastructure.models import LevelModel

    user_repo = get_user_repository()
    form = ChangePasswordForm(request.POST or None)

    # Contexte sidebar
    first_membership = MembershipModel.objects.select_related("school").filter(
        user=request.user, is_active=True
    ).order_by("role").first()
    school = first_membership.school if first_membership else None
    school_year = (
        SchoolYearModel.objects.filter(school_id=school.id, status="ACTIVE").first()
        if school else None
    )
    all_years = (
        SchoolYearModel.objects.filter(school_id=school.id).order_by("-label")
        if school else []
    )
    sidebar_levels = []
    if school_year:
        levels_qs = (LevelModel.objects
                     .filter(school_year_id=school_year.id)
                     .prefetch_related("classes")
                     .order_by("name"))
        sidebar_levels = [{"level": lvl, "classes": lvl.classes.order_by("name")} for lvl in levels_qs]
    user_role = first_membership.role if first_membership else ""

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
        "form":           form,
        "page_title":     "Changer le mot de passe",
        # Contexte sidebar
        "school":         school,
        "school_year":    school_year,
        "all_years":      all_years,
        "sidebar_levels": sidebar_levels,
        "user_role":      user_role,
        "active_nav":     "profil",
    })


# ── Auth offline PWA ──────────────────────────────────────────────────────────

@login_required
def offline_credential(request):
    """
    Retourne le verifier PBKDF2 dédié pour l'authentification offline PWA.

    GET — session valide obligatoire (@login_required).

    Retourne au client JS (auth-offline.js) les données à stocker dans
    IndexedDB pour la vérification locale sans réseau :
      { username, verifier, offline_salt, iterations, expires_at }

    Sécurité :
    - Le verifier retourné est distinct du hash Django (sel propre).
    - Il ne permet PAS de se connecter côté serveur.
    - Si expiré (> 30 jours sans connexion en ligne) → 410 Gone.
    """
    from economat.infrastructure.models import OfflineCredentialModel

    try:
        cred = OfflineCredentialModel.objects.get(user=request.user)
        if cred.expires_at < timezone.now():
            cred.delete()
            return JsonResponse({"error": "credential_expired"}, status=410)

        return JsonResponse({
            "username":     request.user.username,
            "verifier":     cred.verifier,
            "offline_salt": cred.offline_salt,
            "iterations":   cred.iterations,
            "expires_at":   cred.expires_at.isoformat(),
        })
    except OfflineCredentialModel.DoesNotExist:
        return JsonResponse({"error": "no_credential"}, status=404)


# ── Inscription publique d'une école ──────────────────────────────────────────

def register_school(request):
    """
    Formulaire public d'inscription d'une école.

    GET  → Affiche le stepper (données pays injectées en JSON inline).
    POST → Soumet la demande via RegisterSchoolUseCase (statut PENDING).
    """
    if request.method == "POST":
        form = SchoolRegistrationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            command = RegisterSchoolCommand(
                school_name        = cd["school_name"],
                city               = cd["city"],
                country_code       = cd["country_code"],
                manager_first_name = cd["manager_first_name"],
                manager_last_name  = cd["manager_last_name"],
                manager_email      = cd["manager_email"],
                manager_phone      = cd.get("manager_phone", ""),
                payment_methods    = tuple(cd["payment_methods"]),
                mobile_operator    = cd.get("mobile_operator", ""),
                mobile_number      = cd.get("mobile_number", ""),
                client_uuid        = str(cd["client_uuid"]) if cd.get("client_uuid") else "",
            )
            result = get_register_school_use_case().execute(command)
            if result.success:
                return render(request, "economat/accounts/register_school_done.html", {
                    "page_title": "Demande envoyée",
                    "manager_email": cd["manager_email"],
                    "school_name": cd["school_name"],
                })
            # Erreur métier → réafficher le formulaire avec le message
            return render(request, "economat/accounts/register_school.html", {
                "page_title": "Inscrire votre école",
                "form": form,
                "error": result.error_message,
                "countries": _get_countries_data(),
            })
    else:
        form = SchoolRegistrationForm()

    return render(request, "economat/accounts/register_school.html", {
        "page_title":    "Inscrire votre école",
        "form":          form,
        "countries": _get_countries_data(),
    })


# ── Page « Autres pays » — liste d'attente clients potentiels ─────────────────

def other_countries(request):
    """
    Page publique d'inscription à la liste d'attente pour les pays non encore
    gérés par Sukulu.

    GET  → Affiche le formulaire d'information + saisie d'email.
    POST → Enregistre un PotentialCustomerModel et confirme à l'utilisateur.
    """
    from economat.infrastructure.models import PotentialCustomerModel

    submitted = False
    form = PotentialCustomerForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        PotentialCustomerModel.objects.create(
            email        = cd["email"],
            country_name = cd.get("country_name", ""),
        )
        submitted = True
        form = PotentialCustomerForm()  # remet le formulaire à blanc

    return render(request, "economat/accounts/other_countries.html", {
        "page_title": "Arrivée dans votre pays bientôt",
        "form":       form,
        "submitted":  submitted,
    })


def _get_countries_data():
    """
    Retourne les données pays (opérateurs + provider + indicatif) pour le
    stepper JS, sous forme de dict — jamais de JSON pré-sérialisé passé au
    template : `{{ x }}` échapperait ses guillemets en `&quot;`, illisibles
    par JSON.parse dans un <script> (raw text, pas de décodage d'entités).
    Le template embarque ce dict via le filtre `json_script`, qui gère cet
    échappement correctement.
    """
    from economat.infrastructure.models import CountryModel
    from economat.interface.accounts.forms import country_flag
    data = {}
    for c in CountryModel.objects.filter(is_active=True):
        data[c.code] = {
            "name":             c.name,
            "currency":         c.currency,
            "payment_provider": c.payment_provider or "",
            "mobile_operators": c.mobile_operators or [],
            "dial_code":        c.dial_code or "",
            "flag":             country_flag(c.code),
        }
    return data


