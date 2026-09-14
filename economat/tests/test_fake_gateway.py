"""
tests/test_fake_gateway.py
=============================
FakePaymentGateway : permet de développer/tester tout le portail parent
sans dépendre de Samirpay ou CRPay.
"""
from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.application.ports.payment_gateway import GatewayPaymentStatus


def test_initiate_payment_always_succeeds_with_a_transaction_ref():
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment(
        phone="0700000000", operator="Orange Money", amount_fcfa=25000,
        description="Frais scolarité", notify_url="",
    )
    assert result.success
    assert result.transaction_ref.startswith("FAKE-")


def test_poll_status_returns_pending_by_default():
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment(
        phone="0700000000", operator="Wave", amount_fcfa=5000,
        description="Frais", notify_url="",
    )
    event = gateway.poll_status(result.transaction_ref)
    assert event.transaction_ref == result.transaction_ref
    assert event.status == GatewayPaymentStatus.PENDING


def test_simulate_status_accepted():
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment("0700000000", "Wave", 5000, "desc", "")
    gateway.simulate_status(result.transaction_ref, accepted=True)
    event = gateway.poll_status(result.transaction_ref)
    assert event.status == GatewayPaymentStatus.ACCEPTED


def test_simulate_status_refused():
    gateway = FakePaymentGateway()
    result = gateway.initiate_payment("0700000000", "Wave", 5000, "desc", "")
    gateway.simulate_status(result.transaction_ref, accepted=False)
    event = gateway.poll_status(result.transaction_ref)
    assert event.status == GatewayPaymentStatus.REFUSED


def test_poll_unknown_ref_returns_pending():
    gateway = FakePaymentGateway()
    event = gateway.poll_status("FAKE-does-not-exist")
    assert event.status == GatewayPaymentStatus.PENDING


def test_multiple_transactions_are_independent():
    gateway = FakePaymentGateway()
    r1 = gateway.initiate_payment("0700000001", "Wave", 5000, "d1", "")
    r2 = gateway.initiate_payment("0700000002", "Orange Money", 10000, "d2", "")
    gateway.simulate_status(r1.transaction_ref, accepted=True)
    assert gateway.poll_status(r1.transaction_ref).status == GatewayPaymentStatus.ACCEPTED
    assert gateway.poll_status(r2.transaction_ref).status == GatewayPaymentStatus.PENDING

