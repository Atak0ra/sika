"""
tests/test_fee_domain.py
=========================
Tests unitaires du sous-domaine fee/ :
  - FeeCategory : catégories, manual_choices, labels
  - FeeScope : applies_to LEVEL et CLASS
  - FeeItem : invariants domaine (nom vide, montant 0, SCOLARITE/système)
  - PaymentSchedule.for_mensuel : nb_months paramétrable + labels calendaires
  - Level.get_payment_schedule avec nb_months variable
"""
import datetime
import pytest

from economat.domain.fee.entities import FeeItem
from economat.domain.fee.value_objects import FeeCategory, FeeItemId, FeeScope, FeeScopeType  # noqa
from economat.domain.school.entities import Level
from economat.domain.school.payment_schedule import PaymentMode, PaymentSchedule
from economat.domain.school.value_objects import LevelId, SchoolYearId
from economat.domain.shared.errors import DomainError, ZeroAmountError
from economat.domain.shared.value_objects import Currency, Money


def _money(amount: int) -> Money:
    return Money(amount, Currency.XOF)

def _scope_level(level_id: str = "level-1") -> FeeScope:
    return FeeScope.for_level(level_id)

def _fee_item(**overrides) -> FeeItem:
    defaults = dict(
        id=FeeItemId("fee-1"),
        school_year_id=SchoolYearId("year-1"),
        name="Cantine",
        category=FeeCategory.CANTINE,
        amount=_money(15_000),
        scope=_scope_level(),
        payment_mode=PaymentMode.UNIQUE,
        nb_months=10,
        is_mandatory=True,
        is_active=True,
        is_system=False,
    )
    defaults.update(overrides)
    return FeeItem(**defaults)


class TestFeeCategory:
    def test_all_categories_have_labels(self):
        for cat in FeeCategory:
            assert cat.label

    def test_manual_choices_excludes_scolarite(self):
        values = [v for v, _ in FeeCategory.manual_choices()]
        assert "SCOLARITE" not in values
        assert "CANTINE" in values

    def test_scolarite_label(self):
        assert FeeCategory.SCOLARITE.label == "Scolarité"


class TestFeeScope:
    def test_all_applies_to_any_class(self):
        assert FeeScope.all_classes().applies_to("cls-a") is True

    def test_all_applies_to_none(self):
        assert FeeScope.all_classes().applies_to(None) is True

    def test_classes_applies_to_matching(self):
        scope = FeeScope.for_classes(["cls-a", "cls-b"])
        assert scope.applies_to("cls-a") is True
        assert scope.applies_to("cls-b") is True

    def test_classes_no_match(self):
        assert FeeScope.for_classes(["cls-a"]).applies_to("cls-c") is False

    def test_classes_none_class_id(self):
        assert FeeScope.for_classes(["cls-a"]).applies_to(None) is False

    def test_for_classes_empty_raises(self):
        with pytest.raises(ValueError):
            FeeScope.for_classes([])

    def test_classes_scope_empty_tuple_raises(self):
        with pytest.raises(ValueError):
            FeeScope(scope_type=FeeScopeType.CLASSES, class_ids=())

    def test_single_class_helper(self):
        scope = FeeScope.for_class("cls-x")
        assert scope.applies_to("cls-x") is True
        assert scope.applies_to("cls-y") is False

    def test_for_level_returns_all(self):
        scope = FeeScope.for_level("lv-1")
        assert scope.scope_type == FeeScopeType.ALL


class TestFeeItemInvariants:
    def test_valid_fee_item(self):
        item = _fee_item()
        assert item.name == "Cantine"
        assert not item.is_system

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="vide"):
            _fee_item(name="   ")

    def test_zero_amount_raises_for_manual(self):
        with pytest.raises(ZeroAmountError):
            _fee_item(amount=_money(0))

    def test_scolarite_forbidden_on_manual(self):
        with pytest.raises(DomainError, match="SCOLARITE"):
            _fee_item(category=FeeCategory.SCOLARITE, is_system=False)

    def test_system_must_have_scolarite(self):
        with pytest.raises(DomainError):
            _fee_item(category=FeeCategory.CANTINE, is_system=True)

    def test_system_scolarite_zero_amount_ok(self):
        item = FeeItem(
            id=FeeItemId("sys-1"), school_year_id=SchoolYearId("year-1"),
            name="Scolarité — CM2", category=FeeCategory.SCOLARITE,
            amount=_money(0), scope=_scope_level(), is_system=True,
        )
        assert item.is_system

    def test_deactivate_manual(self):
        item = _fee_item()
        item.deactivate()
        assert not item.is_active

    def test_deactivate_system_raises(self):
        item = FeeItem(
            id=FeeItemId("sys-2"), school_year_id=SchoolYearId("year-1"),
            name="Scolarité", category=FeeCategory.SCOLARITE,
            amount=_money(0), scope=_scope_level(), is_system=True,
        )
        with pytest.raises(DomainError, match="système"):
            item.deactivate()

    def test_zero_nb_months_raises(self):
        with pytest.raises(ValueError):
            _fee_item(nb_months=0)

    def test_schedule_unique(self):
        schedule = _fee_item(payment_mode=PaymentMode.UNIQUE).get_payment_schedule(
            datetime.date(2024, 9, 1)
        )
        assert len(schedule.installments) == 1



class TestPaymentScheduleForMensuel:
    def test_calendar_labels_from_october(self):
        schedule = PaymentSchedule.for_mensuel(_money(100_000), datetime.date(2024, 10, 1), nb_months=3)
        assert [i.label for i in schedule.installments] == ["Octobre", "Novembre", "Décembre"]

    def test_calendar_labels_cross_year(self):
        schedule = PaymentSchedule.for_mensuel(_money(120_000), datetime.date(2024, 11, 1), nb_months=4)
        assert [i.label for i in schedule.installments] == ["Novembre", "Décembre", "Janvier", "Février"]

    def test_5_months(self):
        schedule = PaymentSchedule.for_mensuel(_money(50_000), datetime.date(2024, 9, 1), nb_months=5)
        assert len(schedule.installments) == 5
        assert sum(i.amount.amount for i in schedule.installments) == 50_000

    def test_total_preserved_various_nb_months(self):
        for nb in [1, 3, 7, 10, 12]:
            s = PaymentSchedule.for_mensuel(_money(133_333), datetime.date(2024, 10, 1), nb_months=nb)
            assert sum(i.amount.amount for i in s.installments) == 133_333

    def test_zero_nb_months_raises(self):
        with pytest.raises(Exception):
            PaymentSchedule.for_mensuel(_money(10_000), datetime.date(2024, 9, 1), nb_months=0)


class TestLevelNbMonths:
    def _level(self, nb_months: int = 10) -> Level:
        return Level(
            id=LevelId("lv-1"), name="CM2", school_year_id=SchoolYearId("year-1"),
            annual_fee=_money(120_000), payment_mode=PaymentMode.MENSUEL, nb_months=nb_months,
        )

    def test_default_is_10(self):
        assert self._level().nb_months == 10

    def test_custom_nb_months(self):
        assert self._level(nb_months=9).nb_months == 9

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            self._level(nb_months=0)

    def test_schedule_uses_nb_months(self):
        schedule = self._level(nb_months=9).get_payment_schedule(datetime.date(2024, 10, 1))
        assert len(schedule.installments) == 9
        assert sum(i.amount.amount for i in schedule.installments) == 120_000

    def test_schedule_mensuel_uses_nb_months(self):
        schedule = _fee_item(
            payment_mode=PaymentMode.MENSUEL, nb_months=9, amount=_money(90_000)
        ).get_payment_schedule(datetime.date(2024, 10, 1))
        assert len(schedule.installments) == 9
        assert schedule.installments[0].amount == _money(10_000)
