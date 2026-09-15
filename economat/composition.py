"""
composition.py — Composition Root (NOUVEAU SCHEMA).
"""
from __future__ import annotations

from economat.infrastructure.persistence.registration_repository import (
    DjangoSchoolRegistrationRepository,
)
from economat.infrastructure.persistence.django_repositories import (
    DjangoEnrollmentRepository,
    DjangoPaymentRepository,
    DjangoSchoolRepository,
    DjangoSchoolYearRepository,
    DjangoStudentRepository,
)
from economat.infrastructure.persistence.identity_repositories import (
    DjangoMembershipRepository,
    DjangoUserRepository,
)

# ─ Helpers internes ────────────────────────────────────────────────────────────────────

def _repos():
    
    return {
        "school":      DjangoSchoolRepository(),
        "year":        DjangoSchoolYearRepository(),
        "student":     DjangoStudentRepository(),
        "enrollment":  DjangoEnrollmentRepository(),
        "payment":     DjangoPaymentRepository(),
        "membership":  DjangoMembershipRepository(),
        "user":        DjangoUserRepository(),
    }


def get_school_year_repo():
    return _repos()["year"]


def get_payment_repo():
    return _repos()["payment"]


# ─ Année scolaire ────────────────────────────────────────────────────────────────────

def get_create_school_year_use_case():
    from economat.application.use_cases.manage_school_year import CreateSchoolYearUseCase
    r = _repos()
    return CreateSchoolYearUseCase(school_repo=r["school"], year_repo=r["year"])

def get_activate_school_year_use_case():
    from economat.application.use_cases.manage_school_year import ActivateSchoolYearUseCase
    r = _repos()
    return ActivateSchoolYearUseCase(school_repo=r["school"], year_repo=r["year"])

def get_close_school_year_use_case():
    from economat.application.use_cases.manage_school_year import CloseSchoolYearUseCase
    r = _repos()
    return CloseSchoolYearUseCase(year_repo=r["year"])

def get_promote_class_use_case():
    from economat.application.use_cases.promote_class import PromoteClassUseCase
    r = _repos()
    return PromoteClassUseCase(year_repo=r["year"], enrollment_repo=r["enrollment"])


# ─ Structure ───────────────────────────────────────────────────────────────────────────

def get_add_level_use_case():
    from economat.application.use_cases.add_level import AddLevelUseCase
    r = _repos()
    return AddLevelUseCase(year_repo=r["year"], membership_repo=r["membership"])

def get_add_class_use_case():
    from economat.application.use_cases.add_class import AddClassUseCase
    r = _repos()
    return AddClassUseCase(year_repo=r["year"], membership_repo=r["membership"])

def get_configure_pricing_use_case():
    from economat.application.use_cases.configure_school_pricing import ConfigureSchoolPricingUseCase
    r = _repos()
    return ConfigureSchoolPricingUseCase(year_repo=r["year"])


# ─ Élèves + Enrollments ───────────────────────────────────────────────────────────────

def get_register_student_use_case():
    from economat.application.use_cases.register_student import RegisterStudentUseCase
    r = _repos()
    return RegisterStudentUseCase(
        student_repo=r["student"], year_repo=r["year"], enrollment_repo=r["enrollment"]
    )


# ─ Paiements ──────────────────────────────────────────────────────────────────────

def get_record_payment_use_case():
    from economat.application.use_cases.record_payment import RecordPaymentUseCase
    r = _repos()
    return RecordPaymentUseCase(
        student_repo=r["student"],
        year_repo=r["year"], enrollment_repo=r["enrollment"],
        payment_repo=r["payment"],
    )


def get_cancel_payment_use_case():
    from economat.application.use_cases.cancel_payment import CancelPaymentUseCase
    r = _repos()
    return CancelPaymentUseCase(
        payment_repo=r["payment"],
        membership_repo=r["membership"],
    )



# ─ Identity ────────────────────────────────────────────────────────────────────────

def get_signup_use_case():
    from economat.application.use_cases.signup_director import SignUpDirectorUseCase
    r = _repos()
    return SignUpDirectorUseCase(user_repo=r["user"])

def get_create_school_use_case():
    from economat.application.use_cases.create_school import CreateSchoolUseCase
    r = _repos()
    return CreateSchoolUseCase(school_repo=r["school"], membership_repo=r["membership"])

def get_create_collaborator_use_case():
    from economat.application.use_cases.create_collaborator import CreateCollaboratorUseCase
    r = _repos()
    return CreateCollaboratorUseCase(user_repo=r["user"], membership_repo=r["membership"])

def get_list_memberships_query():
    from economat.application.use_cases.list_my_memberships import ListMyMembershipsQuery
    r = _repos()
    return ListMyMembershipsQuery(membership_repo=r["membership"], school_repo=r["school"])

def get_membership_query():
    from economat.application.use_cases.list_my_memberships import GetMembershipQuery
    r = _repos()
    return GetMembershipQuery(membership_repo=r["membership"])

def get_financial_dashboard_query():
    from economat.application.use_cases.financial_dashboard import GetFinancialDashboardQuery
    r = _repos()
    return GetFinancialDashboardQuery(
        school_repo=r["school"], year_repo=r["year"],
        student_repo=r["student"], enrollment_repo=r["enrollment"],
        payment_repo=r["payment"],
    )

def get_user_repository():
    from economat.infrastructure.persistence.identity_repositories import DjangoUserRepository
    return DjangoUserRepository()


# ─ Portail de paiement parent ──────────────────────────────────────────────────

def get_payment_gateway(country=None):
    """
    Retourne la passerelle de paiement selon le pays.

    Accepte :
      - un CountryModel ORM (depuis SchoolModel.country)
      - un code ISO string ("SN", "GN"…)
      - None → FakePaymentGateway (dev / tests)

    Le routage est piloté par CountryModel.payment_provider stocké en base :
    ajouter un pays et sa passerelle = créer une entrée dans l'admin Django,
    sans modifier ce code.
    """
    provider = ""

    if country is not None:
        # CountryModel ORM instance
        if hasattr(country, "payment_provider"):
            provider = country.payment_provider or ""
        # Code ISO string
        elif isinstance(country, str) and country:
            from economat.infrastructure.models import CountryModel
            try:
                provider = CountryModel.objects.get(code=country).payment_provider or ""
            except CountryModel.DoesNotExist:
                provider = ""

    if provider == "samirpay":
        from economat.infrastructure.payment.samirpay_gateway import SamirPayGateway
        return SamirPayGateway()
    if provider == "crpay":
        from economat.infrastructure.payment.crpay_gateway import CRPayGateway
        return CRPayGateway()
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    return FakePaymentGateway()


def get_initiate_online_payment_use_case(country: str | None = None):
    from economat.application.use_cases.initiate_online_payment import InitiateOnlinePaymentUseCase
    return InitiateOnlinePaymentUseCase(
        record_payment_use_case=get_record_payment_use_case(),
        gateway=get_payment_gateway(country),
    )


def get_poll_online_payment_use_case(country: str | None = None):
    from economat.application.use_cases.poll_online_payment import PollOnlinePaymentUseCase
    return PollOnlinePaymentUseCase(
        payment_repo=get_payment_repo(),
        gateway=get_payment_gateway(country),
    )


def get_confirm_online_payment_use_case():
    from economat.application.use_cases.confirm_online_payment import ConfirmOnlinePaymentUseCase
    return ConfirmOnlinePaymentUseCase(payment_repo=get_payment_repo())


# ─ Inscription & activation des écoles ────────────────────────────────────────

def get_registration_repo():
    return DjangoSchoolRegistrationRepository()


def get_email_sender():
    """
    Retourne ResendEmailSender si RESEND_API_KEY est défini,
    sinon ConsoleEmailSender (dev / tests — aucun appel réseau).
    """
    from django.conf import settings
    if getattr(settings, "RESEND_API_KEY", "").strip():
        from economat.infrastructure.email.resend_email_sender import ResendEmailSender
        return ResendEmailSender()
    from economat.infrastructure.email.console_email_sender import ConsoleEmailSender
    return ConsoleEmailSender()


def get_register_school_use_case():
    from economat.application.use_cases.register_school import RegisterSchoolUseCase
    return RegisterSchoolUseCase(registration_repo=get_registration_repo())


def get_activate_school_registration_use_case():
    from economat.application.use_cases.activate_school_registration import (
        ActivateSchoolRegistrationUseCase,
    )
    r = _repos()
    return ActivateSchoolRegistrationUseCase(
        registration_repo = get_registration_repo(),
        user_repo         = r["user"],
        create_school_uc  = get_create_school_use_case(),
        email_sender      = get_email_sender(),
    )

