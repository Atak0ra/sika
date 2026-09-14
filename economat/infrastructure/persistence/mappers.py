"""
infrastructure/persistence/mappers.py
========================================
Mappers ORM → Domaine et Domaine → ORM (Anti-Corruption Layer) — NOUVEAU SCHEMA.
"""
from __future__ import annotations

from economat.domain.enrollment.entities import Enrollment
from economat.domain.enrollment.value_objects import EnrollmentId, EnrollmentStatus
from economat.domain.payment.entities import Payment, PaymentState
from economat.domain.payment.value_objects import PaymentId, PaymentMethod
from economat.domain.school.entities import Class, Level, School, SchoolYear, SchoolYearStatus
from economat.domain.school.payment_schedule import PaymentMode
from economat.domain.school.value_objects import ClassId, LevelId, SchoolId, SchoolYearId
from economat.domain.shared.value_objects import Currency, Money
from economat.domain.student.entities import Student
from economat.domain.student.value_objects import StudentId, StudentName
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, PaymentModel,
    SchoolModel, SchoolYearModel, StudentModel,
)


# ─ School ──────────────────────────────────────────────────────────────────────────

def school_to_domain(orm: SchoolModel) -> School:
    years = [school_year_to_domain(y)
             for y in orm.school_years.prefetch_related("levels__classes").all()]
    # country FK → code ISO string (domaine reste pur)
    country_code = orm.country.code if orm.country else "SN"
    return School(
        id=SchoolId(str(orm.id)), name=orm.name, city=orm.city,
        country=country_code, currency=Currency(orm.currency),
        tolerance_days=orm.tolerance_days, school_years=years,
    )

def school_to_orm(domain: School) -> SchoolModel:
    # Note : country_id (FK) est résolu dans DjangoSchoolRepository.save()
    # pour éviter un import circulaire ici. On retourne un objet sans FK.
    return SchoolModel(
        id=domain.id.value, name=domain.name, city=domain.city,
        currency=domain.currency.value,
        tolerance_days=domain.tolerance_days,
    )


# ─ SchoolYear ───────────────────────────────────────────────────────────────────

def school_year_to_domain(orm: SchoolYearModel) -> SchoolYear:
    levels = [level_to_domain(l) for l in orm.levels.prefetch_related("classes").all()]
    return SchoolYear(
        id=SchoolYearId(str(orm.id)),
        school_id=SchoolId(str(orm.school_id)),
        label=orm.label,
        start_date=orm.start_date,
        end_date=orm.end_date,
        status=SchoolYearStatus(orm.status),
        levels=levels,
    )

def school_year_to_orm(domain: SchoolYear) -> SchoolYearModel:
    return SchoolYearModel(
        id=domain.id.value, school_id=domain.school_id.value,
        label=domain.label, start_date=domain.start_date,
        end_date=domain.end_date, status=domain.status.value,
    )


# ─ Level ───────────────────────────────────────────────────────────────────────────

def level_to_domain(orm: LevelModel) -> Level:
    classes = [class_to_domain(c) for c in orm.classes.all()]
    return Level(
        id=LevelId(str(orm.id)), name=orm.name,
        school_year_id=SchoolYearId(str(orm.school_year_id)),
        annual_fee=Money(orm.annual_fee, Currency.XOF),
        payment_mode=PaymentMode(orm.payment_mode), classes=classes,
    )

def level_to_orm(domain: Level) -> LevelModel:
    return LevelModel(
        id=domain.id.value, school_year_id=domain.school_year_id.value,
        name=domain.name, annual_fee=domain.annual_fee.amount,
        payment_mode=domain.payment_mode.value,
    )


# ─ Class ───────────────────────────────────────────────────────────────────────────

def class_to_domain(orm: ClassModel) -> Class:
    return Class(id=ClassId(str(orm.id)), name=orm.name,
                 level_id=LevelId(str(orm.level_id)), capacity=orm.capacity)

def class_to_orm(domain: Class) -> ClassModel:
    return ClassModel(id=domain.id.value, level_id=domain.level_id.value,
                      name=domain.name, capacity=domain.capacity)


# ─ Student ─────────────────────────────────────────────────────────────────────────

def student_to_domain(orm: StudentModel) -> Student:
    return Student(
        id=StudentId(str(orm.id)),
        name=StudentName(first_name=orm.first_name, last_name=orm.last_name),
        school_id=SchoolId(str(orm.school_id)),
        date_of_birth=orm.date_of_birth, notes=orm.notes or "",
    )

def student_to_orm(domain: Student) -> StudentModel:
    return StudentModel(
        id=domain.id.value, first_name=domain.name.first_name,
        last_name=domain.name.last_name, school_id=domain.school_id.value,
        date_of_birth=domain.date_of_birth, notes=domain.notes,
    )


# ─ Enrollment ────────────────────────────────────────────────────────────────

def enrollment_to_domain(orm: EnrollmentModel) -> Enrollment:
    return Enrollment(
        id=EnrollmentId(str(orm.id)),
        student_id=StudentId(str(orm.student_id)),
        school_id=SchoolId(str(orm.school_year.school_id)),
        school_year_id=SchoolYearId(str(orm.school_year_id)),
        level_id=LevelId(str(orm.level_id)),
        class_id=ClassId(str(orm.klass_id)),
        enrollment_date=orm.enrollment_date,
        status=EnrollmentStatus(orm.status),
        notes=orm.notes or "",
        created_at=orm.created_at,
    )

def enrollment_to_orm(domain: Enrollment) -> EnrollmentModel:
    return EnrollmentModel(
        id=domain.id.value, student_id=domain.student_id.value,
        school_year_id=domain.school_year_id.value,
        level_id=domain.level_id.value, klass_id=domain.class_id.value,
        enrollment_date=domain.enrollment_date,
        status=domain.status.value, notes=domain.notes,
    )


# ─ Payment ────────────────────────────────────────────────────────────────────────

def payment_to_domain(orm: PaymentModel) -> Payment:
    return Payment(
        id=PaymentId(str(orm.id)),
        enrollment_id=EnrollmentId(str(orm.enrollment_id)),
        student_id=StudentId(str(orm.student_id)),
        amount=Money(orm.amount, Currency.XOF),
        payment_date=orm.payment_date, method=PaymentMethod(orm.method),
        receipt_number=orm.receipt_number, recorded_by=orm.recorded_by,
        state=PaymentState(orm.state), notes=orm.notes or "",
        created_at=orm.created_at,
    )

def payment_to_orm(domain: Payment) -> PaymentModel:
    return PaymentModel(
        id=domain.id.value, enrollment_id=domain.enrollment_id.value,
        student_id=domain.student_id.value, amount=domain.amount.amount,
        payment_date=domain.payment_date, method=domain.method.value,
        receipt_number=domain.receipt_number, recorded_by=domain.recorded_by,
        state=domain.state.value, notes=domain.notes,
    )
