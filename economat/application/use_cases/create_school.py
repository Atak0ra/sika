"""
application/use_cases/create_school.py
========================================
USE CASE : CreateSchoolUseCase
Acteur   : Directeur connecté (étape 2 de l'onboarding)
Action   : Créer une école + se rattacher automatiquement en tant que DIRECTOR

Flux :
  1. Valider le nom + la ville.
  2. Créer l'entité School via SchoolRepository.
  3. Créer automatiquement le Membership(role=DIRECTOR) pour l'utilisateur.
  4. Retourner school_id + membership_id.

Règle : un User peut être DIRECTOR de plusieurs écoles (multi-école).
"""

from __future__ import annotations
import uuid

from economat.application.dto_identity import CreateSchoolCommand, CreateSchoolResult
from economat.application.ports.identity_repositories import MembershipRepository
from economat.application.ports.repositories import SchoolRepository
from economat.domain.identity.entities import Membership
from economat.domain.identity.value_objects import MembershipId, Role
from economat.domain.school.entities import School
from economat.domain.school.value_objects import SchoolId
from economat.domain.shared.errors import DomainError
from economat.domain.shared.value_objects import Currency


class CreateSchoolUseCase:

    def __init__(
        self,
        school_repo: SchoolRepository,
        membership_repo: MembershipRepository,
    ) -> None:
        self._schools     = school_repo
        self._memberships = membership_repo

    def execute(self, command: CreateSchoolCommand) -> CreateSchoolResult:
        try:
            return self._execute(command)
        except DomainError as e:
            return CreateSchoolResult(success=False, error_message=str(e))
        except Exception as e:  # noqa: BLE001
            return CreateSchoolResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, command: CreateSchoolCommand) -> CreateSchoolResult:
        if not command.school_name.strip():
            raise DomainError("Le nom de l'école est obligatoire.")
        if not command.city.strip():
            raise DomainError("La ville est obligatoire.")

        # 1. Créer l'entité School (domaine pur)
        school = School(
            id=SchoolId(value=str(uuid.uuid4())),
            name=command.school_name.strip(),
            city=command.city.strip(),
            country=command.country.strip() or "Sénégal",
            currency=Currency(command.currency or "XOF"),
        )
        self._schools.save(school)

        # 2. Créer le Membership DIRECTOR automatiquement
        membership = Membership(
            id=self._memberships.next_id(),
            user_id=command.director_user_id,
            school_id=school.id,
            role=Role.DIRECTOR,
            display_name="",    # sera rempli depuis le User dans la vue
            login="",           # idem
            is_active=True,
            created_by=command.director_user_id,
        )
        self._memberships.save(membership)

        return CreateSchoolResult(
            success=True,
            school_id=str(school.id),
            school_name=school.name,
            membership_id=str(membership.id),
        )
