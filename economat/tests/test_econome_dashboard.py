"""
tests/test_econome_dashboard.py
==================================
Tests d'intégration — dashboard de collecte de l'économe.
  - Accès au dashboard (200) pour un économe connecté.
  - Présence des indicateurs de collecte.
  - Absence des artefacts BI directeur (Chart.js financier).
  - Saisie accessible sur /encaisser/ (GET 200).
  - Non connecté → redirigé vers login.
"""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.infrastructure.models import MembershipModel, SchoolModel


def _create_user(username, password="testpass"):
    return User.objects.create_user(username=username, password=password)


def _create_school(name="École Économe"):
    return SchoolModel.objects.create(name=name, country="SN", city="Dakar")


def _create_membership(user, school, role):
    return MembershipModel.objects.create(
        user=user, school=school, role=role,
        display_name=user.username, login=user.username, is_active=True,
    )


@pytest.mark.django_db
class TestEconomeDashboard:

    def test_econome_acces_dashboard_ok(self):
        """L'économe atteint son dashboard de collecte (200)."""
        client = Client()
        user = _create_user("eco1")
        _create_membership(user, _create_school(), "ECONOME")
        client.login(username="eco1", password="testpass")

        response = client.get(reverse("economat:econome_dashboard"))
        assert response.status_code == 200

    def test_econome_dashboard_contient_indicateurs_collecte(self):
        """Le dashboard contient le titre et les raccourcis attendus."""
        client = Client()
        user = _create_user("eco2")
        _create_membership(user, _create_school("Éc2"), "ECONOME")
        client.login(username="eco2", password="testpass")

        response = client.get(reverse("economat:econome_dashboard"))
        content = response.content.decode()

        # Ces éléments sont toujours présents (même sans année active)
        for terme in ["Tableau de bord", "Encaisser", "Encaissements"]:
            assert terme in content, (
                f"Attendu dans le dashboard économe : {terme!r}"
            )

    def test_econome_dashboard_sans_chart_bi_directeur(self):
        """Le dashboard économe ne charge pas Chart.js (BI directeur)."""
        client = Client()
        user = _create_user("eco3")
        _create_membership(user, _create_school("Éc3"), "ECONOME")
        client.login(username="eco3", password="testpass")

        response = client.get(reverse("economat:econome_dashboard"))
        content = response.content.decode()

        assert "chart.umd.min.js" not in content.lower()

    def test_econome_acces_saisie_redirige_vers_dashboard(self):
        """/encaisser/ n'est plus une page dédiée (saisie en modale sur le
        dashboard) — un GET redirige simplement vers l'accueil économe."""
        client = Client()
        user = _create_user("eco4")
        _create_membership(user, _create_school("Éc4"), "ECONOME")
        client.login(username="eco4", password="testpass")

        response = client.get(reverse("economat:record_payment"))
        assert response.status_code == 302
        assert response.url == reverse("economat:econome_dashboard")

    def test_econome_dashboard_contient_la_modale_encaissement(self):
        """La modale d'encaissement (formulaire complet) est incluse
        directement sur le dashboard — plus besoin de naviguer ailleurs."""
        client = Client()
        user = _create_user("eco5")
        _create_membership(user, _create_school("Éc5"), "ECONOME")
        client.login(username="eco5", password="testpass")

        response = client.get(reverse("economat:econome_dashboard"))
        content = response.content.decode()
        assert 'id="paymentModal"' in content
        assert 'id="paymentForm"' in content

    def test_non_connecte_redirige_login(self):
        """Non connecté → redirigé vers login."""
        client = Client()
        response = client.get(reverse("economat:econome_dashboard"))
        assert response.status_code == 302
        assert "login" in response["Location"].lower()
