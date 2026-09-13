"""
tests/test_fake_gateway.py
=============================
FakePaymentGateway : permet de développer/tester tout le portail parent
sans dépendre de CinetPay.
"""
import json

from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.application.ports.payment_gateway import GatewayPaymentStatus


def test_initiate_payment_always_succeeds_with_a_transaction_ref():
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment(
        phone="0700000000", operator="Orange Money", amount_fcfa=25000,
        description="Frais scolarité", notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    assert result.success
    assert result.transaction_ref.startswith("FAKE-")


def test_webhook_signature_always_valid_for_the_fake_secret():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-abc", "status": "ACCEPTED"}).encode()
    headers = {"X-Fake-Signature": gateway.SHARED_SECRET}
    assert gateway.verify_webhook_signature(body, headers) is True


def test_webhook_signature_rejected_without_correct_header():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-abc", "status": "ACCEPTED"}).encode()
    assert gateway.verify_webhook_signature(body, headers={}) is False
    assert gateway.verify_webhook_signature(body, headers={"X-Fake-Signature": "wrong"}) is False


def test_parse_webhook_status_accepted():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-abc", "status": "ACCEPTED"}).encode()
    event = gateway.parse_webhook_status(body)
    assert event.transaction_ref == "FAKE-abc"
    assert event.status == GatewayPaymentStatus.ACCEPTED


def test_parse_webhook_status_refused():
    gateway = FakePaymentGateway()
    body = json.dumps({"transaction_ref": "FAKE-xyz", "status": "REFUSED"}).encode()
    event = gateway.parse_webhook_status(body)
    assert event.status == GatewayPaymentStatus.REFUSED


def test_simulate_confirmation_helper_builds_a_matching_webhook_body():
    # Utilitaire de test/démo : simule ce que CinetPay enverrait pour
    # confirmer une transaction — utilisé par les tests d'intégration du
    # parcours complet (Task 9/12) sans dépendre d'un vrai webhook HTTP.
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment("0700000000", "Wave", 5000, "desc", "http://x/")
    body, headers = gateway.simulate_confirmation(result.transaction_ref, accepted=True)
    event = gateway.parse_webhook_status(body)
    assert event.transaction_ref == result.transaction_ref
    assert event.status == GatewayPaymentStatus.ACCEPTED
    assert gateway.verify_webhook_signature(body, headers) is True
