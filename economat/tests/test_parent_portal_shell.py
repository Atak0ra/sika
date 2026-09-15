"""
tests/test_parent_portal_shell.py — Shell dédié du portail parent
(_base_parent.html) : identité visuelle distincte du back office staff,
et barre de contexte persistante ("Vous consultez : X · changer d'élève").
"""
import pytest
from django.urls import reverse


def _identify(client, active_enrollment):
    student = active_enrollment.student
    school = active_enrollment.school_year.school
    resp = client.post(reverse("economat:parent_portal_search"), {
        "country": str(school.country_id),
        "school": str(school.id),
        "matricule": student.matricule,
    })
    assert resp.status_code == 302
    return student


@pytest.mark.django_db
def test_search_page_uses_dedicated_shell_not_staff_base(client):
    resp = client.get(reverse("economat:parent_portal_search"))
    body = resp.content.decode()
    assert "Espace Parent" in body
    # Le shell staff embarque le service worker PWA — le portail parent non.
    assert "serviceWorker" not in body


@pytest.mark.django_db
def test_search_page_has_no_context_bar(client):
    resp = client.get(reverse("economat:parent_portal_search"))
    assert 'class="pp-context-bar"' not in resp.content.decode()


@pytest.mark.django_db
def test_dashboard_shows_persistent_context_bar(client, active_enrollment):
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_dashboard", args=[str(student.id)]))
    body = resp.content.decode()
    assert "Vous consultez" in body
    assert student.first_name in body
    assert "Changer d" in body


@pytest.mark.django_db
def test_history_page_shows_persistent_context_bar(client, active_enrollment):
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_history", args=[str(student.id)]))
    assert "Vous consultez" in resp.content.decode()


@pytest.mark.django_db
def test_context_bar_absent_before_any_search(client):
    resp = client.get(reverse("economat:parent_portal_search"))
    assert resp.status_code == 200
    assert "Vous consultez" not in resp.content.decode()
