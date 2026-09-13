"""
composition.py — Composition Root (NOUVEAU SCHEMA).
"""
from __future__ import annotations


# ─ Helpers internes ────────────────────────────────────────────────────────────────────

def _repos():
    from economat.infrastructure.persistence.django_repositories import (
        DjangoEnrollmentRepository, DjangoPaymentRepository,
        DjangoSchoolRepository, DjangoSchoolYearRepository, DjangoStudentRepository,
    )
    from economat.infrastructure.persistence.identity_repositories import (
        DjangoMembershipRepository, DjangoUserRepository,
    )
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


# ─ Chat IA ────────────────────────────────────────────────────────────────────────

def get_ask_director_chat_query():
    from economat.application.use_cases.ask_director_chat import AskDirectorChatQuery
    from economat.infrastructure.ai.groq_llm_adapter import GroqLLMAdapter
    return AskDirectorChatQuery(llm_port=GroqLLMAdapter())


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

def get_payment_gateway():
    from django.conf import settings
    if settings.PAYMENT_GATEWAY == "cinetpay":
        from economat.infrastructure.payment.cinetpay_gateway import CinetPayGateway
        return CinetPayGateway(
            api_key=settings.CINETPAY_API_KEY,
            site_id=settings.CINETPAY_SITE_ID,
            secret_key=settings.CINETPAY_SECRET_KEY,
        )
    from economat.infrastructure.payment.fake_gateway import FakePaymentGateway
    return FakePaymentGateway()
