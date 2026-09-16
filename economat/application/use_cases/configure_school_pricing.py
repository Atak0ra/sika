from __future__ import annotations
from economat.application.dto import ConfigureSchoolPricingCommand, ConfigurePricingResult
from economat.application.ports.repositories import FeeItemRepository, SchoolYearRepository
from economat.domain.fee.value_objects import FeeScope
from economat.domain.school.payment_schedule import PaymentMode
from economat.domain.school.value_objects import LevelId, SchoolYearId
from economat.domain.shared.errors import DomainError, EntityNotFoundError
from economat.domain.shared.value_objects import Money, Currency


class ConfigureSchoolPricingUseCase:
    def __init__(self, year_repo: SchoolYearRepository,
                 fee_item_repo: FeeItemRepository | None = None):
        self._years    = year_repo
        self._fee_items = fee_item_repo

    def execute(self, cmd: ConfigureSchoolPricingCommand) -> ConfigurePricingResult:
        try:
            year = self._years.find_by_id(SchoolYearId(cmd.year_id))
            if year is None:
                raise EntityNotFoundError("Année scolaire introuvable.")
            if cmd.annual_fee_fcfa <= 0:
                raise DomainError("Le montant annuel doit être supérieur à 0 FCFA.")
            year.configure_level_pricing(
                level_id=LevelId(cmd.level_id),
                annual_fee=Money(cmd.annual_fee_fcfa, Currency.XOF),
                payment_mode=PaymentMode(cmd.payment_mode),
                nb_months=cmd.nb_months,
            )
            self._years.save(year)
            level = year.get_level(LevelId(cmd.level_id))

            # Synchroniser (créer ou mettre à jour) la ligne système SCOLARITE
            if self._fee_items is not None:
                self._fee_items.ensure_system_fee_for_level(
                    level_id=LevelId(cmd.level_id),
                    level_name=level.name,
                    year_id=SchoolYearId(cmd.year_id),
                    annual_fee_fcfa=cmd.annual_fee_fcfa,
                    payment_mode=cmd.payment_mode,
                    nb_months=cmd.nb_months,
                    scope=FeeScope.for_level(cmd.level_id),
                )

            return ConfigurePricingResult(
                success=True, level_name=level.name,
                new_fee_fcfa=cmd.annual_fee_fcfa, payment_mode=cmd.payment_mode,
            )
        except DomainError as e:
            return ConfigurePricingResult(success=False, error_message=str(e))
        except Exception as e:
            return ConfigurePricingResult(success=False, error_message=f"Erreur inattendue : {e}")

