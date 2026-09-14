"""
tests/test_country_model.py
==============================
CountryModel : référentiel pays en base.
Vérifie le routage passerelle, les opérateurs Mobile Money, la migration
legacy string → FK, et le fallback.
"""
import pytest
from economat.infrastructure.models import CountryModel, SchoolModel


@pytest.fixture
def all_countries(db):
    """Crée les 5 pays initiaux comme le ferait la migration."""
    data = [
        ("SN", "Sénégal",        "XOF", "samirpay", ["Orange Money", "Wave", "Free Money"]),
        ("CI", "Côte d'Ivoire",  "XOF", "",         ["Orange Money", "MTN Mobile Money", "Moov Money", "Wave"]),
        ("TG", "Togo",           "XOF", "",         ["Flooz (Togocom)", "T-Money (Togocom)", "Wave"]),
        ("BJ", "Bénin",          "XOF", "",         ["MTN Mobile Money", "Moov Money"]),
        ("GN", "Guinée Conakry", "XOF", "crpay",    ["Orange Money", "MTN Mobile Money"]),
    ]
    countries = {}
    for code, name, currency, provider, operators in data:
        c, _ = CountryModel.objects.get_or_create(
            code=code,
            defaults={"name": name, "currency": currency,
                      "payment_provider": provider,
                      "mobile_operators": operators, "is_active": True},
        )
        countries[code] = c
    return countries


@pytest.mark.django_db
def test_senegal_routes_to_samirpay(all_countries):
    from economat.composition import get_payment_gateway
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    # SN a payment_provider="samirpay" mais les vars env ne sont pas définies
    # → EnvironmentError attendue si on instancie vraiment, on teste juste le provider
    sn = all_countries["SN"]
    assert sn.payment_provider == "samirpay"


@pytest.mark.django_db
def test_guinee_routes_to_crpay(all_countries):
    gn = all_countries["GN"]
    assert gn.payment_provider == "crpay"


@pytest.mark.django_db
def test_togo_has_no_provider(all_countries):
    tg = all_countries["TG"]
    assert tg.payment_provider == ""


@pytest.mark.django_db
def test_country_without_provider_returns_fake(all_countries):
    from economat.composition import get_payment_gateway
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    tg = all_countries["TG"]
    gw = get_payment_gateway(tg)
    assert isinstance(gw, FakePaymentGateway)


@pytest.mark.django_db
def test_none_country_returns_fake():
    from economat.composition import get_payment_gateway
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    gw = get_payment_gateway(None)
    assert isinstance(gw, FakePaymentGateway)


@pytest.mark.django_db
def test_iso_code_string_routes_correctly(all_countries):
    from economat.composition import get_payment_gateway
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    gw = get_payment_gateway("TG")
    assert isinstance(gw, FakePaymentGateway)


@pytest.mark.django_db
def test_mobile_operators_from_orm_instance(all_countries):
    from economat.domain.payment.value_objects import mobile_operators_for_country
    tg = all_countries["TG"]
    ops = mobile_operators_for_country(tg)
    assert "Flooz (Togocom)" in ops
    assert "Wave" in ops


@pytest.mark.django_db
def test_mobile_operators_from_iso_code(all_countries):
    from economat.domain.payment.value_objects import mobile_operators_for_country
    ops = mobile_operators_for_country("SN")
    assert "Wave" in ops
    assert "Orange Money" in ops


@pytest.mark.django_db
def test_mobile_operators_fallback_for_unknown_code():
    from economat.domain.payment.value_objects import (
        mobile_operators_for_country, DEFAULT_MOBILE_OPERATORS
    )
    ops = mobile_operators_for_country("XX")
    assert ops == DEFAULT_MOBILE_OPERATORS


@pytest.mark.django_db
def test_mobile_operators_none_returns_default():
    from economat.domain.payment.value_objects import (
        mobile_operators_for_country, DEFAULT_MOBILE_OPERATORS
    )
    assert mobile_operators_for_country(None) == DEFAULT_MOBILE_OPERATORS


@pytest.mark.django_db
def test_school_country_fk_str_representation(all_countries):
    tg = all_countries["TG"]
    school = SchoolModel.objects.create(name="Test School", city="Lomé", country=tg)
    school.refresh_from_db()
    assert school.country.code == "TG"
    assert school.country.name == "Togo"
    assert str(school.country) == "Togo (TG)"


@pytest.mark.django_db
def test_inactive_country_not_in_active_queryset(all_countries):
    bj = all_countries["BJ"]
    bj.is_active = False
    bj.save()
    active_codes = list(CountryModel.objects.filter(is_active=True).values_list("code", flat=True))
    assert "BJ" not in active_codes
    assert "SN" in active_codes
    assert "TG" in active_codes


@pytest.mark.django_db
def test_add_new_country_without_code_change(db):
    """Ajouter un pays = créer un CountryModel, pas toucher au code."""
    cg = CountryModel.objects.create(
        code="CG", name="Congo", currency="XAF",
        payment_provider="",
        mobile_operators=["MTN Mobile Money", "Airtel Money"],
        is_active=True,
    )
    assert CountryModel.objects.filter(code="CG").exists()
    assert cg.currency == "XAF"
