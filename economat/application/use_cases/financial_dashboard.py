"""
application/use_cases/financial_dashboard.py — REFONTE (SchoolYear + Enrollment).
"""
from __future__ import annotations
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from economat.application.ports.repositories import (  # noqa: F401
    EnrollmentRepository, PaymentRepository, SchoolRepository,
    SchoolYearRepository, StudentRepository,
)
from economat.domain.payment.payment_status import PaymentStatusCalculator
from economat.domain.payment.value_objects import PaymentStatus
from economat.domain.school.value_objects import SchoolId, SchoolYearId


@dataclass
class KpiData:
    total_expected: int; collected_year: int; collected_today: int
    remaining: int; recovery_rate: int; perf_level: str; total_students: int

@dataclass
class PeriodSeries:
    labels: List[str]; expected: List[int]; collected: List[int]

@dataclass
class ClassBarData:
    label: str; level: str; objective: int; collected: int; rate: int; late_count: int

@dataclass
class AlertStudent:
    student_id: str; full_name: str; level: str; class_name: str
    overdue_amount: int; days_late: int; oldest_overdue_date: Optional[str]
    alert_level: str

@dataclass
class CategoryBreakdown:
    """Ventilation des encaissements + pr\u00e9visionnel par cat\u00e9gorie."""
    category: str; category_label: str
    collected: int; expected: int; rate: int; color: str

@dataclass
class FinancialDashboardData:
    school_id: str; school_name: str; year_label: str; tolerance_days: int
    kpi: KpiData; period_series: PeriodSeries; class_bars: List[ClassBarData]
    total_late: int; total_critical: int; late_by_class: List[dict]
    alert_students: List[AlertStudent]
    category_breakdown: List[CategoryBreakdown] = field(default_factory=list)


_CATEGORY_COLORS = {
    "SCOLARITE": "#4f46e5", "CANTINE": "#d97706", "TRANSPORT": "#0369a1",
    "SORTIES": "#059669", "SPORT": "#be185d", "FOURNITURES": "#7c3aed", "AUTRE": "#6b7280",
}
_CATEGORY_LABELS = {
    "SCOLARITE": "Scolarit\u00e9", "CANTINE": "Cantine", "TRANSPORT": "Transport",
    "SORTIES": "Sorties", "SPORT": "Sport", "FOURNITURES": "Fournitures", "AUTRE": "Autre",
}


class GetFinancialDashboardQuery:
    def __init__(self, school_repo, year_repo, student_repo, enrollment_repo, payment_repo):
        self._schools = school_repo; self._years = year_repo
        self._students = student_repo; self._enrollments = enrollment_repo
        self._payments = payment_repo; self._calc = PaymentStatusCalculator()

    def execute(self, school_id: str, year_id: str, collected_today: int = 0):
        sid = SchoolId(school_id); yid = SchoolYearId(year_id)
        school = self._schools.find_by_id(sid)
        year   = self._years.find_by_id(yid)
        if school is None or year is None: return None
        today = datetime.date.today(); tolerance = school.tolerance_days
        enrollments = self._enrollments.find_active_by_year(yid)
        total_students = len(enrollments)
        payments_by_enrollment = self._payments.find_by_school_and_year(sid, yid)
        schedules = {str(lv.id): lv.get_payment_schedule(year.start_date) for lv in year.levels}
        scol_expected = sum(
            schedules[str(e.level_id)].total_amount.amount
            for e in enrollments if str(e.level_id) in schedules
        )
        fee_expected_by_cat = _fee_item_expected_by_category(str(yid), enrollments)
        total_expected = scol_expected + sum(fee_expected_by_cat.values())
        collected_year = sum(
            p.amount.amount for pays in payments_by_enrollment.values()
            for p in pays if p.is_valid()
        )
        remaining = max(total_expected - collected_year, 0)
        recovery_rate = round(collected_year / total_expected * 100) if total_expected else 0
        perf_level = "good" if recovery_rate >= 80 else ("warning" if recovery_rate >= 50 else "critical")
        kpi = KpiData(
            total_expected=total_expected, collected_year=collected_year,
            collected_today=collected_today, remaining=remaining,
            recovery_rate=recovery_rate, perf_level=perf_level, total_students=total_students,
        )
        collected_by_cat = _collected_by_category(str(yid))
        scol_collected   = collected_by_cat.get("SCOLARITE", 0)
        category_breakdown = []
        if scol_expected > 0 or scol_collected > 0:
            rate = round(scol_collected / scol_expected * 100) if scol_expected else 0
            category_breakdown.append(CategoryBreakdown(
                category="SCOLARITE", category_label="Scolarité",
                collected=scol_collected, expected=scol_expected,
                rate=rate, color=_CATEGORY_COLORS["SCOLARITE"],
            ))
        for cat, exp in sorted(fee_expected_by_cat.items()):
            coll = collected_by_cat.get(cat, 0)
            rate = round(coll / exp * 100) if exp else 0
            category_breakdown.append(CategoryBreakdown(
                category=cat, category_label=_CATEGORY_LABELS.get(cat, cat),
                collected=coll, expected=exp, rate=rate,
                color=_CATEGORY_COLORS.get(cat, "#6b7280"),
            ))
        enr_by_class = defaultdict(list)
        for e in enrollments: enr_by_class[str(e.class_id)].append(e)
        alert_students = []; agg = {}
        for enr in enrollments:
            sched = schedules.get(str(enr.level_id))
            if not sched: continue
            pays = payments_by_enrollment.get(str(enr.id), [])
            r = self._calc.calculate(sched, pays, as_of=today)
            if r.status != PaymentStatus.EN_RETARD: continue
            alert_lvl = "critical" if r.days_late > tolerance else "late"
            student_name = str(enr.student_id)
            try:
                from economat.infrastructure.models import StudentModel
                s = StudentModel.objects.get(pk=str(enr.student_id))
                student_name = f"{s.first_name} {s.last_name.upper()}"
            except Exception: pass
            level = year.get_level(enr.level_id)
            klass = level.find_class(enr.class_id)
            alert_students.append(AlertStudent(
                student_id=str(enr.student_id), full_name=student_name,
                level=level.name, class_name=klass.name if klass else "",
                overdue_amount=r.overdue_amount.amount, days_late=r.days_late,
                oldest_overdue_date=r.oldest_overdue_date.isoformat() if r.oldest_overdue_date else None,
                alert_level=alert_lvl,
            ))
            key = f"{level.name}||{klass.name if klass else ''}"
            if key not in agg: agg[key] = {"level": level.name, "class_name": klass.name if klass else "", "late": 0, "critical": 0}
            agg[key][alert_lvl] += 1
        alert_students.sort(key=lambda a: (0 if a.alert_level == "critical" else 1, -a.days_late))
        late_by_class = sorted(agg.values(), key=lambda x: -(x["critical"] + x["late"]))
        period_series = _build_period_series(year, schedules, enr_by_class, payments_by_enrollment)
        class_bars    = _build_class_bars(year, schedules, enr_by_class, payments_by_enrollment, self._calc)
        return FinancialDashboardData(
            school_id=school_id, school_name=school.name, year_label=year.label,
            tolerance_days=tolerance, kpi=kpi, period_series=period_series, class_bars=class_bars,
            total_late=sum(1 for a in alert_students if a.alert_level == "late"),
            total_critical=sum(1 for a in alert_students if a.alert_level == "critical"),
            late_by_class=late_by_class, alert_students=alert_students,
            category_breakdown=category_breakdown,
        )


def _fee_item_expected_by_category(year_id, enrollments):
    from economat.infrastructure.models import FeeItemModel
    from collections import defaultdict
    result = defaultdict(int)
    fee_items = FeeItemModel.objects.filter(school_year_id=year_id, is_active=True, is_system=False).select_related("level")
    level_counts = defaultdict(int)
    class_counts = defaultdict(int)
    for e in enrollments:
        level_counts[str(e.level_id)] += 1
        cid = str(getattr(e, "klass_id", None) or getattr(e, "class_id", None) or "")
        if cid: class_counts[cid] += 1
    for fi in fee_items:
        if fi.scope_type == "ALL":
            nb = sum(level_counts.values())  # tous les élèves inscrits
        elif fi.scope_type == "CLASSES" and fi.class_ids:
            nb = sum(class_counts.get(str(cid), 0) for cid in fi.class_ids)
        else:
            nb = 0
        if nb > 0: result[fi.category] += fi.amount * nb
    return dict(result)


def _collected_by_category(year_id):
    from django.db.models import Sum
    from economat.infrastructure.models import PaymentModel
    rows = (
        PaymentModel.objects
        .filter(state="VALID", enrollment__school_year_id=year_id, fee_item__isnull=False)
        .values("fee_item__category")
        .annotate(total=Sum("amount"))
    )
    return {r["fee_item__category"]: r["total"] for r in rows if r["fee_item__category"]}


def _build_period_series(year, schedules, enr_by_class, payments_by_enrollment):
    from collections import defaultdict
    period_map = defaultdict(int)
    for level in year.levels:
        sched = schedules.get(str(level.id))
        if not sched: continue
        nb_enr = sum(len(enr_by_class.get(str(kl.id), [])) for kl in level.classes)
        for inst in sched.installments:
            period_map[(inst.due_date, inst.label)] += inst.amount.amount * nb_enr
    sorted_periods = sorted(period_map.items(), key=lambda x: x[0][0])
    if not sorted_periods: return PeriodSeries(labels=[], expected=[], collected=[])
    real_by_month = defaultdict(int)
    for pays_list in payments_by_enrollment.values():
        for p in pays_list:
            if p.is_valid(): real_by_month[p.payment_date.replace(day=1)] += p.amount.amount
    labels, exp_cum, real_cum = [], [], []
    cum_exp = 0; all_real = sorted(real_by_month.items())
    for (due_date, label), amt in sorted_periods:
        cum_exp += amt
        cum_real = sum(v for d, v in all_real if d <= due_date)
        labels.append(label); exp_cum.append(cum_exp); real_cum.append(cum_real)
    return PeriodSeries(labels=labels, expected=exp_cum, collected=real_cum)


def _build_class_bars(year, schedules, enr_by_class, payments_by_enrollment, calc):
    bars = []
    for level in year.levels:
        sched = schedules.get(str(level.id))
        if not sched: continue
        for klass in level.classes:
            enrollments = enr_by_class.get(str(klass.id), [])
            if not enrollments: continue
            objective = sched.total_amount.amount * len(enrollments)
            collected = late_count = 0
            for enr in enrollments:
                pays = payments_by_enrollment.get(str(enr.id), [])
                collected += sum(p.amount.amount for p in pays if p.is_valid())
                r = calc.calculate(sched, pays)
                if r.status == PaymentStatus.EN_RETARD: late_count += 1
            rate = round(collected / objective * 100) if objective else 0
            bars.append(ClassBarData(label=klass.name, level=level.name,
                objective=objective, collected=collected, rate=rate, late_count=late_count))
    bars.sort(key=lambda b: b.rate)
    return bars
