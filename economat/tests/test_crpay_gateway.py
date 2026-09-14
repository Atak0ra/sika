"""
tests/test_crpay_gateway.py
==============================
CRPayGateway : les appels HTTP réels sont mockés (requests_mock) — ce
test vérifie le contrat (auth JWT, paramètres envoyés, interprétation
de la réponse), pas la disponibilité réelle de l'API CRPay.
"""
import pytest
import requests_mock as rm_module

from economat.application.ports.payment_gateway import GatewayPaymentStatus

_BASE = "http://crpay.test"
_LOGIN_URL = f"{_BASE}/api/v0/auth/login/"
_TXN_URL = f"{_BASE}/api/v0/transactions/"
_FAKE_TOKEN = "fake-jwt-access-token"


@pytest.fixture(autouse=True)
def set_crpay_env(monkeypatch):
    monkeypatch.setenv("CRPAY_BASE_URL", _BASE)
    monkeypatch.setenv("CRPAY_EMAIL", "merchant@test.com")
    monkeypatch.setenv("CRPAY_PASSWORD", "secret123")


@pytest.fixture
def gateway():
    from economat.infrastructure.payment.crpay_gateway import CRPayGateway
    return CRPayGateway()


def _login_mock(m):
    """Enregistre le mock de login JWT sur le mocker actif."""
    m.post(_LOGIN_URL, json={"access": _FAKE_TOKEN, "refresh": "fake-refresh"})


def test_initiate_payment_logs_in_and_creates_transaction(gateway):
    import json
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.post(_TXN_URL, json={
            "uuid": "txn-uuid-001", "reference": "TXN-001",
            "status": "PENDING", "amount": 50000,
        })
        result = gateway.initiate_payment(
            phone="+224621234567", operator="Orange Money",
            amount_fcfa=50000, description="Frais scolarité", notify_url="",
        )
        assert result.success
        assert result.transaction_ref == "txn-uuid-001"
        # Vérifier que le Bearer token est présent
        txn_request = m.request_history[1]
        assert "Bearer" in txn_request.headers.get("Authorization", "")
        sent = json.loads(txn_request.body)
        assert sent["amount"] == 50000
        assert sent["customer_phone"] == "+224621234567"


def test_initiate_payment_failure_on_api_error(gateway):
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.post(_TXN_URL, json={"detail": "Forbidden"}, status_code=403)
        result = gateway.initiate_payment(
            phone="+224621234567", operator="MTN", amount_fcfa=25000, description="d", notify_url="",
        )
        assert result.success is False


def test_initiate_payment_failure_on_network_error(gateway):
    import requests
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.post(_TXN_URL, exc=requests.exceptions.ConnectionError)
        result = gateway.initiate_payment(
            phone="+224621234567", operator="MTN", amount_fcfa=25000, description="d", notify_url="",
        )
        assert result.success is False


def test_poll_status_success(gateway):
    ref = "txn-uuid-001"
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.get(f"{_BASE}/api/v0/transactions/{ref}/",
              json={"uuid": ref, "status": "SUCCESS"})
        event = gateway.poll_status(ref)
        assert event.transaction_ref == ref
        assert event.status == GatewayPaymentStatus.ACCEPTED


def test_poll_status_pending(gateway):
    ref = "txn-uuid-002"
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.get(f"{_BASE}/api/v0/transactions/{ref}/",
              json={"uuid": ref, "status": "PENDING"})
        event = gateway.poll_status(ref)
        assert event.status == GatewayPaymentStatus.PENDING


def test_poll_status_failed(gateway):
    ref = "txn-uuid-003"
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.get(f"{_BASE}/api/v0/transactions/{ref}/",
              json={"uuid": ref, "status": "FAILED"})
        event = gateway.poll_status(ref)
        assert event.status == GatewayPaymentStatus.REFUSED


def test_poll_status_network_error_returns_pending(gateway):
    import requests
    ref = "txn-uuid-err"
    with rm_module.Mocker() as m:
        _login_mock(m)
        m.get(f"{_BASE}/api/v0/transactions/{ref}/",
              exc=requests.exceptions.ConnectionError)
        event = gateway.poll_status(ref)
        assert event.status == GatewayPaymentStatus.PENDING


def test_missing_env_raises_error(monkeypatch):
    monkeypatch.delenv("CRPAY_EMAIL", raising=False)
    with pytest.raises(EnvironmentError, match="CRPAY_EMAIL"):
        from economat.infrastructure.payment import crpay_gateway
        import importlib
        importlib.reload(crpay_gateway)
        crpay_gateway.CRPayGateway()
