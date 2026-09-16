"""
tests/test_fee_use_cases.py
============================
Tests des use cases FeeItem : Create, Update, Deactivate, ListPayableItems.
"""
import pytest
from economat.application.dto import (
    CreateFeeItemCommand, DeactivateFeeItemCommand, UpdateFeeItemCommand,
)
from economat.application.use_cases.create_fee_item import CreateFeeItemUseCase
from economat.application.use_cases.update_fee_item import (
    DeactivateFeeItemUseCase, UpdateFeeItemUseCase,
)
from economat.domain.fee.entities import FeeItem
from economat.domain.fee.value_objects import FeeCategory, FeeItemId, FeeScope
from economat.domain.school.payment_schedule import PaymentMode
from economat.domain.school.value_objects import SchoolYearId
from economat.domain.shared.value_objects import Currency, Money


class _FeeItemRepo:
    def __init__(self): self._store: dict = {}
    def find_by_id(self, fid): return self._store.get(str(fid))
    def find_by_year(self, yid): return list(self._store.values())
    def find_active_by_year(self, yid): return [fi for fi in self._store.values() if fi.is_active]
    def find_applicable_to_enrollment(self, yid, cid):
        return [fi for fi in self._store.values()
                if fi.is_active and fi.applies_to(str(cid))]
    def find_system_for_level(self, lid, yid):
        return next((fi for fi in self._store.values()
                     if fi.is_system and fi.level_id_hint == str(lid)), None)  # not used in new scope
    def ensure_system_fee_for_level(self, level_id, level_name, year_id,
                                    annual_fee_fcfa, payment_mode, nb_months, scope):
        import uuid
        existing = self.find_system_for_level(level_id, year_id)
        if existing:
            existing.amount = Money(annual_fee_fcfa, Currency.XOF)
            return existing
        fi = FeeItem(
            id=FeeItemId(str(uuid.uuid4())),
            school_year_id=SchoolYearId(str(year_id)),
            name=f"Scolarité — {level_name}",
            category=FeeCategory.SCOLARITE,
            amount=Money(annual_fee_fcfa, Currency.XOF),
            scope=scope, payment_mode=PaymentMode(payment_mode),
            nb_months=nb_months, is_system=True,
        )
        self._store[str(fi.id)] = fi
        return fi
    def save(self, fi): self._store[str(fi.id)] = fi
    def next_id(self): return FeeItemId.generate()


def _cmd(**kw):
    base = dict(school_year_id="year-1", name="Cantine T1", category="CANTINE",
                amount_fcfa=15_000, scope_type="ALL", class_ids=[],
                payment_mode="UNIQUE", nb_months=10, is_mandatory=True)
    base.update(kw)
    return CreateFeeItemCommand(**base)


class TestCreateFeeItemUseCase:
    def test_ok(self):
        repo = _FeeItemRepo()
        r = CreateFeeItemUseCase(repo).execute(_cmd())
        assert r.success and r.fee_item_id and r.category == "CANTINE"

    def test_rejects_scolarite(self):
        r = CreateFeeItemUseCase(_FeeItemRepo()).execute(_cmd(category="SCOLARITE"))
        assert not r.success and "SCOLARITE" in r.error_message

    def test_rejects_zero_amount(self):
        r = CreateFeeItemUseCase(_FeeItemRepo()).execute(_cmd(amount_fcfa=0))
        assert not r.success

    def test_rejects_empty_name(self):
        r = CreateFeeItemUseCase(_FeeItemRepo()).execute(_cmd(name="  "))
        assert not r.success

    def test_rejects_unknown_category(self):
        r = CreateFeeItemUseCase(_FeeItemRepo()).execute(_cmd(category="FOOBAR"))
        assert not r.success

    def test_class_scope(self):
        r = CreateFeeItemUseCase(_FeeItemRepo()).execute(_cmd(scope_type="CLASSES", class_ids=["class-a"]))
        assert r.success


class TestUpdateFeeItemUseCase:
    def _create(self, repo, **kw) -> str:
        r = CreateFeeItemUseCase(repo).execute(_cmd(**kw))
        assert r.success
        return r.fee_item_id

    def test_update_ok(self):
        repo = _FeeItemRepo()
        fid = self._create(repo)
        r = UpdateFeeItemUseCase(repo).execute(UpdateFeeItemCommand(
            fee_item_id=fid, name="Cantine T2", amount_fcfa=20_000,
            payment_mode="UNIQUE", nb_months=10, is_mandatory=False,
        ))
        assert r.success
        item = repo.find_by_id(FeeItemId(fid))
        assert item.name == "Cantine T2" and item.amount.amount == 20_000

    def test_cannot_update_system(self):
        repo = _FeeItemRepo()
        sys = FeeItem(
            id=FeeItemId("sys-1"), school_year_id=SchoolYearId("year-1"),
            name="Scolarité", category=FeeCategory.SCOLARITE,
            amount=Money(100_000, Currency.XOF),
            scope=FeeScope.all_classes(), is_system=True,
        )
        repo.save(sys)
        r = UpdateFeeItemUseCase(repo).execute(UpdateFeeItemCommand(
            fee_item_id="sys-1", name="X", amount_fcfa=1, payment_mode="UNIQUE",
            nb_months=10, is_mandatory=True,
        ))
        assert not r.success and "système" in r.error_message

    def test_deactivate(self):
        repo = _FeeItemRepo()
        fid = self._create(repo)
        r = DeactivateFeeItemUseCase(repo).execute(DeactivateFeeItemCommand(fee_item_id=fid))
        assert r.success and not repo.find_by_id(FeeItemId(fid)).is_active

    def test_deactivate_not_found(self):
        r = DeactivateFeeItemUseCase(_FeeItemRepo()).execute(DeactivateFeeItemCommand(fee_item_id="ghost"))
        assert not r.success
