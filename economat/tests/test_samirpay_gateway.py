"""
tests/test_samirpay_gateway.py
================================
SamirPayGateway : les appels HTTP réels sont mockés (requests_mock) — ce
test vérifie le contrat (paramètres envoyés, interprétation de la réponse),
pas la disponibilité réelle de l'API Samirpay.
"""
import os
import pytest
import requests_mock as rm_module

from economat.application.ports.payment_gateway import GatewayPaymentStatus


@pytest.fixture(autouse=True)
def set_samir_env(monkeypatch):
    monkeypatch.setenv("SAMIR_API_BASE_URL", "https://api.samirpay.test")
    monkeypatch.setenv("SAMIR_API_KEY", "test-key")
    monkeypatch.setenv("SAMIR_SECRET_KEY", "test-secret")


@pytest.fixture
def gateway():
    from economat.infrastructure.payment.samirpay_gateway import SamirPayGateway
    return SamirPayGateway()


def test_initiate_payment_sends_correct_fields(gateway):
    import json
    with rm_module.Mocker() as m:
        m.post("https://api.samirpay.test/api/tiers/initPayment",
               json={"success": True, "data": {"id": "ext-ref-123"}})
        result = gateway.initiate_payment(
            phone="0700000000", operator="Orange Money", amount_fcfa=25000,
            description="Frais scolarité", notify_url="",
        )
        assert result.success
        assert result.transaction_ref.startswith("SUKULU-")
        sent = json.loads(m.request_history[0].body)
        assert sent["amount"] == "25000"
        assert sent["telephone"] == "0700000000"
        assert "orderId" in sent


def test_initiate_payment_failure_on_api_error(gateway):
    with rm_module.Mocker() as m:
        m.post("https://api.samirpay.test/api/tiers/initPayment",
               json={"success": False, "message": "Compte désactivé"})
        result = gateway.initiate_payment("0700000000", "Wave", 25000, "desc", "")
        assert result.success is False
        assert "Compte désactivé" in result.error_message


def test_initiate_payment_failure_on_network_error(gateway):
    import requests
    with rm_module.Mocker() as m:
        m.post("https://api.samirpay.test/api/tiers/initPayment",
               exc=requests.exceptions.ConnectionError)
        result = gateway.initiate_payment("0700000000", "Wave", 25000, "desc", "")
        assert result.success is False


def test_poll_status_accepted(gateway):
    ref = "SUKULU-abc123"
    with rm_module.Mocker() as m:
        m.get(f"https://api.samirpay.test/api/tiers/payments/{ref}/status",
              json={"status": "success"})
        event = gateway.poll_status(ref)
        assert event.transaction_ref == ref
        assert event.status == GatewayPaymentStatus.ACCEPTED


def test_poll_status_refused(gateway):
    ref = "SUKULU-xyz456"
    with rm_module.Mocker() as m:
        m.get(f"https://api.samirpay.test/api/tiers/payments/{ref}/status",
              json={"status": "failed"})
        event = gateway.poll_status(ref)
        assert event.status == GatewayPaymentStatus.REFUSED


def test_poll_status_pending(gateway):
    ref = "SUKULU-pending"
    with rm_module.Mocker() as m:
        m.get(f"https://api.samirpay.test/api/tiers/payments/{ref}/status",
              json={"status": "pending"})
        event = gateway.poll_status(ref)
        assert event.status == GatewayPaymentStatus.PENDING


def test_poll_status_network_error_returns_pending(gateway):
    import requests
    ref = "SUKULU-error"
    with rm_module.Mocker() as m:
        m.get(f"https://api.samirpay.test/api/tiers/payments/{ref}/status",
              exc=requests.exceptions.ConnectionError)
        event = gateway.poll_status(ref)
        assert event.status == GatewayPaymentStatus.PENDING


def test_missing_env_raises_error(monkeypatch):
    monkeypatch.delenv("SAMIR_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="SAMIR_API_KEY"):
        from economat.infrastructure.payment import samirpay_gateway
        import importlib
        importlib.reload(samirpay_gateway)
        samirpay_gateway.SamirPayGateway()
