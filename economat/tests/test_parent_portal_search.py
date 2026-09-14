"""
tests/test_parent_portal_search.py
=====================================
Recherche parent (pays + école + matricule) — désambiguïsation homonymes,
pré-sélection IP, fallback Sénégal, cohérence pays↔école.
"""
import datetime
import pytest
from django.urls import reverse


def _post_search(client, school, matricule, country_pk=None):
    if country_pk is None:
        country_pk = school.country_id
    return client.post(reverse("economat:parent_portal_search"), {
        "country": str(country_pk),
        "school":  str(school.id),
        "matricule": matricule,
    })


@pytest.mark.django_db
def test_search_page_loads_without_authentication(client, togo_country):
    resp = client.get(reverse("economat:parent_portal_search"))
    assert resp.status_code == 200
    assert "matricule" in resp.content.decode().lower()


@pytest.mark.django_db
def test_search_page_shows_country_selector(client, togo_country):
    resp = client.get(reverse("economat:parent_portal_search"))
    body = resp.content.decode()
    assert "Pays" in body
    assert "countrySelect" in body


@pytest.mark.django_db
def test_valid_search_redirects_to_dashboard(client, active_enrollment):
    student = active_enrollment.student
    resp = _post_search(client, active_enrollment.school_year.school,
                        student.matricule)
    assert resp.status_code == 302
    assert resp.url == reverse("economat:parent_portal_dashboard", args=[str(student.id)])
    assert client.session["parent_portal_student_id"] == str(student.id)


@pytest.mark.django_db
def test_unknown_matricule_shows_generic_error(client, active_enrollment):
    resp = _post_search(client, active_enrollment.school_year.school,
                        "INCONNU-0000000")
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


@pytest.mark.django_db
def test_correct_matricule_wrong_school_shows_generic_error(client, active_enrollment):
    from economat.infrastructure.models import SchoolModel
    other = SchoolModel.objects.create(
        name="Autre École", city="Cotonou",
        country=active_enrollment.student.school.country,
    )
    resp = _post_search(client, other, active_enrollment.student.matricule)
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


@pytest.mark.django_db
def test_partial_matricule_shows_generic_error(client, active_enrollment):
    student = active_enrollment.student
    resp = _post_search(client, active_enrollment.school_year.school,
                        student.matricule[:6])
    assert resp.status_code == 200
    assert student.first_name not in resp.content.decode()
    assert "introuvable" in resp.content.decode().lower()


# ── Désambiguïsation par pays ────────────────────────────────────────────────

def _make_school_with_student(school, first_name, matricule_str):
    from economat.infrastructure.models import (
        ClassModel, EnrollmentModel, LevelModel,
        SchoolYearModel, StudentModel,
    )
    year = SchoolYearModel.objects.create(
        school=school, label="2026-2027", status="ACTIVE",
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2027, 6, 30),
    )
    level = LevelModel.objects.create(
        school_year=year, name="CM2", annual_fee=100000, payment_mode="UNIQUE",
    )
    klass = ClassModel.objects.create(level=level, name="CM2 A")
    student = StudentModel.objects.create(
        first_name=first_name, last_name="TEST",
        school=school, matricule=matricule_str,
    )
    EnrollmentModel.objects.create(
        student=student, school_year=year, level=level, klass=klass,
        enrollment_date=datetime.date(2026, 9, 1),
    )
    return student


@pytest.mark.django_db
def test_two_homonym_schools_disambiguated_by_country(client, make_country):
    """Deux écoles homonymes dans deux pays → sélectionner le bon pays isole la bonne école."""
    from economat.infrastructure.models import SchoolModel
    sn = make_country("SN")
    gn = make_country("GN")
    school_sn = SchoolModel.objects.create(name="École Sainte-Marie", city="Dakar", country=sn)
    school_gn = SchoolModel.objects.create(name="École Sainte-Marie", city="Conakry", country=gn)
    student_sn = _make_school_with_student(school_sn, "Aminata", "TEST-SN001")
    student_gn = _make_school_with_student(school_gn, "Fatoumata", "TEST-GN001")

    # Recherche Sénégal → trouve Aminata
    resp = _post_search(client, school_sn, student_sn.matricule)
    assert resp.status_code == 302
    assert client.session["parent_portal_student_id"] == str(student_sn.id)

    # Recherche Guinée → trouve Fatoumata
    resp = _post_search(client, school_gn, student_gn.matricule)
    assert resp.status_code == 302
    assert client.session["parent_portal_student_id"] == str(student_gn.id)


@pytest.mark.django_db
def test_school_from_wrong_country_is_rejected(client, make_country):
    """Pays=Guinée mais école=Sénégal → erreur générique (cohérence pays↔école)."""
    from economat.infrastructure.models import SchoolModel
    sn = make_country("SN")
    gn = make_country("GN")
    school_sn = SchoolModel.objects.create(name="École Test SN", city="Dakar", country=sn)
    student_sn = _make_school_with_student(school_sn, "Mamadou", "MAM-001")
    resp = _post_search(client, school_sn, student_sn.matricule, country_pk=gn.pk)
    assert resp.status_code == 200
    assert "introuvable" in resp.content.decode().lower()


# ── Détection pays par IP ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_vercel_header_gn_preselects_guinee(client, make_country):
    gn = make_country("GN")
    resp = client.get(
        reverse("economat:parent_portal_search"),
        HTTP_X_VERCEL_IP_COUNTRY="GN",
    )
    assert resp.status_code == 200
    assert str(gn.pk) in resp.content.decode()


@pytest.mark.django_db
def test_cloudflare_header_sn_works(client, make_country):
    sn = make_country("SN")
    resp = client.get(
        reverse("economat:parent_portal_search"),
        HTTP_CF_IPCOUNTRY="SN",
    )
    assert resp.status_code == 200
    assert str(sn.pk) in resp.content.decode()


@pytest.mark.django_db
def test_unknown_country_ip_falls_back_to_senegal(client, make_country):
    """IP France (pays non géré) → fallback Sénégal."""
    sn = make_country("SN")
    resp = client.get(
        reverse("economat:parent_portal_search"),
        HTTP_X_VERCEL_IP_COUNTRY="FR",
    )
    assert resp.status_code == 200
    assert str(sn.pk) in resp.content.decode()


@pytest.mark.django_db
def test_no_ip_header_falls_back_to_senegal(client, make_country):
    """Pas de header IP (dev local) → fallback Sénégal."""
    sn = make_country("SN")
    resp = client.get(reverse("economat:parent_portal_search"))
    assert resp.status_code == 200
    assert str(sn.pk) in resp.content.decode()


@pytest.mark.django_db
def test_no_active_countries_does_not_crash(client):
    """Base vide de pays actifs → pas de crash."""
    resp = client.get(reverse("economat:parent_portal_search"))
    assert resp.status_code == 200
