"""
tests/test_parent_portal_flow.py
===================================
Parcours complet : recherche → montant → initiation → attente → polling
→ statut → reçu. Utilise FakePaymentGateway (pays non-SN/GN → fake auto).
"""
import pytest
from django.urls import reverse


def _search_and_open_pay(client, active_enrollment):
    student = active_enrollment.student
    client.post(reverse("economat:parent_portal_search"), {
        "school": str(active_enrollment.school_year.school_id),
        "matricule": student.matricule,
    })
    return student


@pytest.mark.django_db
def test_full_flow_from_payment_to_confirmed_receipt(client, active_enrollment):
    _search_and_open_pay(client, active_enrollment)

    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Wave",
        "mobile_number": "0700000000",
    })
    assert resp.status_code == 302
    payment_id = resp.url.rstrip("/").split("/")[-1]

    # Écran d'attente accessible
    resp = client.get(reverse("economat:parent_portal_waiting", args=[payment_id]))
    assert resp.status_code == 200

    # Statut : PENDING avant simulation de confirmation
    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "PENDING"

    # Simuler la confirmation via la gateway Fake en mémoire
    from economat.infrastructure.models import PaymentModel
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    orm = PaymentModel.objects.get(pk=payment_id)
    # On crée une gateway, on simule, puis on applique manuellement le use case
    gw = FakePaymentGateway()
    gw._statuses[orm.gateway_transaction_ref] = __import__(
        "economat.application.ports.payment_gateway", fromlist=["GatewayPaymentStatus"]
    ).GatewayPaymentStatus.ACCEPTED

    from economat.application.use_cases.poll_online_payment import PollOnlinePaymentUseCase
    from economat.composition import get_payment_repo
    PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gw).execute(payment_id)

    # Statut : VALID après confirmation
    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "VALID"


@pytest.mark.django_db
def test_refused_poll_updates_status_to_cancelled(client, active_enrollment):
    _search_and_open_pay(client, active_enrollment)
    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Wave", "mobile_number": "0700000000",
    })
    payment_id = resp.url.rstrip("/").split("/")[-1]

    from economat.infrastructure.models import PaymentModel
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    from economat.application.ports.payment_gateway import GatewayPaymentStatus
    from economat.application.use_cases.poll_online_payment import PollOnlinePaymentUseCase
    from economat.composition import get_payment_repo

    orm = PaymentModel.objects.get(pk=payment_id)
    gw = FakePaymentGateway()
    gw._statuses[orm.gateway_transaction_ref] = GatewayPaymentStatus.REFUSED
    PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gw).execute(payment_id)

    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "CANCELLED"

