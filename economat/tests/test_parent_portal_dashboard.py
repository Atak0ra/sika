"""
tests/test_parent_portal_dashboard.py — Espace parent (dashboard + historique).
"""
import datetime
import uuid
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
def test_dashboard_requires_session(client, active_enrollment):
    student = active_enrollment.student
    resp = client.get(reverse("economat:parent_portal_dashboard", args=[str(student.id)]))
    assert resp.status_code == 302
    assert resp.url == reverse("economat:parent_portal_search")


@pytest.mark.django_db
def test_dashboard_shows_student_and_school(client, active_enrollment):
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_dashboard", args=[str(student.id)]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert student.first_name in body
    assert active_enrollment.level.name in body
    assert active_enrollment.school_year.school.name in body


@pytest.mark.django_db
def test_dashboard_pay_button_visible_when_balance_positive(client, active_enrollment):
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_dashboard", args=[str(student.id)]))
    assert "Payer maintenant" in resp.content.decode()


@pytest.mark.django_db
def test_dashboard_frais_soldes_when_balance_zero(client, active_enrollment):
    from economat.infrastructure.models import PaymentModel
    PaymentModel.objects.create(
        id=uuid.uuid4(), enrollment=active_enrollment,
        student=active_enrollment.student,
        amount=active_enrollment.level.annual_fee,
        payment_date=datetime.date.today(), method="ESPECES",
        receipt_number="REC-D-0001", recorded_by="test", state="VALID",
    )
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_dashboard", args=[str(student.id)]))
    assert "Tous les frais sold" in resp.content.decode()


@pytest.mark.django_db
def test_dashboard_link_to_history(client, active_enrollment):
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_dashboard", args=[str(student.id)]))
    history_url = reverse("economat:parent_portal_history", args=[str(student.id)])
    assert history_url in resp.content.decode()


@pytest.mark.django_db
def test_history_requires_session(client, active_enrollment):
    student = active_enrollment.student
    resp = client.get(reverse("economat:parent_portal_history", args=[str(student.id)]))
    assert resp.status_code == 302


@pytest.mark.django_db
def test_history_shows_all_payment_states(client, active_enrollment):
    from economat.infrastructure.models import PaymentModel
    PaymentModel.objects.create(
        id=uuid.uuid4(), enrollment=active_enrollment,
        student=active_enrollment.student, amount=50000,
        payment_date=datetime.date.today(), method="ESPECES",
        receipt_number="REC-H-0001", recorded_by="econome",
        state="VALID", channel="GUICHET",
    )
    PaymentModel.objects.create(
        id=uuid.uuid4(), enrollment=active_enrollment,
        student=active_enrollment.student, amount=25000,
        payment_date=datetime.date.today(), method="MOBILE_MONEY",
        receipt_number="REC-H-0002", recorded_by="Portail parent",
        state="PENDING", channel="PORTAIL_PARENT",
        gateway_transaction_ref="FAKE-ref",
    )
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_history", args=[str(student.id)]))
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "50" in body and "25" in body


@pytest.mark.django_db
def test_history_pdf_link_for_portail_valid(client, active_enrollment):
    from economat.infrastructure.models import PaymentModel
    pid = uuid.uuid4()
    PaymentModel.objects.create(
        id=pid, enrollment=active_enrollment,
        student=active_enrollment.student, amount=75000,
        payment_date=datetime.date.today(), method="MOBILE_MONEY",
        receipt_number="REC-H-0003", recorded_by="Portail parent",
        state="VALID", channel="PORTAIL_PARENT",
        gateway_transaction_ref="FAKE-abc",
    )
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_history", args=[str(student.id)]))
    body = resp.content.decode()
    assert reverse("economat:parent_portal_receipt", args=[str(pid)]) in body
    assert "Reçu PDF" in body


@pytest.mark.django_db
def test_history_recu_papier_for_guichet(client, active_enrollment):
    from economat.infrastructure.models import PaymentModel
    PaymentModel.objects.create(
        id=uuid.uuid4(), enrollment=active_enrollment,
        student=active_enrollment.student, amount=40000,
        payment_date=datetime.date.today(), method="ESPECES",
        receipt_number="REC-H-0004", recorded_by="econome",
        state="VALID", channel="GUICHET",
    )
    student = _identify(client, active_enrollment)
    resp = client.get(reverse("economat:parent_portal_history", args=[str(student.id)]))
    body = resp.content.decode()
    assert "Reçu papier" in body
    assert "Reçu PDF" not in body
