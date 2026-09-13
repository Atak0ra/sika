import datetime
import pytest

from economat.composition import get_record_payment_use_case


@pytest.fixture
def record_payment_use_case():
    return get_record_payment_use_case()


@pytest.fixture
def active_enrollment(db):
    """Crée école + année active + niveau + classe + élève inscrit, prêt à recevoir un paiement."""
    from economat.infrastructure.models import (
        SchoolModel, SchoolYearModel, LevelModel, ClassModel,
        StudentModel, EnrollmentModel,
    )
    school = SchoolModel.objects.create(name="École Test", city="Lomé", country="Togo")
    year = SchoolYearModel.objects.create(
        school=school, label="2026-2027", status="ACTIVE",
        start_date=datetime.date(2026, 9, 1), end_date=datetime.date(2027, 6, 30),
    )
    level = LevelModel.objects.create(
        school_year=year, name="CM2", annual_fee=150000, payment_mode="UNIQUE",
    )
    klass = ClassModel.objects.create(level=level, name="CM2 A")
    student = StudentModel.objects.create(
        first_name="Awa", last_name="Diallo", school=school, matricule="DIAAWA-7K9XQPR",
    )
    enrollment = EnrollmentModel.objects.create(
        student=student, school_year=year, level=level, klass=klass,
        enrollment_date=datetime.date(2026, 9, 1),
    )
    return enrollment
