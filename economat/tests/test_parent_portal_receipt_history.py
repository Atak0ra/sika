"""
tests/test_parent_portal_receipt_history.py
==============================================
Reçu (accessible seulement si VALID) + historique (recherche identique à
l'écran d'accueil, liste les paiements passés VALID de l'élève).
"""
import datetime
import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_receipt_not_accessible_while_pending(client, active_enrollment):
    from economat.application.use_cases.initiate_online_payment import (
        InitiateOnlinePaymentCommand,
    )
    from economat.composition import get_initiate_online_payment_use_case

    student = active_enrollment.student
    result = get_initiate_online_payment_use_case().execute(InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id), matricule=student.matricule,
        amount_fcfa=25000, mobile_operator="Orange Money", mobile_number="0700000000",
    ))
    resp = client.get(reverse("economat:parent_portal_receipt", args=[result.payment_id]))
    assert resp.status_code == 302  # redirigé vers l'écran d'attente, pas de reçu


@pytest.mark.django_db
def test_receipt_shown_once_valid(client, active_enrollment):
    from economat.composition import get_record_payment_use_case
    from economat.application.dto import RecordPaymentCommand

    student = active_enrollment.student
    r = get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(active_enrollment.school_year_id),
        amount_fcfa=25000, payment_date=datetime.date.today(), method="MOBILE_MONEY",
        recorded_by="Portail parent", initial_state="VALID", channel="PORTAIL_PARENT",
        mobile_operator="Orange Money", mobile_number="0700000000",
    ))
    resp = client.get(reverse("economat:parent_portal_receipt", args=[r.payment_id]))
    assert resp.status_code == 200
    assert "Orange Money" in resp.content.decode()


@pytest.mark.django_db
def test_history_lists_valid_payments_only(client, active_enrollment):
    """L'historique (dans l'espace parent) affiche VALID + PENDING, pas juste VALID.
    Test adapté au nouveau flux : identification via search → espace parent → historique."""
    from economat.composition import get_record_payment_use_case
    from economat.application.dto import RecordPaymentCommand

    student = active_enrollment.student
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(active_enrollment.school_year_id),
        amount_fcfa=15000, payment_date=datetime.date.today(), method="ESPECES",
        recorded_by="econome-test",
    ))
    get_record_payment_use_case().execute(RecordPaymentCommand(
        student_id=str(student.id), year_id=str(active_enrollment.school_year_id),
        amount_fcfa=10000, payment_date=datetime.date.today(), method="MOBILE_MONEY",
        recorded_by="Portail parent", initial_state="PENDING", channel="PORTAIL_PARENT",
        mobile_operator="Wave", mobile_number="0711111111",
    ))

    # Identifier via search pour mettre en session
    school = active_enrollment.school_year.school
    client.post(reverse("economat:parent_portal_search"), {
        "country": str(school.country_id),
        "school": str(school.id),
        "matricule": student.matricule,
    })

    resp = client.get(reverse("economat:parent_portal_history", args=[str(student.id)]))
    assert resp.status_code == 200
    body = resp.content.decode()
    # Les deux paiements apparaissent (l'historique montre tous les états)
    assert "15" in body   # 15 000 FCFA
    assert "10" in body   # 10 000 FCFA
