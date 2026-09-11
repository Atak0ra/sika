"""
tests/test_cancel_payment.py
==============================
Tests unitaires du CancelPaymentUseCase — sans base de données.
"""
import datetime
import unittest.mock as mock
import pytest

from economat.domain.identity.entities import Membership
from economat.domain.identity.value_objects import MembershipId, Role
from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.value_objects import PaymentId, PaymentMethod
from economat.domain.school.value_objects import SchoolId
from economat.domain.shared.value_objects import Money, Currency
from economat.domain.enrollment.value_objects import EnrollmentId
from economat.domain.student.value_objects import StudentId
from economat.application.dto import CancelPaymentCommand
from economat.application.use_cases.cancel_payment import CancelPaymentUseCase


# ─ Fakes ──────────────────────────────────────────────────────────────────────

class FakePaymentRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, pid): return self._s.get(str(pid))
    def find_by_enrollment(self, eid): return []
    def find_by_school_and_year(self, sid, yid): return {}
    def save(self, p): self._s[str(p.id)] = p
    def next_id(self): return PaymentId.generate()
    def last_receipt_number(self, sid): return 0


class FakeMembershipRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, mid): return self._s.get(mid.value)
    def find_by_user_and_school(self, user_id, school_id):
        return next(
            (m for m in self._s.values()
             if m.user_id == user_id and str(m.school_id) == str(school_id)),
            None,
        )
    def find_by_user(self, uid): return []
    def find_by_school(self, sid): return []
    def save(self, m): self._s[m.id.value] = m
    def next_id(self): return MembershipId.generate()
    def count_directors(self, sid): return 0


# ─ Helpers ────────────────────────────────────────────────────────────────────

def _make_membership(role, school_id, user_id="42", active=True):
    return Membership(
        id=MembershipId.generate(), user_id=user_id, school_id=school_id,
        role=role, display_name="Test", login="test", is_active=active,
    )

def _make_payment():
    return Payment(
        id=PaymentId.generate(),
        enrollment_id=EnrollmentId.generate(),
        student_id=StudentId.generate(),
        amount=Money(50_000, Currency.XOF),
        payment_date=datetime.date(2024, 10, 1),
        method=PaymentMethod.ESPECES,
        receipt_number="REC-TEST-0001",
        recorded_by="eco.test",
        state=PaymentState.VALID,
    )

def _setup(role="DIRECTOR", active=True):
    school_id = SchoolId.generate()
    mr = FakeMembershipRepo()
    pr = FakePaymentRepo()
    m = _make_membership(Role[role], school_id, active=active)
    mr.save(m)
    payment = _make_payment()
    pr.save(payment)
    uc = CancelPaymentUseCase(payment_repo=pr, membership_repo=mr)
    return uc, pr, m, payment, school_id

def _run(uc, cmd):
    """Exécute le use case en neutralisant le check IDOR ORM (pas de DB en test)."""
    with mock.patch("economat.infrastructure.models.PaymentModel.objects") as mgr:
        mgr.filter.return_value.exists.return_value = True
        return uc.execute(cmd)



# ─ Tests domaine Payment.cancel() ─────────────────────────────────────────────

class TestPaymentCancelDomain:
    def test_cancel_change_state(self):
        p = _make_payment()
        p.cancel(reason="Erreur de saisie")
        assert p.state == PaymentState.CANCELLED

    def test_cancel_stores_reason_in_notes(self):
        p = _make_payment()
        p.cancel(reason="Doublon")
        assert "[ANNULÉ]" in p.notes and "Doublon" in p.notes

    def test_cancel_without_reason(self):
        p = _make_payment()
        p.cancel()
        assert p.state == PaymentState.CANCELLED and p.notes == ""

    def test_cancel_preserves_existing_notes(self):
        p = _make_payment()
        p.notes = "Note originale"
        p.cancel(reason="Remboursement")
        assert "Note originale" in p.notes and "Remboursement" in p.notes


# ─ Tests CancelPaymentUseCase ─────────────────────────────────────────────────

class TestCancelPaymentUseCase:

    def test_directeur_annule_ok(self):
        uc, pr, m, payment, school_id = _setup("DIRECTOR")
        r = _run(uc, CancelPaymentCommand(
            payment_id=str(payment.id), school_id=str(school_id),
            director_user_id=m.user_id, reason="Erreur de saisie",
        ))
        assert r.success
        assert r.receipt_number == payment.receipt_number
        saved = pr.find_by_id(payment.id)
        assert saved.state == PaymentState.CANCELLED
        assert "Erreur de saisie" in saved.notes

    def test_secretaire_refuse(self):
        uc, _, m, payment, school_id = _setup("SECRETARY")
        r = _run(uc, CancelPaymentCommand(
            payment_id=str(payment.id), school_id=str(school_id),
            director_user_id=m.user_id, reason="Test",
        ))
        assert not r.success
        assert "directeur" in r.error_message.lower()

    def test_econome_refuse(self):
        uc, _, m, payment, school_id = _setup("ECONOME")
        r = _run(uc, CancelPaymentCommand(
            payment_id=str(payment.id), school_id=str(school_id),
            director_user_id=m.user_id, reason="Test",
        ))
        assert not r.success
        assert "directeur" in r.error_message.lower()

    def test_directeur_inactif_refuse(self):
        uc, _, m, payment, school_id = _setup("DIRECTOR", active=False)
        r = _run(uc, CancelPaymentCommand(
            payment_id=str(payment.id), school_id=str(school_id),
            director_user_id=m.user_id, reason="Test",
        ))
        assert not r.success

    def test_paiement_inexistant(self):
        uc, _, m, _, school_id = _setup("DIRECTOR")
        r = _run(uc, CancelPaymentCommand(
            payment_id=str(PaymentId.generate()),
            school_id=str(school_id),
            director_user_id=m.user_id, reason="Test",
        ))
        assert not r.success
        assert "introuvable" in r.error_message.lower()

    def test_double_annulation_refuse(self):
        uc, _, m, payment, school_id = _setup("DIRECTOR")
        cmd = CancelPaymentCommand(
            payment_id=str(payment.id), school_id=str(school_id),
            director_user_id=m.user_id, reason="Erreur de saisie",
        )
        assert _run(uc, cmd).success
        r2 = _run(uc, cmd)
        assert not r2.success
        assert "déjà annulé" in r2.error_message.lower()

    def test_membre_non_trouve_refuse(self):
        uc, _, _, payment, school_id = _setup("DIRECTOR")
        r = _run(uc, CancelPaymentCommand(
            payment_id=str(payment.id), school_id=str(school_id),
            director_user_id="inconnu", reason="Test",
        ))
        assert not r.success
