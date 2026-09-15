"""
tests/test_landing_backlinks.py — Retour clair vers la landing page depuis
les pages d'entrée (login, inscription école). La page "pays indisponible"
(other_countries.html) a déjà ce lien de longue date, non re-testé ici.
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_login_page_links_back_to_landing(client):
    resp = client.get(reverse("economat:login"))
    body = resp.content.decode()
    landing_url = reverse("economat:landing")
    assert body.count(landing_url) >= 2  # logo cliquable + lien explicite


@pytest.mark.django_db
def test_register_school_page_links_back_to_landing(client):
    resp = client.get(reverse("economat:register_school"))
    body = resp.content.decode()
    landing_url = reverse("economat:landing")
    assert body.count(landing_url) >= 2  # logo cliquable + lien explicite
