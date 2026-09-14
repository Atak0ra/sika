"""
interface/parent_portal/urls.py — Portail de paiement parent, sans authentification.
"""
from django.urls import path

from . import views

urlpatterns = [
    # Entrée : recherche école + matricule
    path("", views.search, name="parent_portal_search"),

    # Espace parent centralisé (dashboard)
    path("espace/<uuid:student_id>/",              views.portal_dashboard, name="parent_portal_dashboard"),
    path("espace/<uuid:student_id>/historique/",   views.portal_history,   name="parent_portal_history"),
    path("espace/<uuid:student_id>/payer/",        views.pay,              name="parent_portal_pay_student"),

    # Flux paiement (compat session — gardé pour les liens existants)
    path("montant/",                               views.pay,              name="parent_portal_pay"),
    path("attente/<uuid:payment_id>/",             views.waiting,          name="parent_portal_waiting"),
    path("statut/<uuid:payment_id>/",              views.status,           name="parent_portal_status"),
    path("recu/<uuid:payment_id>/",                views.receipt,          name="parent_portal_receipt"),

    # Ancien historique → redirect
    path("historique/",                            views.history,          name="parent_portal_history_legacy"),
]
