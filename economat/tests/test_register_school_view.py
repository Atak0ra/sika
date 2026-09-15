"""
tests/test_register_school_view.py — Vue register_school (GET) : données pays
embarquées correctement pour le stepper JS (opérateurs, indicatif, drapeau).
"""
import json

import pytest
from django.urls import reverse

from economat.interface.accounts.forms import country_flag


def test_country_flag_from_iso_code():
    assert country_flag("SN") == "🇸🇳"
    assert country_flag("tg") == "🇹🇬"


def test_country_flag_invalid_input_returns_empty():
    assert country_flag("") == ""
    assert country_flag("XYZ") == ""
    assert country_flag("1S") == ""


@pytest.mark.django_db
def test_register_school_countries_json_is_valid_and_unescaped(client, make_country):
    make_country("SN")
    make_country("TG")
    resp = client.get(reverse("economat:register_school"))
    body = resp.content.decode()

    # Le payload JSON doit être présent tel quel — jamais échappé en &quot;,
    # sinon JSON.parse plante côté client (bug historique corrigé ici).
    assert "&quot;" not in body
    assert "&#39;" not in body

    # Extrait le contenu du <script type="application/json" id="countries-data">
    marker = 'id="countries-data"'
    start = body.index(marker)
    json_start = body.index(">", start) + 1
    json_end = body.index("</script>", json_start)
    payload = json.loads(body[json_start:json_end])

    assert payload["SN"]["dial_code"] == "+221"
    assert payload["SN"]["flag"] == "🇸🇳"
    assert "Orange Money" in payload["SN"]["mobile_operators"]
    assert payload["TG"]["dial_code"] == "+228"
    assert payload["TG"]["flag"] == "🇹🇬"


@pytest.mark.django_db
def test_register_school_country_select_shows_flag(client, make_country):
    make_country("SN")
    resp = client.get(reverse("economat:register_school"))
    body = resp.content.decode()
    assert "🇸🇳 Sénégal" in body


@pytest.mark.django_db
def test_register_school_manager_phone_has_dial_code_badge(client, make_country):
    make_country("SN")
    resp = client.get(reverse("economat:register_school"))
    body = resp.content.decode()
    assert 'id="manager-dial-code"' in body
    assert 'name="manager_phone"' in body
