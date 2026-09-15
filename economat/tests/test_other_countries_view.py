"""
tests/test_other_countries_view.py
=====================================
Tests de la vue publique « Autres pays » (liste d'attente clients potentiels).

Cas couverts :
  - GET  → 200, texte clé présent
  - POST email valide → crée un PotentialCustomerModel
  - POST deux fois le même email → 2 lignes (doublons autorisés)
  - POST email invalide → 0 ligne créée, formulaire réaffiché avec erreur
  - POST sans email → 0 ligne créée
"""
import pytest
from django.test import Client
from django.urls import reverse

from economat.infrastructure.models import PotentialCustomerModel

URL = "economat:other_countries"


# ── GET ───────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_page_returns_200():
    resp = Client().get(reverse(URL))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_get_page_contains_key_text():
    resp = Client().get(reverse(URL))
    body = resp.content.decode()
    assert "Sukulu arrive bientôt dans votre pays" in body
    assert "Me prévenir dès l'ouverture" in body


@pytest.mark.django_db
def test_get_page_contains_link_back_to_register():
    resp = Client().get(reverse(URL))
    body = resp.content.decode()
    assert reverse("economat:register_school") in body


# ── POST valide ───────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_post_valid_email_creates_lead():
    assert PotentialCustomerModel.objects.count() == 0
    resp = Client().post(reverse(URL), {
        "email":        "test@ecole.sn",
        "country_name": "Sénégal",
    })
    assert resp.status_code == 200
    assert PotentialCustomerModel.objects.count() == 1
    lead = PotentialCustomerModel.objects.first()
    assert lead.email == "test@ecole.sn"
    assert lead.country_name == "Sénégal"


@pytest.mark.django_db
def test_post_valid_email_without_country_creates_lead():
    resp = Client().post(reverse(URL), {"email": "anon@test.com"})
    assert resp.status_code == 200
    lead = PotentialCustomerModel.objects.first()
    assert lead.email == "anon@test.com"
    assert lead.country_name == ""


@pytest.mark.django_db
def test_post_shows_confirmation_after_success():
    resp = Client().post(reverse(URL), {"email": "confirm@ecole.ci"})
    body = resp.content.decode()
    assert "C'est noté, merci" in body


# ── Doublons autorisés ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_duplicate_email_creates_two_rows():
    c = Client()
    c.post(reverse(URL), {"email": "dup@ecole.tg"})
    c.post(reverse(URL), {"email": "dup@ecole.tg"})
    assert PotentialCustomerModel.objects.filter(email="dup@ecole.tg").count() == 2


# ── POST invalide ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_post_invalid_email_creates_nothing():
    resp = Client().post(reverse(URL), {
        "email":        "pas-un-email",
        "country_name": "Congo",
    })
    assert resp.status_code == 200
    assert PotentialCustomerModel.objects.count() == 0


@pytest.mark.django_db
def test_post_invalid_email_shows_form_error():
    resp = Client().post(reverse(URL), {"email": "invalid@@"})
    body = resp.content.decode()
    # Le formulaire doit être réaffiché avec l'erreur, sans la confirmation
    assert "C'est noté, merci" not in body


@pytest.mark.django_db
def test_post_empty_email_creates_nothing():
    Client().post(reverse(URL), {"email": ""})
    assert PotentialCustomerModel.objects.count() == 0
