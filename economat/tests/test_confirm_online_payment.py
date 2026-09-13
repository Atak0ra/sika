"""
tests/test_confirm_online_payment.py
=======================================
ConfirmOnlinePaymentUseCase : transition PENDING → VALID/CANCELLED suite
au webhook de la passerelle. Idempotent, ne fait jamais confiance à
l'appelant sans vérification préalable de signature (faite en amont, dans
la vue — ce use case suppose un événement déjà authentifié).
"""
import pytest

from economat.application.ports.payment_gateway import GatewayPaymentStatus, GatewayWebhookEvent
from economat.application.use_cases.confirm_online_payment import ConfirmOnlinePaymentUseCase
from economat.application.use_cases.initiate_online_payment import (
    InitiateOnlinePaymentCommand, InitiateOnlinePaymentUseCase,
)
from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.composition import get_record_payment_use_case, get_payment_repo


def _initiate(active_enrollment) -> str:
    gateway = FakePaymentGateway()
    use_case = InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(), gateway=gateway,
    )
    result = use_case.execute(InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=active_enrollment.student.matricule,
        amount_fcfa=25000, mobile_operator="Wave", mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    ))
    assert result.success
    return result.payment_id


@pytest.mark.django_db
def test_accepted_event_confirms_pending_payment(active_enrollment):
    payment_id = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    transaction_ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    result = use_case.execute(GatewayWebhookEvent(
        transaction_ref=transaction_ref, status=GatewayPaymentStatus.ACCEPTED,
    ))
    assert result.success, result.error_message

    orm = PaymentModel.objects.get(pk=payment_id)
    assert orm.state == "VALID"


@pytest.mark.django_db
def test_refused_event_cancels_pending_payment(active_enrollment):
    payment_id = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    transaction_ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    result = use_case.execute(GatewayWebhookEvent(
        transaction_ref=transaction_ref, status=GatewayPaymentStatus.REFUSED,
    ))
    assert result.success, result.error_message

    orm = PaymentModel.objects.get(pk=payment_id)
    assert orm.state == "CANCELLED"


@pytest.mark.django_db
def test_unknown_transaction_ref_fails_gracefully(active_enrollment):
    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    result = use_case.execute(GatewayWebhookEvent(
        transaction_ref="FAKE-does-not-exist", status=GatewayPaymentStatus.ACCEPTED,
    ))
    assert result.success is False


@pytest.mark.django_db
def test_webhook_received_twice_is_idempotent(active_enrollment):
    payment_id = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    transaction_ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    use_case = ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())
    event = GatewayWebhookEvent(transaction_ref=transaction_ref, status=GatewayPaymentStatus.ACCEPTED)

    first = use_case.execute(event)
    second = use_case.execute(event)  # le fournisseur peut renvoyer le même webhook
    assert first.success and second.success

    orm = PaymentModel.objects.get(pk=payment_id)
    assert orm.state == "VALID"  # toujours VALID, pas d'erreur ni de double-traitement
