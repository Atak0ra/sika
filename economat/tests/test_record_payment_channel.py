"""
tests/test_record_payment_channel.py
=======================================
Vérifie que RecordPaymentUseCase peut produire un paiement PENDING/
PORTAIL_PARENT (utilisé par le portail parent) sans changer le
comportement par défaut (VALID/GUICHET) des appelants existants.
"""
import datetime
import pytest

from economat.application.dto import RecordPaymentCommand


@pytest.mark.django_db
def test_default_command_produces_valid_guichet_payment(
    record_payment_use_case, active_enrollment,
):
    cmd = RecordPaymentCommand(
        student_id=str(active_enrollment.student_id),
        year_id=str(active_enrollment.school_year_id),
        amount_fcfa=10000,
        payment_date=datetime.date.today(),
        method="ESPECES",
        recorded_by="econome-test",
    )
    result = record_payment_use_case.execute(cmd)
    assert result.success, result.error_message

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=result.payment_id)
    assert orm.state == "VALID"
    assert orm.channel == "GUICHET"
    assert orm.gateway_transaction_ref == ""


@pytest.mark.django_db
def test_initial_state_and_channel_are_applied(
    record_payment_use_case, active_enrollment,
):
    cmd = RecordPaymentCommand(
        student_id=str(active_enrollment.student_id),
        year_id=str(active_enrollment.school_year_id),
        amount_fcfa=10000,
        payment_date=datetime.date.today(),
        method="MOBILE_MONEY",
        recorded_by="Portail parent",
        initial_state="PENDING",
        channel="PORTAIL_PARENT",
        gateway_transaction_ref="cp-txn-abc123",
        mobile_operator="Orange Money",
        mobile_number="0700000000",
    )
    result = record_payment_use_case.execute(cmd)
    assert result.success, result.error_message

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=result.payment_id)
    assert orm.state == "PENDING"
    assert orm.channel == "PORTAIL_PARENT"
    assert orm.gateway_transaction_ref == "cp-txn-abc123"
    assert orm.mobile_operator == "Orange Money"
