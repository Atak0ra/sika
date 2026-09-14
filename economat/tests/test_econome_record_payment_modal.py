"""
tests/test_econome_record_payment_modal.py
==============================================
Encaissement via la modale (dashboard + liste des paiements) — plus de
page dédiée /econome/encaisser/. record_payment est POST-only, redirige
vers le reçu en cas de succès, vers le référent (ou le dashboard) avec un
message d'erreur sinon.
"""
import datetime
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, MembershipModel,
    PaymentModel, SchoolModel, SchoolYearModel, StudentModel,
)


def _create_user(username, password="testpass"):
    return User.objects.create_user(username=username, password=password)


def _create_membership(user, school, role):
    return MembershipModel.objects.create(
        user=user, school=school, role=role,
        display_name=user.username, login=user.username, is_active=True,
    )


@pytest.fixture
def econome_setup(db):
    from economat.infrastructure.models import CountryModel
    tg, _ = CountryModel.objects.get_or_create(
        code="TG", defaults={"name": "Togo", "currency": "XOF", "payment_provider": "",
                              "mobile_operators": ["Flooz (Togocom)", "T-Money (Togocom)", "Wave"],
                              "is_active": True}
    )
    school = SchoolModel.objects.create(name="École Test", city="Lomé", country=tg)
    year = SchoolYearModel.objects.create(
        school=school, label="2026-2027", status="ACTIVE",
        start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2027, 6, 30),
    )
    level = LevelModel.objects.create(
        school_year=year, name="CM2", annual_fee=150000, payment_mode="UNIQUE",
    )
    klass = ClassModel.objects.create(level=level, name="CM2 A")
    student = StudentModel.objects.create(
        first_name="Awa", last_name="Diallo", school=school, matricule="DIAAWA-7K9XQPR",
    )
    EnrollmentModel.objects.create(
        student=student, school_year=year, level=level, klass=klass,
        enrollment_date=datetime.date(2026, 9, 1),
    )
    user = _create_user("eco-modal")
    _create_membership(user, school, "ECONOME")
    return {"school": school, "student": student}


@pytest.mark.django_db
def test_successful_payment_redirects_to_receipt(econome_setup):
    client = Client()
    client.login(username="eco-modal", password="testpass")

    resp = client.post(reverse("economat:record_payment"), {
        "student_id": str(econome_setup["student"].id),
        "amount_fcfa": "25000",
        "payment_date": "2026-09-13",
        "method": "ESPECES",
    })
    assert resp.status_code == 302
    assert "/recus/" in resp.url

    payment = PaymentModel.objects.get(student=econome_setup["student"])
    assert payment.amount == 25000
    assert payment.channel == "GUICHET"


@pytest.mark.django_db
def test_invalid_form_redirects_to_referer_with_message(econome_setup):
    client = Client()
    client.login(username="eco-modal", password="testpass")

    payments_url = reverse("economat:econome_payments")
    referer = f"http://testserver{payments_url}"
    resp = client.post(
        reverse("economat:record_payment"),
        {"student_id": "", "amount_fcfa": "0", "payment_date": "2026-09-13", "method": "ESPECES"},
        HTTP_REFERER=referer,
    )
    assert resp.status_code == 302
    assert resp.url == referer
    assert PaymentModel.objects.count() == 0


@pytest.mark.django_db
def test_invalid_form_without_referer_redirects_to_dashboard(econome_setup):
    client = Client()
    client.login(username="eco-modal", password="testpass")

    resp = client.post(reverse("economat:record_payment"), {
        "student_id": "", "amount_fcfa": "0", "payment_date": "2026-09-13", "method": "ESPECES",
    })
    assert resp.status_code == 302
    assert resp.url == reverse("economat:econome_dashboard")


@pytest.mark.django_db
def test_external_referer_is_not_used_for_redirect(econome_setup):
    """Le référent n'est suivi que s'il pointe vers le même hôte — évite
    une redirection ouverte vers un site externe."""
    client = Client()
    client.login(username="eco-modal", password="testpass")

    resp = client.post(
        reverse("economat:record_payment"),
        {"student_id": "", "amount_fcfa": "0", "payment_date": "2026-09-13", "method": "ESPECES"},
        HTTP_REFERER="http://evil.example.com/phishing/",
    )
    assert resp.status_code == 302
    assert resp.url == reverse("economat:econome_dashboard")
