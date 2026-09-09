"""
application/use_cases/financial_dashboard.py — REFONTE (SchoolYear + Enrollment).
"""
from __future__ import annotations
import datetime
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from economat.application.ports.repositories import (
    EnrollmentRepository, PaymentRepository, SchoolRepository,
    SchoolYearRepository, StudentRepository,
)
from economat.domain.payment.payment_status import PaymentStatusCalculator
from economat.domain.payment.value_objects import PaymentStatus
from economat.domain.school.value_objects import SchoolId, SchoolYearId


@dataclass
class KpiData:
    total_expected:  int; collected_year: int; collected_today: int
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
class FinancialDashboardData:
    school_id: str; school_name: str; year_label: str; tolerance_days: int
    kpi: KpiData; period_series: PeriodSeries; class_bars: List[ClassBarData]
    total_late: int; total_critical: int; late_by_class: List[dict]
    alert_students: List[AlertStudent]


class GetFinancialDashboardQuery:
    def __init__(self, school_repo, year_repo, student_repo, enrollment_repo, payment_repo):
        self._schools     = school_repo
        self._years       = year_repo
        self._students    = student_repo
        self._enrollments = enrollment_repo
        self._payments    = payment_repo
        self._calc        = PaymentStatusCalculator()

    def execute(self, school_id: str, year_id: str,
                collected_today: int = 0) -> Optional[FinancialDashboardData]:
        sid  = SchoolId(school_id)
        yid  = SchoolYearId(year_id)
        school = self._schools.find_by_id(sid)
        year   = self._years.find_by_id(yid)
        if school is None or year is None:
            return None

        today     = datetime.date.today()
        tolerance = school.tolerance_days

        # Élèves inscrits cette année
        enrollments = self._enrollments.find_active_by_year(yid)
        total_students = len(enrollments)

        # Paiements batch
        payments_by_enrollment: Dict[str, list] = self._payments.find_by_school_and_year(sid, yid)

        # Barèmes par niveau (une fois par niveau)
        schedules = {str(lv.id): lv.get_payment_schedule(year.start_date)
                     for lv in year.levels}

        # KPIs
        total_expected = sum(
            schedules[str(e.level_id)].total_amount.amount
            for e in enrollments if str(e.level_id) in schedules
        )
        collected_year = sum(
            p.amount.amount
            for pays in payments_by_enrollment.values()
            for p in pays if p.is_valid()
        )
        remaining     = max(total_expected - collected_year, 0)
        recovery_rate = round(collected_year / total_expected * 100) if total_expected else 0
        perf_level    = "good" if recovery_rate >= 80 else ("warning" if recovery_rate >= 50 else "critical")

        kpi = KpiData(
            total_expected=total_expected, collected_year=collected_year,
            collected_today=collected_today, remaining=remaining,
            recovery_rate=recovery_rate, perf_level=perf_level, total_students=total_students,
        )

        # Enrollment index
        enr_by_class: Dict[str, list] = defaultdict(list)
        for e in enrollments:
            enr_by_class[str(e.class_id)].append(e)

        # Alertes
        alert_students: List[AlertStudent] = []
        agg: Dict[str, dict] = {}

        for level in year.levels:
            sched = schedules.get(str(level.id))
            if not sched:
                continue
            for klass in level.classes:
                for enr in enr_by_class.get(str(klass.id), []):
                    pays   = payments_by_enrollment.get(str(enr.id), [])
                    result = self._calc.calculate(sched, pays, as_of=today)
                    if result.status != PaymentStatus.EN_RETARD:
                        continue
                    # Récupérer le nom de l'élève
                    student = self._students.find_by_id(enr.student_id)
                    full_name = student.name.full_name if student else str(enr.student_id)
                    days = result.days_late
                    alert_lvl = "critical" if days >= tolerance else "late"
                    alert_students.append(AlertStudent(
                        student_id=str(enr.student_id), full_name=full_name,
                        level=level.name, class_name=klass.name,
                        overdue_amount=result.overdue_amount.amount,
                        days_late=days,
                        oldest_overdue_date=result.oldest_overdue_date.isoformat() if result.oldest_overdue_date else None,
                        alert_level=alert_lvl,
                    ))
                    key = f"{level.name}||{klass.name}"
                    if key not in agg:
                        agg[key] = {"level": level.name, "class_name": klass.name, "late": 0, "critical": 0}
                    agg[key][alert_lvl] += 1

        alert_students.sort(key=lambda a: (0 if a.alert_level == "critical" else 1, -a.days_late))
        late_by_class = sorted(agg.values(), key=lambda x: -(x["critical"] + x["late"]))

        # Séries graphiques
        period_series = _build_period_series(year, schedules, enr_by_class, payments_by_enrollment)
        class_bars    = _build_class_bars(year, schedules, enr_by_class, payments_by_enrollment, self._calc)

        return FinancialDashboardData(
            school_id=school_id, school_name=school.name, year_label=year.label,
            tolerance_days=tolerance, kpi=kpi,
            period_series=period_series, class_bars=class_bars,
            total_late=sum(1 for a in alert_students if a.alert_level == "late"),
            total_critical=sum(1 for a in alert_students if a.alert_level == "critical"),
            late_by_class=late_by_class, alert_students=alert_students,
        )


def _build_period_series(year, schedules, enr_by_class, payments_by_enrollment) -> PeriodSeries:
    from collections import defaultdict
    period_map = defaultdict(int)
    for level in year.levels:
        sched = schedules.get(str(level.id))
        if not sched: continue
        nb_enr = sum(len(enr_by_class.get(str(kl.id), [])) for kl in level.classes)
        for inst in sched.installments:
            period_map[(inst.due_date, inst.label)] += inst.amount.amount * nb_enr
    sorted_periods = sorted(period_map.items(), key=lambda x: x[0][0])
    if not sorted_periods:
        return PeriodSeries(labels=[], expected=[], collected=[])
    real_by_month = defaultdict(int)
    for pays_list in payments_by_enrollment.values():
        for p in pays_list:
            if p.is_valid():
                real_by_month[p.payment_date.replace(day=1)] += p.amount.amount
    labels, exp_cum, real_cum = [], [], []
    cum_exp = 0
    all_real = sorted(real_by_month.items())
    for (due_date, label), amt in sorted_periods:
        cum_exp += amt
        cum_real = sum(v for d, v in all_real if d <= due_date)
        labels.append(label); exp_cum.append(cum_exp); real_cum.append(cum_real)
    return PeriodSeries(labels=labels, expected=exp_cum, collected=real_cum)


def _build_class_bars(year, schedules, enr_by_class, payments_by_enrollment, calc) -> list:
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
                if r.status == PaymentStatus.EN_RETARD:
                    late_count += 1
            rate = round(collected / objective * 100) if objective else 0
            bars.append(ClassBarData(
                label=klass.name, level=level.name,
                objective=objective, collected=collected,
                rate=rate, late_count=late_count,
            ))
    bars.sort(key=lambda b: b.rate)
    return bars
