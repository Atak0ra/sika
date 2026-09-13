"""
interface/parent_portal/urls.py — Portail de paiement parent, sans authentification.

Pas de `app_name` ici, par cohérence avec les autres sous-apps du projet
(`econome/urls.py`, `director/urls.py`, `accounts/urls.py`) : aucune ne
déclare son propre `app_name` — toutes les routes vivent à plat sous le
seul namespace `economat` déclaré dans `economat/urls.py`. Chaque route
porte donc un nom préfixé `parent_portal_...` pour éviter toute collision
avec les routes des autres sous-apps (même convention que
`econome_dashboard`, `econome_payments`, etc.).
"""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.search, name="parent_portal_search"),
    path("montant/", views.pay, name="parent_portal_pay"),
    path("attente/<uuid:payment_id>/", views.waiting, name="parent_portal_waiting"),
    path("statut/<uuid:payment_id>/", views.status, name="parent_portal_status"),
    path("webhook/cinetpay/", views.webhook_cinetpay, name="parent_portal_webhook_cinetpay"),
    path("recu/<uuid:payment_id>/", views.receipt, name="parent_portal_receipt"),
    path("historique/", views.history, name="parent_portal_history"),
]
