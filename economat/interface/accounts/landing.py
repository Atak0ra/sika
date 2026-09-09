from __future__ import annotations
from django.shortcuts import redirect, render


def landing(request):
    if request.user.is_authenticated:
        return redirect("economat:school_selector")

    features = [
        {
            "icon": "wallet", "bg": "#eef2ff", "color": "#4f46e5",
            "title": "Encaissement rapide",
            "desc": "L’économe saisit un paiement en 3 clics. Reçu généré automatiquement, numéroté par école.",
        },
        {
            "icon": "chart", "bg": "#ecfdf5", "color": "#059669",
            "title": "Pilotage financier",
            "desc": "Taux de recouvrement, écarts prévisionnel/réel, performance par classe — tout d’un coup d’œil.",
        },
        {
            "icon": "shield", "bg": "#fff7ed", "color": "#d97706",
            "title": "Barèmes flexibles",
            "desc": "Paiement unique, 3 tranches (40/30/30 %) ou mensualités sur 10 mois. Configurable par niveau.",
        },
        {
            "icon": "ai", "bg": "#fdf4ff", "color": "#9333ea",
            "title": "Chat IA",
            "desc": "Le directeur pose ses questions en français. L’IA interroge les données et répond en chiffres.",
        },
        {
            "icon": "users", "bg": "#f0fdf4", "color": "#16a34a",
            "title": "Multi-rôles",
            "desc": "Directeur, secrétaire, économe — chacun accède uniquement à son périmètre.",
        },
        {
            "icon": "school", "bg": "#f8fafc", "color": "#52556b",
            "title": "Années scolaires",
            "desc": "Structure isolée par année. Passez de 2024-2025 à 2025-2026 en dupliquant la configuration.",
        },
    ]
    return render(request, "economat/landing.html", {"features": features})
