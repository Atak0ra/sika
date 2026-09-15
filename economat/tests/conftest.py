import datetime
import pytest

from economat.composition import get_record_payment_use_case


@pytest.fixture
def record_payment_use_case():
    return get_record_payment_use_case()


@pytest.fixture
def make_country(db):
    """Fixture factory : crée ou récupère un CountryModel par son code ISO."""
    from economat.infrastructure.models import CountryModel
    _DEFAULTS = {
        "SN": {"name": "Sénégal",        "currency": "XOF", "payment_provider": "samirpay",
               "mobile_operators": ["Orange Money", "Wave", "Free Money"], "dial_code": "+221"},
        "TG": {"name": "Togo",           "currency": "XOF", "payment_provider": "",
               "mobile_operators": ["Flooz (Togocom)", "T-Money (Togocom)", "Wave"], "dial_code": "+228"},
        "BJ": {"name": "Bénin",          "currency": "XOF", "payment_provider": "",
               "mobile_operators": ["MTN Mobile Money", "Moov Money"], "dial_code": "+229"},
        "GN": {"name": "Guinée Conakry", "currency": "XOF", "payment_provider": "crpay",
               "mobile_operators": ["Orange Money", "MTN Mobile Money"], "dial_code": "+224"},
        "CI": {"name": "Côte d'Ivoire",  "currency": "XOF", "payment_provider": "",
               "mobile_operators": ["Orange Money", "MTN Mobile Money", "Moov Money", "Wave"], "dial_code": "+225"},
    }

    def _make(code: str):
        defaults = _DEFAULTS.get(code.upper(), {"name": code, "currency": "XOF",
                                                 "payment_provider": "", "mobile_operators": [],
                                                 "dial_code": ""})
        country, _ = CountryModel.objects.get_or_create(
            code=code.upper(), defaults={**defaults, "is_active": True}
        )
        return country

    return _make


@pytest.fixture
def togo_country(make_country):
    """Pays Togo — utilisé par la fixture active_enrollment."""
    return make_country("TG")


@pytest.fixture
def active_enrollment(togo_country):
    """Crée école + année active + niveau + classe + élève inscrit, prêt à recevoir un paiement."""
    from economat.infrastructure.models import (
        SchoolModel, SchoolYearModel, LevelModel, ClassModel,
        StudentModel, EnrollmentModel,
    )
    school = SchoolModel.objects.create(
        name="École Test", city="Lomé", country=togo_country
    )
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
