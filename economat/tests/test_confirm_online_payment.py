"""
tests/test_confirm_online_payment.py
=======================================
PollOnlinePaymentUseCase : transition PENDING → VALID/CANCELLED suite
au polling de la passerelle. Idempotent — si le paiement n'est plus
PENDING, aucune action n'est effectuée.
"""
import pytest

from economat.application.ports.payment_gateway import GatewayPaymentStatus
from economat.application.use_cases.poll_online_payment import PollOnlinePaymentUseCase
from economat.application.use_cases.initiate_online_payment import (
    InitiateOnlinePaymentCommand, InitiateOnlinePaymentUseCase,
)
from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.composition import get_record_payment_use_case, get_payment_repo


def _initiate(active_enrollment) -> tuple[str, FakePaymentGateway]:
    gateway = FakePaymentGateway()
    use_case = InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(), gateway=gateway,
    )
    result = use_case.execute(InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=active_enrollment.student.matricule,
        amount_fcfa=25000, mobile_operator="Wave", mobile_number="0700000000",
    ))
    assert result.success
    return result.payment_id, gateway


@pytest.mark.django_db
def test_accepted_poll_confirms_pending_payment(active_enrollment):
    payment_id, gateway = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    gateway.simulate_status(ref, accepted=True)
    use_case = PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gateway)
    result = use_case.execute(payment_id)
    assert result.success, result.error_message
    assert result.new_state == "VALID"

    assert PaymentModel.objects.get(pk=payment_id).state == "VALID"


@pytest.mark.django_db
def test_refused_poll_cancels_pending_payment(active_enrollment):
    payment_id, gateway = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    gateway.simulate_status(ref, accepted=False)
    use_case = PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gateway)
    result = use_case.execute(payment_id)
    assert result.success, result.error_message
    assert result.new_state == "CANCELLED"

    assert PaymentModel.objects.get(pk=payment_id).state == "CANCELLED"


@pytest.mark.django_db
def test_pending_poll_leaves_payment_pending(active_enrollment):
    payment_id, gateway = _initiate(active_enrollment)
    # Pas de simulate_status → reste PENDING
    use_case = PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gateway)
    result = use_case.execute(payment_id)
    assert result.success
    assert result.new_state == "PENDING"

    from economat.infrastructure.models import PaymentModel
    assert PaymentModel.objects.get(pk=payment_id).state == "PENDING"


@pytest.mark.django_db
def test_unknown_payment_id_fails_gracefully(active_enrollment):
    gateway = FakePaymentGateway()
    use_case = PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gateway)
    import uuid
    result = use_case.execute(str(uuid.uuid4()))
    assert result.success is False


@pytest.mark.django_db
def test_poll_twice_is_idempotent(active_enrollment):
    payment_id, gateway = _initiate(active_enrollment)
    from economat.infrastructure.models import PaymentModel
    ref = PaymentModel.objects.get(pk=payment_id).gateway_transaction_ref

    gateway.simulate_status(ref, accepted=True)
    use_case = PollOnlinePaymentUseCase(payment_repo=get_payment_repo(), gateway=gateway)

    first = use_case.execute(payment_id)
    second = use_case.execute(payment_id)
    assert first.success and second.success
    assert PaymentModel.objects.get(pk=payment_id).state == "VALID"

