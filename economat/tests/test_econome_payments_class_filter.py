"""
tests/test_econome_payments_class_filter.py
===============================================
Clic sur une classe (sidebar) → tous les paiements de cette classe,
pas seulement ceux du jour. Le lien sidebar ne passe que ?class=<id>,
sans date — avant fix, ça retombait sur le filtre "aujourd'hui" par
défaut et masquait tout l'historique.
"""
import datetime
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from economat.application.dto import RecordPaymentCommand
from economat.composition import get_record_payment_use_case
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, MembershipModel,
    SchoolModel, SchoolYearModel, StudentModel,
)


def _create_membership(user, school, role):
    return MembershipModel.objects.create(
        user=user, school=school, role=role,
        display_name=user.username, login=user.username, is_active=True,
    )


@pytest.mark.django_db
def test_clicking_a_class_shows_payments_from_other_days():
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

    # Paiement enregistré il y a une semaine — PAS aujourd'hui.
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(year.id),
        amount_fcfa=25000,
        payment_date=datetime.date.today() - datetime.timedelta(days=7),
        method="ESPECES", recorded_by="econome-test",
    ))

    user = User.objects.create_user(username="eco-cls", password="testpass")
    _create_membership(user, school, "ECONOME")
    client = Client()
    client.login(username="eco-cls", password="testpass")

    # Exactement le lien construit par la sidebar : ?class=<id>, pas de date.
    resp = client.get(reverse("economat:econome_payments") + f"?class={klass.id}")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "DIALLO" in body  # le paiement d'il y a une semaine apparaît
    assert "Aucun encaissement" not in body
    assert "CM2 A" in body  # nom de la classe affiché dans l'en-tête
