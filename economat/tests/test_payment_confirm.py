"""
tests/test_payment_confirm.py
================================
Tests de l'état PENDING et de la transition confirm() sur Payment.
"""
import datetime

from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.value_objects import PaymentId, PaymentMethod
from economat.domain.enrollment.value_objects import EnrollmentId
from economat.domain.student.value_objects import StudentId
from economat.domain.shared.value_objects import Money


def _make_pending_payment() -> Payment:
    return Payment(
        id=PaymentId.generate(),
        enrollment_id=EnrollmentId.generate(),
        student_id=StudentId.generate(),
        amount=Money.of_xof(25000),
        payment_date=datetime.date.today(),
        method=PaymentMethod.MOBILE_MONEY,
        receipt_number="REC-TEST-0001",
        recorded_by="Portail parent",
        state=PaymentState.PENDING,
    )


def test_payment_can_be_created_pending():
    payment = _make_pending_payment()
    assert payment.state == PaymentState.PENDING
    assert payment.is_valid() is False


def test_confirm_transitions_pending_to_valid():
    payment = _make_pending_payment()
    payment.confirm()
    assert payment.state == PaymentState.VALID
    assert payment.is_valid() is True


def test_cancel_still_works_from_pending():
    # Un paiement en attente refusé par l'opérateur suit le même chemin
    # domaine qu'une annulation classique.
    payment = _make_pending_payment()
    payment.cancel(reason="Refusé par l'opérateur Mobile Money")
    assert payment.state == PaymentState.CANCELLED
    assert "Refusé par l'opérateur" in payment.notes
