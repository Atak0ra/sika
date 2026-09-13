"""
tests/test_parent_portal_search.py
=====================================
Recherche parent (école + matricule) — aucune authentification, match
exact uniquement, message d'erreur générique.
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_search_page_loads_without_authentication(client):
    resp = client.get(reverse("economat:parent_portal_search"))
    assert resp.status_code == 200
    assert "matricule" in resp.content.decode().lower()


@pytest.mark.django_db
def test_valid_school_and_matricule_redirects_to_payment_screen(client, active_enrollment):
    student = active_enrollment.student
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": student.matricule,
    })
    assert resp.status_code == 302
    assert resp.url == reverse("economat:parent_portal_pay")
    session = client.session
    assert session["parent_portal_student_id"] == str(student.id)


@pytest.mark.django_db
def test_unknown_matricule_shows_generic_error(client, active_enrollment):
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": "INCONNU-0000000",
    })
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


@pytest.mark.django_db
def test_correct_matricule_wrong_school_shows_same_generic_error(client, active_enrollment):
    from economat.infrastructure.models import SchoolModel
    other_school = SchoolModel.objects.create(name="Autre École", city="Cotonou", country="Bénin")
    student = active_enrollment.student
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(other_school.id),
        "matricule": student.matricule,
    })
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


@pytest.mark.django_db
def test_search_does_not_suggest_partial_matches(client, active_enrollment):
    """Aucune autocomplétion : une saisie partielle ne doit renvoyer aucune
    suggestion, seulement l'erreur générique."""
    student = active_enrollment.student
    partial = student.matricule[:6]  # préfixe seulement, pas le matricule complet
    resp = client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": partial,
    })
    assert resp.status_code == 200
    assert student.first_name not in resp.content.decode()
    assert "introuvable" in resp.content.decode().lower()
