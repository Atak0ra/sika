"""
tests/test_domain.py — REFONTE (nouveau schéma SchoolYear + Enrollment).
"""
import datetime, pytest
from economat.domain.shared.errors import CurrencyMismatchError, NegativeAmountError
from economat.domain.shared.value_objects import Currency, Money
from economat.domain.school.entities import Class, Level, School, SchoolYear, SchoolYearStatus
from economat.domain.school.payment_schedule import PaymentMode, PaymentSchedule
from economat.domain.school.value_objects import ClassId, LevelId, SchoolId, SchoolYearId
from economat.domain.student.entities import Student
from economat.domain.student.value_objects import StudentId, StudentName
from economat.domain.enrollment.entities import Enrollment
from economat.domain.enrollment.value_objects import EnrollmentId, EnrollmentStatus
from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.value_objects import PaymentId, PaymentMethod, PaymentStatus
from economat.domain.payment.payment_status import PaymentStatusCalculator

YEAR_START = datetime.date(2024, 10, 1)
TOTAL      = Money.of_xof(150_000)

# ─ Fixtures ──────────────────────────────────────────────────────────────────────────

def make_school():
    sid = SchoolId.generate()
    school = School(id=sid, name="Test", city="Dakar")
    return school

def make_year(school):
    yid = SchoolYearId.generate()
    return SchoolYear(
        id=yid, school_id=school.id, label="2024-2025",
        start_date=YEAR_START, end_date=datetime.date(2025, 7, 31),
        status=SchoolYearStatus.ACTIVE,
    )

def make_level(year):
    lid = LevelId.generate()
    return Level(id=lid, name="CM2", school_year_id=year.id,
                 annual_fee=TOTAL, payment_mode=PaymentMode.TRANCHES)

def make_class(level):
    cid = ClassId.generate()
    return Class(id=cid, name="CM2 A", level_id=level.id)

def make_student(school):
    return Student(
        id=StudentId.generate(),
        name=StudentName(first_name="Awa", last_name="Diallo"),
        school_id=school.id,
    )

def make_enrollment(student, year, level, klass):
    return Enrollment(
        id=EnrollmentId.generate(), student_id=student.id,
        school_id=student.school_id, school_year_id=year.id,
        level_id=level.id, class_id=klass.id,
        enrollment_date=YEAR_START,
    )

def make_payment(enrollment, amount, date):
    return Payment(
        id=PaymentId.generate(), enrollment_id=enrollment.id,
        student_id=enrollment.student_id,
        amount=Money.of_xof(amount), payment_date=date,
        method=PaymentMethod.ESPECES, receipt_number=f"REC-{date}",
        recorded_by="econome", state=PaymentState.VALID,
    )


# ─ Money ─────────────────────────────────────────────────────────────────────────────

class TestMoney:
    def test_creation_valide(self): assert Money(25_000, Currency.XOF).amount == 25_000
    def test_factory(self): assert Money.of_xof(50_000).amount == 50_000
    def test_zero(self): assert Money.zero().is_zero()
    def test_addition(self): assert Money.of_xof(25_000).add(Money.of_xof(10_000)) == Money.of_xof(35_000)
    def test_soustraction(self): assert Money.of_xof(50_000).subtract(Money.of_xof(20_000)) == Money.of_xof(30_000)
    def test_soustraction_negatif(self):
        with pytest.raises(NegativeAmountError): Money.of_xof(10_000).subtract(Money.of_xof(20_000))
    def test_montant_negatif(self):
        with pytest.raises(NegativeAmountError): Money(-1, Currency.XOF)
    def test_mismatch(self):
        with pytest.raises(CurrencyMismatchError): Money.of_xof(25_000).add(Money(25, Currency.EUR))
    def test_immuable(self):
        m = Money.of_xof(10_000)
        with pytest.raises(AttributeError): m.amount = 99_999  # type: ignore
    def test_pourcentage(self): assert TOTAL.percentage(40) == Money.of_xof(60_000)


# ─ SchoolYear ────────────────────────────────────────────────────────────────────

class TestSchoolYear:
    def test_activation(self):
        s = make_school(); y = make_year(s)
        y.status = SchoolYearStatus.DRAFT; y.activate()
        assert y.is_active

    def test_cloture(self):
        s = make_school(); y = make_year(s)
        y.close()
        assert y.is_closed

    def test_cloture_draft_impossible(self):
        s = make_school(); y = make_year(s)
        y.status = SchoolYearStatus.DRAFT
        with pytest.raises(Exception): y.close()

    def test_une_seule_active(self):
        from economat.domain.shared.errors import DomainError
        s = make_school()
        y1 = make_year(s); y2 = SchoolYear(
            id=SchoolYearId.generate(), school_id=s.id, label="2025-2026",
            start_date=datetime.date(2025,10,1), end_date=datetime.date(2026,7,31),
            status=SchoolYearStatus.DRAFT,
        )
        s.add_school_year(y1); s.add_school_year(y2)
        with pytest.raises(DomainError):
            s.activate_year(y2.id)  # y1 est déjà active

    def test_add_level_closed_interdit(self):
        from economat.domain.shared.errors import DomainError
        s = make_school(); y = make_year(s); y.close()
        lv = make_level(y); lv.school_year_id = y.id
        with pytest.raises(DomainError): y.add_level(lv)


# ─ PaymentSchedule ─────────────────────────────────────────────────────────────────

class TestPaymentSchedule:
    def test_tranches_somme(self):
        s = PaymentSchedule.for_tranches(TOTAL, YEAR_START)
        assert sum(i.amount.amount for i in s.installments) == TOTAL.amount
    def test_tranches_premiere_40pct(self):
        s = PaymentSchedule.for_tranches(TOTAL, YEAR_START)
        assert s.installments[0].amount == Money.of_xof(60_000)
    def test_mensuel_10_mois(self):
        s = PaymentSchedule.for_mensuel(TOTAL, YEAR_START, nb_months=10)
        assert len(s.installments) == 10
        assert sum(i.amount.amount for i in s.installments) == TOTAL.amount


# ─ PaymentStatusCalculator ────────────────────────────────────────────────────────────

CALC = PaymentStatusCalculator()

class TestPaymentStatusCalculator:
    def _sched(self): return PaymentSchedule.for_tranches(TOTAL, YEAR_START)
    def _enr(self):
        s = make_school(); y = make_year(s); lv = make_level(y)
        return make_enrollment(make_student(s), y, lv, make_class(lv))

    def test_solde(self):
        enr = self._enr(); p = make_payment(enr, 150_000, YEAR_START)
        r = CALC.calculate(self._sched(), [p], as_of=datetime.date(2024,10,2))
        assert r.status == PaymentStatus.SOLDE and r.balance.is_zero()

    def test_non_paye(self):
        r = CALC.calculate(self._sched(), [], as_of=datetime.date(2024,9,1))
        assert r.status == PaymentStatus.NON_PAYE

    def test_en_retard(self):
        r = CALC.calculate(self._sched(), [], as_of=datetime.date(2024,11,15))
        assert r.status == PaymentStatus.EN_RETARD
        assert r.days_late > 0
        assert r.oldest_overdue_date == YEAR_START

    def test_en_cours(self):
        enr = self._enr(); p = make_payment(enr, 60_000, datetime.date(2024,10,5))
        r = CALC.calculate(self._sched(), [p], as_of=datetime.date(2024,11,15))
        assert r.status == PaymentStatus.EN_COURS and r.balance.amount == 90_000

    def test_annule_non_compte(self):
        enr = self._enr(); p = make_payment(enr, 150_000, YEAR_START)
        p.cancel("test"); r = CALC.calculate(self._sched(), [p], as_of=datetime.date(2024,10,2))
        assert r.status == PaymentStatus.EN_RETARD


# ─ Fakes ────────────────────────────────────────────────────────────────────────────

class FakeStudentRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, sid): return self._s.get(str(sid))
    def find_by_school(self, sid): return [s for s in self._s.values() if str(s.school_id)==str(sid)]
    def save(self, s): self._s[str(s.id)] = s
    def next_id(self): return StudentId.generate()
    def exists(self, sid): return str(sid) in self._s

class FakeSchoolRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, sid): return self._s.get(str(sid))
    def save(self, s): self._s[str(s.id)] = s
    def find_all(self): return list(self._s.values())

class FakeYearRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, yid): return self._s.get(str(yid))
    def find_by_school(self, sid): return [y for y in self._s.values() if str(y.school_id)==str(sid)]
    def find_active(self, sid): return next((y for y in self._s.values() if str(y.school_id)==str(sid) and y.is_active), None)
    def save(self, y): self._s[str(y.id)] = y
    def next_id(self): return SchoolYearId.generate()

class FakeEnrollmentRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, eid): return self._s.get(str(eid))
    def find_by_student_and_year(self, sid, yid):
        return next((e for e in self._s.values() if str(e.student_id)==str(sid) and str(e.school_year_id)==str(yid)), None)
    def find_by_year(self, yid): return [e for e in self._s.values() if str(e.school_year_id)==str(yid)]
    def find_active_by_year(self, yid): return [e for e in self._s.values() if str(e.school_year_id)==str(yid) and e.is_active()]
    def find_by_class_and_year(self, cid, yid): return [e for e in self._s.values() if str(e.class_id)==str(cid) and str(e.school_year_id)==str(yid) and e.is_active()]
    def save(self, e): self._s[str(e.id)] = e
    def next_id(self): return EnrollmentId.generate()

class FakePaymentRepo:
    def __init__(self): self._s = {}
    def find_by_id(self, pid): return self._s.get(str(pid))
    def find_by_enrollment(self, eid): return [p for p in self._s.values() if str(p.enrollment_id)==str(eid)]
    def find_by_school_and_year(self, sid, yid): return {}
    def save(self, p): self._s[str(p.id)] = p
    def next_id(self): return PaymentId.generate()
    def last_receipt_number(self, sid): return len(self._s)


# ─ RecordPaymentUseCase ────────────────────────────────────────────────────────────

from economat.application.use_cases.record_payment import RecordPaymentUseCase
from economat.application.dto import RecordPaymentCommand


def _setup_full():
    school = make_school(); year = make_year(school)
    level = make_level(year); klass = make_class(level)
    level.add_class(klass); year.add_level(level)
    school.add_school_year(year)
    student = make_student(school)
    enrollment = make_enrollment(student, year, level, klass)

    sr = FakeStudentRepo(); scr = FakeSchoolRepo()
    yr = FakeYearRepo(); er = FakeEnrollmentRepo(); pr = FakePaymentRepo()
    sr.save(student); scr.save(school); yr.save(year); er.save(enrollment)
    uc = RecordPaymentUseCase(
        student_repo=sr, year_repo=yr,
        enrollment_repo=er, payment_repo=pr,
    )
    return uc, pr, student, year, enrollment


class TestRecordPaymentUseCase:
    def test_paiement_partiel(self):
        uc, repo, student, year, _ = _setup_full()
        r = uc.execute(RecordPaymentCommand(
            student_id=str(student.id), year_id=str(year.id),
            amount_fcfa=60_000, payment_date=datetime.date(2024,10,5),
            method="ESPECES", recorded_by="econome",
        ))
        assert r.success and r.amount_paid == 60_000
        assert r.student_name == "Awa DIALLO"
        assert len(repo._s) == 1

    def test_paiement_solde(self):
        uc, _, student, year, _ = _setup_full()
        r = uc.execute(RecordPaymentCommand(
            student_id=str(student.id), year_id=str(year.id),
            amount_fcfa=150_000, payment_date=datetime.date(2024,10,5),
            method="MOBILE_MONEY", recorded_by="econome",
        ))
        assert r.success and r.payment_status == "SOLDE" and r.new_balance == 0

    def test_montant_zero(self):
        uc, _, student, year, _ = _setup_full()
        r = uc.execute(RecordPaymentCommand(
            student_id=str(student.id), year_id=str(year.id),
            amount_fcfa=0, payment_date=datetime.date(2024,10,5),
            method="ESPECES", recorded_by="econome",
        ))
        assert not r.success

    def test_eleve_inconnu(self):
        uc, _, _, year, _ = _setup_full()
        r = uc.execute(RecordPaymentCommand(
            student_id="id-inexistant", year_id=str(year.id),
            amount_fcfa=25_000, payment_date=datetime.date(2024,10,5),
            method="ESPECES", recorded_by="econome",
        ))
        assert not r.success and "introuvable" in r.error_message.lower()

    def test_annee_cloturee(self):
        uc, _, student, year, _ = _setup_full()
        year.close()
        r = uc.execute(RecordPaymentCommand(
            student_id=str(student.id), year_id=str(year.id),
            amount_fcfa=25_000, payment_date=datetime.date(2024,10,5),
            method="ESPECES", recorded_by="econome",
        ))
        assert not r.success and "clôtur" in r.error_message.lower()
