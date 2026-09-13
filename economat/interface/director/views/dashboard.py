"""
interface/director/views/dashboard.py
========================================
Vue dashboard directeur : tableau de bord financier + switch_year.
Vue dashboard secrétaire : indicateurs non-financiers (effectifs, inscrits, niveaux).
"""
from __future__ import annotations

import datetime
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Sum
from django.shortcuts import redirect, render, reverse

from economat.composition import (
    get_financial_dashboard_query,
    get_list_memberships_query,
)
from economat.infrastructure.models import (
    ClassModel,
    EnrollmentModel,
    LevelModel,
    PaymentModel,
    SchoolModel,
    SchoolYearModel,
)
from economat.interface.decorators import require_membership

from ._shared import _active_year, base_context


@login_required
def dashboard(request):
    """Tableau de bord financier du directeur (KPIs + graphiques BI).
    Inaccessible à la secrétaire : redirigée vers son propre dashboard.
    """
    result = get_list_memberships_query().execute(user_id=str(request.user.pk))

    # ── Garde de rôle : sans rôle DIRECTOR → dashboard de son propre rôle ────
    roles = {m["role"] for m in result.memberships}
    if "DIRECTOR" not in roles:
        if "SECRETARY" in roles:
            return redirect("economat:secretary_dashboard")
        return redirect("economat:econome_dashboard")

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
        schools=schools,
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
def secretary_dashboard(request):
    """
    Tableau de bord de la secrétaire — indicateurs non-financiers uniquement.
    Aucun montant, taux ni objectif n'est exposé ici.

    Indicateurs :
      - Total élèves inscrits (année active)
      - Nombre de classes et de niveaux
      - Répartition des inscrits par niveau (effectifs, pas de montants)
      - Derniers élèves inscrits (8 plus récents)
      - Raccourcis métier
    """
    result = get_list_memberships_query().execute(user_id=str(request.user.pk))

    my_ids = [
        m["school_id"]
        for m in result.memberships
        if m["role"] in ("DIRECTOR", "SECRETARY")
    ]
    schools = SchoolModel.objects.filter(id__in=my_ids)

    school_id_p = request.GET.get("school")
    active_school = (
        schools.filter(id=school_id_p).first() if school_id_p else schools.first()
    )
    active_year_orm = None
    if active_school:
        active_year_orm = _active_year(str(active_school.id))

    # ── Indicateurs non-financiers ────────────────────────────────────────────
    total_inscrits    = 0
    total_classes     = 0
    total_niveaux     = 0
    repartition       = []
    derniers_inscrits = []

    if active_school and active_year_orm:
        base_enr = EnrollmentModel.objects.filter(
            school_year=active_year_orm, status="ACTIVE"
        )
        total_inscrits = base_enr.count()
        total_niveaux  = LevelModel.objects.filter(school_year=active_year_orm).count()
        total_classes  = ClassModel.objects.filter(
            level__school_year=active_year_orm
        ).count()

        # Répartition par niveau — COUNT uniquement, jamais Sum(amount)
        repartition = list(
            base_enr
            .values(niveau=F("level__name"))
            .annotate(nb=Count("id"))
            .order_by("-nb")
        )

        # Derniers inscrits (8 plus récents)
        derniers_inscrits = list(
            base_enr
            .select_related("student", "klass", "level")
            .order_by("-created_at")[:8]
        )

    ctx = base_context(
        request, active_school, active_year_orm, "dashboard_secretaire",
        schools=schools,
        total_inscrits=total_inscrits,
        total_classes=total_classes,
        total_niveaux=total_niveaux,
        repartition=repartition,
        derniers_inscrits=derniers_inscrits,
        page_title="Tableau de bord — Secrétaire",
    )
    return render(request, "economat/director/secretary_dashboard.html", ctx)


@login_required
@require_membership
def switch_year(request, school_id: str, membership=None):
    """Change l'année active et redirige vers le dashboard de la nouvelle année.
    Seul le directeur peut naviguer entre années ; secrétaire/économe sont
    toujours sur l'année active et retombent simplement sur leur accueil.
    """
    role = membership.role.value if membership else ""
    home = {
        "SECRETARY": "economat:secretary_dashboard",
        "ECONOME":   "economat:econome_dashboard",
    }.get(role, "economat:director_dashboard")

    year_id = request.GET.get("year_id", "").strip()
    if role != "DIRECTOR" or not year_id:
        return redirect(home)

    year = SchoolYearModel.objects.filter(pk=year_id, school_id=school_id).first()
    if not year:
        return redirect(home)

    url = reverse("economat:director_dashboard") + f"?school={school_id}&year={year_id}"
    return redirect(url)


@login_required
def dashboard_refresh(request):
    """
    Endpoint JSON léger, pollé par le dashboard directeur (JS, toutes les
    20s) pour signaler les nouveaux encaissements sans reload de page.
    Renvoie le même total que bi.kpi.collected_today calculé par dashboard().
    """
    from django.http import JsonResponse
    from economat.infrastructure.models import PaymentModel
    import datetime
    from django.db.models import Sum

    school_id_p = request.GET.get("school")
    year_id_p = request.GET.get("year")
    if not school_id_p or not year_id_p:
        return JsonResponse({"collected_today": 0})

    today = datetime.date.today()
    collected_today = (
        PaymentModel.objects
        .filter(state="VALID", payment_date=today,
                enrollment__school_year_id=year_id_p,
                enrollment__school_year__school_id=school_id_p)
        .aggregate(t=Sum("amount"))["t"] or 0
    )
    return JsonResponse({"collected_today": collected_today})
