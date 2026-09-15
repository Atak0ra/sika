"""
tests/test_field_format_markup.py — Câblage HTML du formatage de saisie
partagé (economat/static/economat/js/field-format.js).

Le JS lui-même n'est pas testable en pytest ; ces tests vérifient que
chaque champ montant a bien sa paire display (data-amount-for) + hidden
(name= réel), et que le script est chargé sur chaque surface.
"""
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.infrastructure.models import MembershipModel


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
def test_student_detail_amount_field_has_display_and_hidden_pair(client, active_enrollment):
    user = _create_user("dir_fmt")
    _create_membership(user, active_enrollment.school_year.school, "DIRECTOR")
    client.login(username="dir_fmt", password="testpass")

    resp = client.get(_detail_url(active_enrollment))
    body = resp.content.decode()
    assert 'data-amount-for="amount_fcfa"' in body
    assert '<input type="hidden" name="amount_fcfa"' in body
    assert 'economat/js/field-format.js' in body


@pytest.mark.django_db
def test_configure_pricing_amount_field_has_display_and_hidden_pair(client, active_enrollment):
    user = _create_user("dir_fmt2")
    school = active_enrollment.school_year.school
    _create_membership(user, school, "DIRECTOR")
    client.login(username="dir_fmt2", password="testpass")

    resp = client.get(reverse(
        "economat:configure_pricing",
        args=[str(school.id), str(active_enrollment.school_year_id)],
    ))
    body = resp.content.decode()
    assert 'data-amount-for="annual_fee_fcfa"' in body
    assert '<input type="hidden" name="annual_fee_fcfa"' in body


@pytest.mark.django_db
def test_econome_payment_modal_amount_field_has_display_and_hidden_pair(client, active_enrollment):
    user = _create_user("eco_fmt")
    school = active_enrollment.school_year.school
    _create_membership(user, school, "ECONOME")
    client.login(username="eco_fmt", password="testpass")

    resp = client.get(reverse("economat:econome_dashboard"))
    body = resp.content.decode()
    assert 'data-amount-for="amount_fcfa"' in body
    assert '<input type="hidden" name="amount_fcfa"' in body


@pytest.mark.django_db
def test_parent_portal_pay_amount_field_has_display_and_hidden_pair(client, active_enrollment):
    student = active_enrollment.student
    school = active_enrollment.school_year.school
    resp = client.post(reverse("economat:parent_portal_search"), {
        "country": str(school.country_id),
        "school": str(school.id),
        "matricule": student.matricule,
    })
    assert resp.status_code == 302

    resp = client.get(reverse("economat:parent_portal_pay_student", args=[str(student.id)]))
    body = resp.content.decode()
    assert 'data-amount-for="amount_fcfa"' in body
    assert '<input type="hidden" name="amount_fcfa"' in body
    assert 'economat/js/field-format.js' in body


@pytest.mark.django_db
def test_register_school_loads_field_format_script(client):
    resp = client.get(reverse("economat:register_school"))
    assert 'economat/js/field-format.js' in resp.content.decode()
