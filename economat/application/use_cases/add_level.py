from __future__ import annotations
import uuid
from economat.application.dto import AddLevelCommand, AddLevelResult
from economat.application.ports.repositories import SchoolYearRepository
from economat.application.ports.identity_repositories import MembershipRepository
from economat.domain.school.entities import Level
from economat.domain.school.payment_schedule import PaymentMode
from economat.domain.school.value_objects import LevelId, SchoolId, SchoolYearId
from economat.domain.shared.errors import DomainError, DuplicateEntityError, EntityNotFoundError
from economat.domain.shared.value_objects import Money, Currency
from economat.domain.identity.entities import UnauthorizedError


class AddLevelUseCase:
    def __init__(self, year_repo: SchoolYearRepository, membership_repo: MembershipRepository):
        self._years       = year_repo
        self._memberships = membership_repo

    def execute(self, cmd: AddLevelCommand) -> AddLevelResult:
        try:
            return self._execute(cmd)
        except (DomainError, UnauthorizedError) as e:
            return AddLevelResult(success=False, error_message=str(e))
        except Exception as e:
            return AddLevelResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, cmd: AddLevelCommand) -> AddLevelResult:
        year_id = SchoolYearId(cmd.year_id)

        membership = self._memberships.find_by_user_and_school(
            cmd.user_id, SchoolId(cmd.school_id)
        )
        if membership is None:
            raise EntityNotFoundError("Vous n'êtes pas membre de cette école.")
        membership.guard_manage_structure()

        year = self._years.find_by_id(year_id)
        if year is None:
            raise EntityNotFoundError("Année scolaire introuvable.")
        if year.is_closed:
            raise DomainError("Impossible de modifier une année clôturée.")
        if not cmd.level_name.strip():
            raise DomainError("Le nom du niveau ne peut pas être vide.")
        if any(l.name.lower() == cmd.level_name.strip().lower() for l in year.levels):
            raise DuplicateEntityError(f"Un niveau '{cmd.level_name}' existe déjà dans cette année.")

        level = Level(
            id=LevelId(value=str(uuid.uuid4())),
            name=cmd.level_name.strip(),
            school_year_id=year_id,
            annual_fee=Money(cmd.annual_fee_fcfa, Currency.XOF),
            payment_mode=PaymentMode(cmd.payment_mode),
            nb_months=cmd.nb_months,
        )
        year.add_level(level)
        self._years.save(year)
        return AddLevelResult(success=True, level_id=str(level.id), level_name=level.name)
