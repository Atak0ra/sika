"""
infrastructure/persistence/identity_repositories.py
======================================================
Implémentations concrètes des ports UserRepository et MembershipRepository.
"""

from __future__ import annotations
from typing import List, Optional

from django.contrib.auth.models import User as DjangoUser

from economat.application.ports.identity_repositories import MembershipRepository, UserRepository
from economat.domain.identity.entities import Membership
from economat.domain.identity.value_objects import MembershipId, Role
from economat.domain.school.value_objects import SchoolId
from economat.infrastructure.models import MembershipModel


class DjangoUserRepository(UserRepository):
    """Wrappe django.contrib.auth.User."""

    def create_user(
        self,
        username: str,
        password: str,
        first_name: str = "",
        last_name: str = "",
        email: str = "",
    ) -> str:
        user = DjangoUser.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        return str(user.pk)

    def find_by_username(self, username: str) -> Optional[dict]:
        try:
            u = DjangoUser.objects.get(username=username)
            return {
                "id":         str(u.pk),
                "username":   u.username,
                "first_name": u.first_name,
                "last_name":  u.last_name,
                "email":      u.email,
            }
        except DjangoUser.DoesNotExist:
            return None

    def username_exists(self, username: str) -> bool:
        return DjangoUser.objects.filter(username=username).exists()

    def set_password(self, user_id: str, new_password: str) -> None:
        u = DjangoUser.objects.get(pk=int(user_id))
        u.set_password(new_password)
        u.save(update_fields=["password"])


class DjangoMembershipRepository(MembershipRepository):

    def find_by_id(self, membership_id: MembershipId) -> Optional[Membership]:
        try:
            orm = MembershipModel.objects.select_related("user", "school", "created_by").get(
                pk=membership_id.value
            )
            return _to_domain(orm)
        except MembershipModel.DoesNotExist:
            return None

    def find_by_user_and_school(
        self, user_id: str, school_id: SchoolId
    ) -> Optional[Membership]:
        try:
            orm = MembershipModel.objects.select_related("user", "school").get(
                user_id=int(user_id),
                school_id=school_id.value,
                is_active=True,
            )
            return _to_domain(orm)
        except MembershipModel.DoesNotExist:
            return None

    def find_by_user(self, user_id: str) -> List[Membership]:
        qs = MembershipModel.objects.select_related("user", "school").filter(
            user_id=int(user_id), is_active=True
        )
        return [_to_domain(o) for o in qs]

    def find_by_school(self, school_id: SchoolId) -> List[Membership]:
        qs = MembershipModel.objects.select_related("user", "school").filter(
            school_id=school_id.value
        ).order_by("role", "display_name")
        return [_to_domain(o) for o in qs]

    def save(self, membership: Membership) -> None:
        created_by_id = None
        if membership.created_by:
            try:
                created_by_id = int(membership.created_by)
            except (ValueError, TypeError):
                pass

        MembershipModel.objects.update_or_create(
            pk=membership.id.value,
            defaults={
                "user_id":      int(membership.user_id),
                "school_id":    membership.school_id.value,
                "role":         membership.role.value,
                "display_name": membership.display_name,
                "login":        membership.login,
                "is_active":    membership.is_active,
                "created_by_id": created_by_id,
            },
        )

    def next_id(self) -> MembershipId:
        return MembershipId.generate()

    def count_directors(self, school_id: SchoolId) -> int:
        return MembershipModel.objects.filter(
            school_id=school_id.value, role=Role.DIRECTOR.value, is_active=True
        ).count()


# ── Mapper ────────────────────────────────────────────────────────────────────

def _to_domain(orm: MembershipModel) -> Membership:
    return Membership(
        id=MembershipId(str(orm.id)),
        user_id=str(orm.user_id),
        school_id=SchoolId(str(orm.school_id)),
        role=Role(orm.role),
        display_name=orm.display_name or orm.user.get_full_name() or orm.user.username,
        login=orm.login or orm.user.username,
        is_active=orm.is_active,
        created_by=str(orm.created_by_id) if orm.created_by_id else None,
        joined_at=orm.joined_at,
    )
