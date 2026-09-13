"""
economat/urls.py — Routeur principal de l'app économat.
"""
from django.urls import path, include

app_name = "economat"

urlpatterns = [
    # Authentification + onboarding + équipe
    path("",        include("economat.interface.accounts.urls")),
    # Interface économe (saisie paiements)
    path("econome/",   include("economat.interface.econome.urls")),
    # Interface directeur (dashboard + tarifs + inscriptions + chat IA)
    path("directeur/", include("economat.interface.director.urls")),
    # Portail de paiement parent — sans authentification
    path("payer/", include("economat.interface.parent_portal.urls")),
]
