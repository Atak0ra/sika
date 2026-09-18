"""
tests/test_econome_payments_fee_filter.py
==========================================
Filtre par poste de frais sur la page des encaissements (/econome/encaissements/).

Vérifie :
  1. La colonne « Poste » apparaît dans le tableau pour tous les encaissements.
  2. Le filtre ?fee_item=<id> isole uniquement les paiements du poste choisi.
  3. Le récap (total / nb) suit le filtre.
  4. Le select « Poste de frais » est présent dans la barre de filtres.
"""
import datetime
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.application.dto import RecordPaymentCommand
from economat.composition import get_record_payment_use_case
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, FeeItemModel, LevelModel, MembershipModel,
    SchoolModel, SchoolYearModel, StudentModel,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_country():
    from economat.infrastructure.models import CountryModel
    tg, _ = CountryModel.objects.get_or_create(
        code="TG",
        defaults={
            "name": "Togo", "currency": "XOF", "payment_provider": "",
            "mobile_operators": ["Flooz (Togocom)", "T-Money (Togocom)", "Wave"],
            "is_active": True,
        },
    )
    return tg


def _make_school_and_year(country):
    school = SchoolModel.objects.create(name="École Frais Test", city="Lomé", country=country)
    year = SchoolYearModel.objects.create(
        school=school, label="2026-2027", status="ACTIVE",
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2027, 6, 30),
    )
    return school, year


def _make_level_class_student(school, year, name="CM1", fee=120000):
    level = LevelModel.objects.create(
        school_year=year, name=name, annual_fee=fee, payment_mode="UNIQUE",
    )
    klass = ClassModel.objects.create(level=level, name=f"{name} A")
    student = StudentModel.objects.create(
        first_name="Test", last_name=f"Eleve{name}", school=school,
        matricule=f"MAT{name.replace(' ', '')}-XTEST01",
    )
    EnrollmentModel.objects.create(
        student=student, school_year=year, level=level, klass=klass,
        enrollment_date=datetime.date(2026, 9, 1),
    )
    return level, klass, student


def _make_econome_client(school):
    user = User.objects.create_user(username=f"eco-fee-{school.id}", password="testpass")
    MembershipModel.objects.create(
        user=user, school=school, role="ECONOME",
        display_name=user.username, login=user.username, is_active=True,
    )
    client = Client()
    client.login(username=user.username, password="testpass")
    return client


def _fee_item_scolarite(year, level):
    """Retourne (ou crée) le FeeItem système scolarité pour ce niveau."""
    fi, _ = FeeItemModel.objects.get_or_create(
        school_year=year, category="SCOLARITE", is_system=True, level=level,
        defaults={"name": "Scolarité", "amount": level.annual_fee},
    )
    return fi


def _fee_item_cantine(year):
    """Crée un FeeItem manuel Cantine pour l'année."""
    return FeeItemModel.objects.create(
        school_year=year, name="Cantine T1", category="CANTINE",
        amount=15000, scope_type="ALL", is_system=False, is_active=True,
    )


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_colonne_poste_apparait_dans_le_tableau():
    """La colonne 'Poste' est présente dans l'en-tête du tableau des encaissements."""
    country = _make_country()
    school, year = _make_school_and_year(country)
    level, klass, student = _make_level_class_student(school, year)
    fi_scol = _fee_item_scolarite(year, level)

    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=30000, payment_date=datetime.date.today(),
        method="ESPECES", recorded_by="eco-test",
        fee_item_id=str(fi_scol.id),
    ))

    client = _make_econome_client(school)
    resp = client.get(reverse("economat:econome_payments"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Poste" in body
    assert "Scolarité" in body


@pytest.mark.django_db
def test_filtre_poste_isole_les_paiements_cantine():
    """?fee_item=<id_cantine> n'affiche que les paiements cantine."""
    country = _make_country()
    school, year = _make_school_and_year(country)
    level, klass, student = _make_level_class_student(school, year)
    fi_scol    = _fee_item_scolarite(year, level)
    fi_cantine = _fee_item_cantine(year)
    today = datetime.date.today()

    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=40000, payment_date=today,
        method="ESPECES", recorded_by="eco-test",
        fee_item_id=str(fi_scol.id),
    ))
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=15000, payment_date=today,
        method="ESPECES", recorded_by="eco-test",
        fee_item_id=str(fi_cantine.id),
    ))

    client = _make_econome_client(school)
    url = reverse("economat:econome_payments") + f"?fee_item={fi_cantine.id}"
    resp = client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Cantine T1" in body
    assert "Aucun encaissement" not in body
    assert "selected" in body  # l'option est marquée selected dans le filtre


@pytest.mark.django_db
def test_filtre_poste_exclut_autres_categories():
    """Filtrer par cantine n'affiche pas les encaissements scolarité."""
    country = _make_country()
    school, year = _make_school_and_year(country)
    level, klass, student = _make_level_class_student(school, year, name="CP")
    fi_scol    = _fee_item_scolarite(year, level)
    fi_cantine = _fee_item_cantine(year)
    today = datetime.date.today()

    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=50000, payment_date=today,
        method="ESPECES", recorded_by="eco-test",
        fee_item_id=str(fi_scol.id),
    ))

    client = _make_econome_client(school)
    url = reverse("economat:econome_payments") + f"?fee_item={fi_cantine.id}"
    resp = client.get(url)
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Aucun encaissement" in body
    assert "avec ces filtres" in body


@pytest.mark.django_db
def test_recap_total_suit_le_filtre_poste():
    """Le bandeau récap reflète uniquement les paiements du poste filtré."""
    country = _make_country()
    school, year = _make_school_and_year(country)
    level, klass, student = _make_level_class_student(school, year, name="CE1")
    fi_scol    = _fee_item_scolarite(year, level)
    fi_cantine = _fee_item_cantine(year)
    today = datetime.date.today()

    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=60000, payment_date=today,
        method="ESPECES", recorded_by="eco-test",
        fee_item_id=str(fi_scol.id),
    ))
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=15000, payment_date=today,
        method="ESPECES", recorded_by="eco-test",
        fee_item_id=str(fi_cantine.id),
    ))

    client = _make_econome_client(school)
    url = reverse("economat:econome_payments") + f"?fee_item={fi_cantine.id}"
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.context["recap_count"] == 1
    assert resp.context["recap_total"] == 15000


@pytest.mark.django_db
def test_select_poste_de_frais_apparait_dans_la_barre_de_filtres():
    """Le <select> 'Poste de frais' est présent dès qu'il y a des postes actifs."""
    country = _make_country()
    school, year = _make_school_and_year(country)
    level, _, _ = _make_level_class_student(school, year, name="CE2")
    _fee_item_scolarite(year, level)
    _fee_item_cantine(year)

    client = _make_econome_client(school)
    resp = client.get(reverse("economat:econome_payments"))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "Poste de frais" in body
    assert "Tous les postes" in body
    assert "Cantine T1" in body

