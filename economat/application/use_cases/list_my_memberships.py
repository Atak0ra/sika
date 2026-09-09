"""
application/use_cases/list_my_memberships.py
=============================================
USE CASE (Query) : ListMyMembershipsQuery
Acteur : Utilisateur connecté
Action : Lister les écoles auxquelles l'utilisateur appartient

Retourne la liste des Memberships actifs de l'utilisateur, avec les
informations de l'école associée — pour construire le "sélecteur d'école"
après la connexion.
"""

from __future__ import annotations
from typing import List

from economat.application.dto_identity import MembershipInfo, MySchoolsResult
from economat.application.ports.identity_repositories import MembershipRepository
from economat.application.ports.repositories import SchoolRepository


class ListMyMembershipsQuery:

    def __init__(
        self,
        membership_repo: MembershipRepository,
        school_repo: SchoolRepository,
    ) -> None:
        self._memberships = membership_repo
        self._schools     = school_repo

    def execute(self, user_id: str) -> MySchoolsResult:
        try:
            memberships = self._memberships.find_by_user(user_id)
            result = []
            for m in memberships:
                if not m.is_active:
                    continue
                school = self._schools.find_by_id(m.school_id)
                result.append({
                    "membership_id": str(m.id),
                    "school_id":     str(m.school_id),
                    "school_name":   school.name if school else "École inconnue",
                    "school_city":   school.city if school else "",
                    "role":          m.role.value,
                    "role_label":    m.role.label,
                    "role_badge":    m.role.badge_color,
                })
            return MySchoolsResult(success=True, memberships=result)
        except Exception as e:  # noqa: BLE001
            return MySchoolsResult(success=False, error_message=str(e))


class GetMembershipQuery:
    """
    Charge le Membership d'un utilisateur pour une école donnée.
    Utilisé par les décorateurs de sécurité dans les vues.
    Retourne None si l'utilisateur n'est pas membre (→ 403 dans la vue).
    """

    def __init__(self, membership_repo: MembershipRepository) -> None:
        self._memberships = membership_repo

    def execute(self, user_id: str, school_id: str):
        from economat.domain.school.value_objects import SchoolId
        return self._memberships.find_by_user_and_school(
            user_id, SchoolId(school_id)
        )
