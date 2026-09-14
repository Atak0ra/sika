"""
tests/test_parent_portal_pay.py
==================================
Écran montant + opérateur — nécessite un élève déjà confirmé en session
(pas d'accès direct sans être passé par la recherche).
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_pay_screen_requires_a_confirmed_student_in_session(client):
    resp = client.get(reverse("economat:parent_portal_pay"))
    assert resp.status_code == 302
    assert resp.url == reverse("economat:parent_portal_search")


@pytest.mark.django_db
def test_pay_screen_shows_student_full_name_after_search(client, active_enrollment):
    student = active_enrollment.student
    school = active_enrollment.school_year.school
    client.post(reverse("economat:parent_portal_search"), {
        "country": str(school.country_id),
        "school": str(school.id),
        "matricule": student.matricule,
    })
    resp = client.get(reverse("economat:parent_portal_pay"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert student.first_name in body
    assert student.last_name.upper() in body.upper()


@pytest.mark.django_db
def test_operator_cards_reflect_school_country(client, active_enrollment):
    # active_enrollment fixture crée une école au Togo (voir conftest.py)
    student = active_enrollment.student
    school = active_enrollment.school_year.school
    client.post(reverse("economat:parent_portal_search"), {
        "country": str(school.country_id),
        "school": str(school.id),
        "matricule": student.matricule,
    })
    resp = client.get(reverse("economat:parent_portal_pay"))
    body = resp.content.decode()
    assert "Flooz" in body or "T-Money" in body  # opérateurs Togo
