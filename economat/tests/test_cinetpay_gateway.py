"""
tests/test_cinetpay_gateway.py
=================================
CinetPayGateway : les appels HTTP réels sont mockés (requests_mock) — ce
test vérifie le contrat (paramètres envoyés, interprétation de la réponse),
pas la disponibilité réelle de l'API CinetPay.
"""
import json
import pytest
import requests_mock

from economat.infrastructure.payment.cinetpay_gateway import CinetPayGateway
from economat.application.ports.payment_gateway import GatewayPaymentStatus


@pytest.fixture
def gateway():
    return CinetPayGateway(api_key="test-key", site_id="123456", secret_key="test-secret")


def test_initiate_payment_sends_expected_fields(gateway):
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment", json={
            "code": "201", "message": "CREATED",
            "data": {"payment_token": "tok_abc", "payment_url": "https://checkout.cinetpay.com/x"},
        })
        result = gateway.initiate_payment(
            phone="0700000000", operator="ORANGE", amount_fcfa=25000,
            description="Frais scolarité", notify_url="https://example.com/webhook/",
        )
        assert result.success
        assert result.transaction_ref  # généré côté nous, envoyé comme transaction_id

        sent = json.loads(m.request_history[0].body)
        assert sent["apikey"] == "test-key"
        assert sent["site_id"] == "123456"
        assert sent["amount"] == 25000
        assert sent["currency"] == "XOF"
        assert sent["customer_phone_number"] == "0700000000"
        assert sent["notify_url"] == "https://example.com/webhook/"
        assert sent["channels"] == "MOBILE_MONEY"


def test_initiate_payment_reports_failure_on_error_code(gateway):
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment", json={
            "code": "600", "message": "INVALID_AMOUNT",
        })
        result = gateway.initiate_payment(
            phone="0700000000", operator="ORANGE", amount_fcfa=25000,
            description="Frais scolarité", notify_url="https://example.com/webhook/",
        )
        assert result.success is False
        assert "INVALID_AMOUNT" in result.error_message


def test_initiate_payment_reports_failure_on_network_error(gateway):
    import requests as requests_lib
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment", exc=requests_lib.exceptions.ConnectionError)
        result = gateway.initiate_payment(
            phone="0700000000", operator="ORANGE", amount_fcfa=25000,
            description="Frais scolarité", notify_url="https://example.com/webhook/",
        )
        assert result.success is False


def test_parse_webhook_status_reverifies_via_check_endpoint(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-123"}).encode()
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment/check", json={
            "code": "00", "data": {"status": "ACCEPTED"},
        })
        event = gateway.parse_webhook_status(body)
        assert event.transaction_ref == "cp-txn-123"
        assert event.status == GatewayPaymentStatus.ACCEPTED


def test_parse_webhook_status_refused(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-456"}).encode()
    with requests_mock.Mocker() as m:
        m.post("https://api-checkout.cinetpay.com/v2/payment/check", json={
            "code": "00", "data": {"status": "REFUSED"},
        })
        event = gateway.parse_webhook_status(body)
        assert event.status == GatewayPaymentStatus.REFUSED


def test_verify_webhook_signature_accepts_known_site_id(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-123", "cpm_site_id": "123456"}).encode()
    assert gateway.verify_webhook_signature(body, headers={}) is True


def test_verify_webhook_signature_rejects_mismatched_site_id(gateway):
    body = json.dumps({"cpm_trans_id": "cp-txn-123", "cpm_site_id": "999999"}).encode()
    assert gateway.verify_webhook_signature(body, headers={}) is False
