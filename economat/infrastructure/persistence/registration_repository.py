"""
infrastructure/persistence/registration_repository.py
=======================================================
Implémentation concrète de SchoolRegistrationRepository (ORM Django).
"""
from __future__ import annotations

from typing import List, Optional

from django.utils import timezone

from economat.application.ports.registration_repository import SchoolRegistrationRepository
from economat.infrastructure.models import SchoolRegistrationModel


class DjangoSchoolRegistrationRepository(SchoolRegistrationRepository):

    def create(
        self,
        *,
        client_uuid: Optional[str],
        school_name: str,
        city: str,
        country_code: Optional[str],
        manager_first_name: str,
        manager_last_name: str,
        manager_email: str,
        manager_phone: str,
        payment_methods: list,
        mobile_operator: str,
        mobile_number: str,
    ) -> str:
        country = None
        if country_code:
            from economat.infrastructure.models import CountryModel
            try:
                country = CountryModel.objects.get(code=country_code.upper())
            except CountryModel.DoesNotExist:
                pass

        reg = SchoolRegistrationModel.objects.create(
            client_uuid        = client_uuid or None,
            school_name        = school_name,
            city               = city,
            country            = country,
            manager_first_name = manager_first_name,
            manager_last_name  = manager_last_name,
            manager_email      = manager_email.lower().strip(),
            manager_phone      = manager_phone,
            payment_methods    = payment_methods,
            mobile_operator    = mobile_operator,
            mobile_number      = mobile_number,
            status             = SchoolRegistrationModel.STATUS_PENDING,
        )
        return str(reg.id)

    def get(self, registration_id: str) -> Optional[dict]:
        try:
            reg = SchoolRegistrationModel.objects.select_related("country", "created_school", "activated_user").get(pk=registration_id)
            return _to_dict(reg)
        except SchoolRegistrationModel.DoesNotExist:
            return None

    def list_pending(self) -> List[dict]:
        qs = (
            SchoolRegistrationModel.objects
            .select_related("country")
            .filter(status=SchoolRegistrationModel.STATUS_PENDING)
            .order_by("created_at")
        )
        return [_to_dict(r) for r in qs]

    def mark_activated(self, registration_id: str, school_id: str, user_id: str) -> None:
        from economat.infrastructure.models import SchoolModel
        from django.contrib.auth.models import User as DjangoUser

        school = SchoolModel.objects.get(pk=school_id)
        user   = DjangoUser.objects.get(pk=int(user_id))

        SchoolRegistrationModel.objects.filter(pk=registration_id).update(
            status         = SchoolRegistrationModel.STATUS_ACTIVATED,
            created_school = school,
            activated_user = user,
            activated_at   = timezone.now(),
        )

    def find_by_client_uuid(self, client_uuid: str) -> Optional[dict]:
        try:
            reg = SchoolRegistrationModel.objects.select_related("country").get(client_uuid=client_uuid)
            return _to_dict(reg)
        except SchoolRegistrationModel.DoesNotExist:
            return None

    def email_has_pending(self, email: str) -> bool:
        return SchoolRegistrationModel.objects.filter(
            manager_email=email.lower().strip(),
            status=SchoolRegistrationModel.STATUS_PENDING,
        ).exists()


# ── Mapper interne ─────────────────────────────────────────────────────────────

def _to_dict(reg: SchoolRegistrationModel) -> dict:
    country = reg.country
    return {
        "id":                  str(reg.id),
        "client_uuid":         str(reg.client_uuid) if reg.client_uuid else None,
        "school_name":         reg.school_name,
        "city":                reg.city,
        "country_code":        country.code     if country else None,
        "country_name":        country.name     if country else "",
        "currency":            country.currency if country else "XOF",
        "mobile_operators":    country.mobile_operators if country else [],
        "payment_provider":    country.payment_provider if country else "",
        "manager_first_name":  reg.manager_first_name,
        "manager_last_name":   reg.manager_last_name,
        "manager_email":       reg.manager_email,
        "manager_phone":       reg.manager_phone,
        "payment_methods":     reg.payment_methods or [],
        "mobile_operator":     reg.mobile_operator,
        "mobile_number":       reg.mobile_number,
        "status":              reg.status,
        "notes":               reg.notes,
        "created_at":          reg.created_at.isoformat() if reg.created_at else None,
        "activated_at":        reg.activated_at.isoformat() if reg.activated_at else None,
        "created_school_id":   str(reg.created_school_id) if reg.created_school_id else None,
        "activated_user_id":   str(reg.activated_user_id) if reg.activated_user_id else None,
    }
