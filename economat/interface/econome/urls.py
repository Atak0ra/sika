"""
interface/econome/urls.py — Routes de l'économe.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Accueil = dashboard de collecte
    path("",                        views.collection_dashboard, name="econome_dashboard"),
    # Saisie d'un paiement (GET + POST)
    path("encaisser/",              views.record_payment,       name="record_payment"),
    # Page reçu dédiée (imprimable / PDF)
    path("recus/<str:payment_id>/", views.receipt_view,         name="receipt_view"),
    # Liste des encaissements filtrables
    path("encaissements/",          views.payments_list,        name="econome_payments"),
    # API AJAX recherche élève
    path("api/eleves/",             views.student_search_api,   name="student_search_api"),
    # Endpoint de synchronisation batch (paiements offline)
    path("sync/",                   views.sync_payments,        name="sync_payments"),
]
