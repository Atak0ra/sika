"""
tests/test_secretary_dashboard.py
=====================================
Tests d'intégration (client Django) — confidentialité dashboard secrétaire.
  - La secrétaire ne peut pas accéder au dashboard financier du directeur.
  - Elle est redirigée vers son propre dashboard.
  - Son dashboard ne contient aucune donnée financière.
  - Le directeur conserve son accès intact.
"""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.infrastructure.models import MembershipModel, SchoolModel


def _create_user(username, password="testpass"):
    return User.objects.create_user(username=username, password=password)


def _create_school(name="École Test"):
    from economat.infrastructure.models import CountryModel
    sn, _ = CountryModel.objects.get_or_create(
        code="SN", defaults={"name": "Sénégal", "currency": "XOF",
                              "payment_provider": "samirpay",
                              "mobile_operators": ["Orange Money", "Wave"], "is_active": True}
    )
    return SchoolModel.objects.create(name=name, country=sn, city="Dakar")


def _create_membership(user, school, role):
    return MembershipModel.objects.create(
        user=user, school=school, role=role,
        display_name=user.username, login=user.username, is_active=True,
    )


@pytest.mark.django_db
class TestSecretaryDashboardAccess:

    def test_secretaire_redirigee_depuis_dashboard_financier(self):
        """Une secrétaire qui accède au dashboard financier est redirigée."""
        client = Client()
        user = _create_user("sec1")
        _create_membership(user, _create_school("Éc1"), "SECRETARY")
        client.login(username="sec1", password="testpass")

        response = client.get(reverse("economat:director_dashboard"))
        assert response.status_code == 302
        assert "secretaire" in response["Location"]

    def test_secretaire_acces_son_dashboard_ok(self):
        """La secrétaire atteint son propre dashboard (HTTP 200)."""
        client = Client()
        user = _create_user("sec2")
        _create_membership(user, _create_school("Éc2"), "SECRETARY")
        client.login(username="sec2", password="testpass")

        response = client.get(reverse("economat:secretary_dashboard"))
        assert response.status_code == 200

    def test_secretaire_dashboard_sans_donnees_financieres(self):
        """Le dashboard secrétaire ne contient aucun terme financier sensible."""
        client = Client()
        user = _create_user("sec3")
        _create_membership(user, _create_school("Éc3"), "SECRETARY")
        client.login(username="sec3", password="testpass")

        response = client.get(reverse("economat:secretary_dashboard"))
        content = response.content.decode()

        for term in ["Taux de recouvrement", "recouvrement", "chart.js", "Chart("]:
            assert term.lower() not in content.lower(), (
                f"Le dashboard secrétaire ne doit pas contenir : {term!r}"
            )

    def test_directeur_acces_dashboard_financier_ok(self):
        """Le directeur accède toujours à son dashboard financier (200, pas de redirection)."""
        client = Client()
        user = _create_user("dir1")
        _create_membership(user, _create_school("Éc4"), "DIRECTOR")
        client.login(username="dir1", password="testpass")

        response = client.get(reverse("economat:director_dashboard"))
        assert response.status_code == 200
        assert "secretaire" not in response.get("Location", "")

    def test_non_connecte_redirige_vers_login(self):
        """Un utilisateur non connecté est redirigé vers le login."""
        client = Client()
        response = client.get(reverse("economat:secretary_dashboard"))
        assert response.status_code == 302
        assert "login" in response["Location"].lower()
