from __future__ import annotations
import uuid
from economat.application.dto import AddClassCommand, AddClassResult
from economat.application.ports.repositories import SchoolYearRepository
from economat.application.ports.identity_repositories import MembershipRepository
from economat.domain.school.entities import Class
from economat.domain.school.value_objects import ClassId, LevelId, SchoolId, SchoolYearId
from economat.domain.shared.errors import DomainError, DuplicateEntityError, EntityNotFoundError
from economat.domain.identity.entities import UnauthorizedError


class AddClassUseCase:
    def __init__(self, year_repo: SchoolYearRepository, membership_repo: MembershipRepository):
        self._years       = year_repo
        self._memberships = membership_repo

    def execute(self, cmd: AddClassCommand) -> AddClassResult:
        try:
            return self._execute(cmd)
        except (DomainError, UnauthorizedError) as e:
            return AddClassResult(success=False, error_message=str(e))
        except Exception as e:
            return AddClassResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: AddClassCommand) -> AddClassResult:
        membership = self._memberships.find_by_user_and_school(
            cmd.user_id, SchoolId(cmd.school_id)
        )
        if membership is None:
            raise EntityNotFoundError("Vous n'êtes pas membre de cette école.")
        membership.guard_manage_structure()

        year = self._years.find_by_id(SchoolYearId(cmd.year_id))
        if year is None:
            raise EntityNotFoundError("Année scolaire introuvable.")
        if year.is_closed:
            raise DomainError("Impossible de modifier une année clôturée.")

        level = year.get_level(LevelId(cmd.level_id))

        if not cmd.class_name.strip():
            raise DomainError("Le nom de la classe ne peut pas être vide.")
        if any(c.name.lower() == cmd.class_name.strip().lower() for c in level.classes):
            raise DuplicateEntityError(f"Une classe '{cmd.class_name}' existe déjà.")
        if cmd.capacity < 1:
            raise DomainError("La capacité doit être >= 1.")

        klass = Class(
            id=ClassId(value=str(uuid.uuid4())),
            name=cmd.class_name.strip(),
            level_id=level.id,
            capacity=cmd.capacity,
        )
        level.add_class(klass)
        self._years.save(year)
        return AddClassResult(success=True, class_id=str(klass.id),
                              class_name=klass.name, level_name=level.name)
