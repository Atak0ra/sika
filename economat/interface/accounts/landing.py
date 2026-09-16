from __future__ import annotations
from django.shortcuts import redirect, render


def landing(request):
    if request.user.is_authenticated:
        return redirect("economat:school_selector")

    features = [
        {
            "icon": "wallet", "bg": "#eef2ff", "color": "#4f46e5",
            "title": "Encaissement centralisé",
            "desc": "Scolarité, cantine, transport, sorties, sport… tous les frais au même endroit. L’économe saisit un paiement en 3 clics, reçu numéroté généré automatiquement.",
        },
        {
            "icon": "layers", "bg": "#ecfdf5", "color": "#059669",
            "title": "Frais sur-mesure",
            "desc": "Créez n’importe quelle ligne de frais — Cantine T1, Transport octobre, Sortie zoo — et assignez-la à un niveau ou une classe. Elle apparaît aussitôt chez les parents concernés.",
        },
        {
            "icon": "chart", "bg": "#fff7ed", "color": "#d97706",
            "title": "Pilotage par catégorie",
            "desc": "Taux de recouvrement, recettes par catégorie (scolarité, cantine, sorties…), performance par classe — tout d’un coup d’œil avec des graphiques en temps réel.",
        },
        {
            "icon": "phone", "bg": "#f0fdf4", "color": "#16a34a",
            "title": "Paiement mobile parent",
            "desc": "Le parent voit depuis son téléphone tous ses frais dus, choisit ce qu’il veut payer et règle en Mobile Money. Aucun déplacement, aucune queue.",
        },
        {
            "icon": "shield", "bg": "#f5f3ff", "color": "#7c3aed",
            "title": "Barèmes flexibles",
            "desc": "Paiement unique, 3 tranches (40/30/30 %) ou mensualités sur le nombre de mois de votre choix. Chaque poste de frais a son propre rythme.",
        },
        {
            "icon": "users", "bg": "#f8fafc", "color": "#52556b",
            "title": "Multi-rôles",
            "desc": "Directeur, secrétaire, économe — chacun accède uniquement à son périmètre. La structure par années scolaires isole chaque exercice.",
        },
    ]
    return render(request, "economat/landing.html", {"features": features})
