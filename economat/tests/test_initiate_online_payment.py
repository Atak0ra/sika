"""
tests/test_initiate_online_payment.py
========================================
InitiateOnlinePaymentUseCase : point d'entrée du paiement en ligne parent.
"""
import pytest

from economat.application.use_cases.initiate_online_payment import (
    InitiateOnlinePaymentCommand,
    InitiateOnlinePaymentUseCase,
)
from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
from economat.composition import get_record_payment_use_case


@pytest.fixture
def use_case():
    return InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(),
        gateway=FakePaymentGateway(),
    )


@pytest.mark.django_db
def test_valid_matricule_creates_a_pending_payment(use_case, active_enrollment):
    student = active_enrollment.student
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=student.matricule,
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success, result.error_message
    assert result.payment_id

    from economat.infrastructure.models import PaymentModel
    orm = PaymentModel.objects.get(pk=result.payment_id)
    assert orm.state == "PENDING"
    assert orm.channel == "PORTAIL_PARENT"
    assert orm.recorded_by == "Portail parent"
    assert orm.gateway_transaction_ref.startswith("FAKE-")


@pytest.mark.django_db
def test_unknown_matricule_fails_with_generic_message(use_case, active_enrollment):
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule="INCONNU-0000000",
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success is False
    # Message générique : ne doit jamais confirmer/infirmer si le matricule
    # existe dans une AUTRE école — juste "introuvable" pour cette école.
    assert "introuvable" in result.error_message.lower()


@pytest.mark.django_db
def test_matricule_from_another_school_fails(use_case, active_enrollment):
    from economat.infrastructure.models import SchoolModel
    other_school = SchoolModel.objects.create(name="Autre École", city="Cotonou", country="Bénin")
    student = active_enrollment.student
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(other_school.id),  # bonne matricule, mauvaise école
        matricule=student.matricule,
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success is False


@pytest.mark.django_db
def test_gateway_failure_does_not_create_a_payment_row(active_enrollment):
    class AlwaysFailingGateway(FakePaymentGateway):
        def initiate_payment(self, *a, **kw):
            from economat.application.ports.payment_gateway import GatewayInitiationResult
            return GatewayInitiationResult(success=False, error_message="Service indisponible")

    use_case = InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(),
        gateway=AlwaysFailingGateway(),
    )
    student = active_enrollment.student
    cmd = InitiateOnlinePaymentCommand(
        school_id=str(active_enrollment.school_year.school_id),
        matricule=student.matricule,
        amount_fcfa=25000,
        mobile_operator="Orange Money",
        mobile_number="0700000000",
        notify_url="http://testserver/payer/webhook/cinetpay/",
    )
    result = use_case.execute(cmd)
    assert result.success is False

    from economat.infrastructure.models import PaymentModel
    assert PaymentModel.objects.count() == 0
