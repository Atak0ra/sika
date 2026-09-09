"""
interface/accounts/urls.py — Routes du module accounts.
Auto-inscription publique supprimée : le superuser crée les directeurs via /admin/.
"""
from django.urls import path
from . import views
from .landing import landing

urlpatterns = [
    # ── Landing page (point d'entrée public) ──────────────────────────────
    path("",            landing,                    name="landing"),

    # ── Authentification ──────────────────────────────────────────────────
    path("login/",      views.login_view,           name="login"),
    path("logout/",     views.logout_view,          name="logout"),

    # ── Sélecteur d'école (après connexion) ──────────────────────────────
    path("ecoles/",     views.school_selector,      name="school_selector"),

    # ── Gestion de l'équipe (DIRECTOR) ───────────────────────────────────
    path("<str:school_id>/equipe/",
         views.team,                name="team"),
    path("<str:school_id>/equipe/<str:member_id>/toggle/",
         views.toggle_collaborator, name="toggle_collaborator"),
]
