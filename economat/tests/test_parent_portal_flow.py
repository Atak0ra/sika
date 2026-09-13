"""
tests/test_parent_portal_flow.py
===================================
Parcours complet : recherche → montant → initiation → attente → webhook
→ statut → reçu. Utilise FakePaymentGateway (PAYMENT_GATEWAY=fake, défaut
de settings_test).
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
    student = _search_and_open_pay(client, active_enrollment)

    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Wave",
        "mobile_number": "0700000000",
    })
    assert resp.status_code == 302
    payment_id = resp.url.rstrip("/").split("/")[-1]

    # Écran d'attente accessible
    resp = client.get(reverse("economat:parent_portal_waiting", args=[payment_id]))
    assert resp.status_code == 200

    # Statut : toujours PENDING avant webhook
    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "PENDING"

    # Simule le webhook CinetPay (via FakePaymentGateway)
    from economat.composition import get_payment_gateway
    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=payment_id)
    gateway = get_payment_gateway()
    body, headers = gateway.simulate_confirmation(orm.gateway_transaction_ref, accepted=True)
    resp = client.post(
        reverse("economat:parent_portal_webhook_cinetpay"),
        data=body, content_type="application/json",
        **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
    )
    assert resp.status_code == 200

    # Statut : VALID après webhook
    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "VALID"


@pytest.mark.django_db
def test_webhook_without_valid_signature_is_rejected(client, active_enrollment):
    student = _search_and_open_pay(client, active_enrollment)
    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Wave",
        "mobile_number": "0700000000",
    })
    payment_id = resp.url.rstrip("/").split("/")[-1]

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=payment_id)

    import json
    body = json.dumps({"transaction_ref": orm.gateway_transaction_ref, "status": "ACCEPTED"}).encode()
    resp = client.post(
        reverse("economat:parent_portal_webhook_cinetpay"),
        data=body, content_type="application/json",
        # Pas de signature — doit être rejeté
    )
    assert resp.status_code == 403

    orm.refresh_from_db()
    assert orm.state == "PENDING"  # inchangé


@pytest.mark.django_db
def test_refused_webhook_updates_status_to_cancelled(client, active_enrollment):
    student = _search_and_open_pay(client, active_enrollment)
    resp = client.post(reverse("economat:parent_portal_pay"), {
        "amount_fcfa": "25000", "mobile_operator": "Wave", "mobile_number": "0700000000",
    })
    payment_id = resp.url.rstrip("/").split("/")[-1]

    from economat.composition import get_payment_gateway
    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=payment_id)
    gateway = get_payment_gateway()
    body, headers = gateway.simulate_confirmation(orm.gateway_transaction_ref, accepted=False)
    client.post(
        reverse("economat:parent_portal_webhook_cinetpay"),
        data=body, content_type="application/json",
        **{f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()},
    )

    resp = client.get(reverse("economat:parent_portal_status", args=[payment_id]))
    assert resp.json()["state"] == "CANCELLED"
