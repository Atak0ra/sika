"""
tests/test_student_detail_payment.py
=======================================
Encaissement depuis la fiche élève (bouton + modale, POST _action=record_payment).
Directeur et secrétaire peuvent tous les deux encaisser depuis cette page.
"""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.infrastructure.models import MembershipModel, PaymentModel


def _create_user(username, password="testpass"):
    return User.objects.create_user(username=username, password=password)


def _create_membership(user, school, role):
    return MembershipModel.objects.create(
        user=user, school=school, role=role,
        display_name=user.username, login=user.username, is_active=True,
    )


def _detail_url(active_enrollment):
    return reverse(
        "economat:student_detail",
        args=[
            str(active_enrollment.school_year.school_id),
            str(active_enrollment.school_year_id),
            str(active_enrollment.id),
        ],
    )


@pytest.mark.django_db
def test_director_can_record_payment_from_student_detail(client, active_enrollment):
    user = _create_user("dir1")
    _create_membership(user, active_enrollment.school_year.school, "DIRECTOR")
    client.login(username="dir1", password="testpass")

    resp = client.post(_detail_url(active_enrollment), {
        "_action": "record_payment",
        "amount_fcfa": "25000",
        "method": "ESPECES",
    })
    assert resp.status_code == 302

    payment = PaymentModel.objects.get(enrollment=active_enrollment)
    assert payment.amount == 25000
    assert payment.state == "VALID"
    assert payment.channel == "GUICHET"
    assert payment.recorded_by == "dir1"


@pytest.mark.django_db
def test_secretary_can_record_payment_from_student_detail(client, active_enrollment):
    user = _create_user("sec1")
    _create_membership(user, active_enrollment.school_year.school, "SECRETARY")
    client.login(username="sec1", password="testpass")

    resp = client.post(_detail_url(active_enrollment), {
        "_action": "record_payment",
        "amount_fcfa": "15000",
        "method": "MOBILE_MONEY",
        "mobile_operator": "Wave",
        "mobile_number": "0700000000",
    })
    assert resp.status_code == 302

    payment = PaymentModel.objects.get(enrollment=active_enrollment)
    assert payment.amount == 15000
    assert payment.mobile_operator == "Wave"


@pytest.mark.django_db
def test_invalid_amount_shows_error_and_creates_nothing(client, active_enrollment):
    user = _create_user("dir2")
    _create_membership(user, active_enrollment.school_year.school, "DIRECTOR")
    client.login(username="dir2", password="testpass")

    resp = client.post(_detail_url(active_enrollment), {
        "_action": "record_payment",
        "amount_fcfa": "0",
        "method": "ESPECES",
    })
    assert resp.status_code == 302
    assert PaymentModel.objects.filter(enrollment=active_enrollment).count() == 0


@pytest.mark.django_db
def test_payment_modal_button_appears_when_balance_remains(client, active_enrollment):
    user = _create_user("dir3")
    _create_membership(user, active_enrollment.school_year.school, "DIRECTOR")
    client.login(username="dir3", password="testpass")

    resp = client.get(_detail_url(active_enrollment))
    assert resp.status_code == 200
    assert "Encaisser" in resp.content.decode()
