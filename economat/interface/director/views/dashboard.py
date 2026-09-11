"""
interface/director/views/dashboard.py
========================================
Vue dashboard directeur : tableau de bord financier + switch_year.
"""
from __future__ import annotations

import datetime
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render, reverse

from economat.composition import (
    get_financial_dashboard_query,
    get_list_memberships_query,
)
from economat.infrastructure.models import (
    PaymentModel,
    SchoolModel,
    SchoolYearModel,
)
from economat.interface.decorators import require_membership

from ._shared import _active_year, base_context


@login_required
def dashboard(request):
    """Tableau de bord financier du directeur (KPIs + graphiques BI)."""
    result = get_list_memberships_query().execute(user_id=str(request.user.pk))
    my_ids = [
        m["school_id"]
        for m in result.memberships
        if m["role"] in ("DIRECTOR", "SECRETARY")
    ]
    schools = SchoolModel.objects.prefetch_related("school_years").filter(id__in=my_ids)

    school_id_p = request.GET.get("school")
    active_school = (
        schools.filter(id=school_id_p).first() if school_id_p else schools.first()
    )

    today = datetime.date.today()
    year_id_p = request.GET.get("year")
    active_year_orm = None
    if active_school:
        if year_id_p:
            active_year_orm = SchoolYearModel.objects.filter(
                id=year_id_p, school_id=active_school.id
            ).first()
        if not active_year_orm:
            active_year_orm = _active_year(str(active_school.id))

    collected_today = 0
    bi_data = None
    period_labels = period_expected = period_real = "[]"
    class_labels = class_objectives = class_collected = class_rates = "[]"

    if active_school and active_year_orm:
        collected_today = (
            PaymentModel.objects
            .filter(
                state="VALID",
                payment_date=today,
                enrollment__school_year_id=active_year_orm.id,
            )
            .aggregate(t=Sum("amount"))["t"] or 0
        )
        bi_data = get_financial_dashboard_query().execute(
            school_id=str(active_school.id),
            year_id=str(active_year_orm.id),
            collected_today=collected_today,
        )
        if bi_data:
            period_labels   = json.dumps(bi_data.period_series.labels)
            period_expected = json.dumps(bi_data.period_series.expected)
            period_real     = json.dumps(bi_data.period_series.collected)
            class_labels     = json.dumps(
                [f"{b.level} \u2013 {b.label}" for b in bi_data.class_bars]
            )
            class_objectives = json.dumps([b.objective  for b in bi_data.class_bars])
            class_collected  = json.dumps([b.collected  for b in bi_data.class_bars])
            class_rates      = json.dumps([b.rate       for b in bi_data.class_bars])

    ctx = base_context(
        request, active_school, active_year_orm, "dashboard",
        # Pas de membership ici (vue sans @require_membership)
        schools=schools,   # override : on a déjà la QS filtrée
        bi=bi_data,
        period_labels=period_labels,
        period_expected=period_expected,
        period_real=period_real,
        class_labels=class_labels,
        class_objectives=class_objectives,
        class_collected=class_collected,
        class_rates=class_rates,
        page_title="Tableau de bord — Directeur",
    )
    return render(request, "economat/director/dashboard.html", ctx)


@login_required
@require_membership
def switch_year(request, school_id: str, membership=None):
    """Change l'année active et redirige vers le dashboard de la nouvelle année."""
    year_id = request.GET.get("year_id", "").strip()
    if not year_id:
        return redirect("economat:director_dashboard")

    year = SchoolYearModel.objects.filter(pk=year_id, school_id=school_id).first()
    if not year:
        return redirect("economat:director_dashboard")

    url = reverse("economat:director_dashboard") + f"?school={school_id}&year={year_id}"
    return redirect(url)
