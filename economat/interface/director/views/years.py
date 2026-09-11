"""
interface/director/views/years.py
====================================
Vues de gestion des années scolaires : création, activation, clôture.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from economat.application.dto import (
    ActivateSchoolYearCommand,
    CloseSchoolYearCommand,
    CreateSchoolYearCommand,
)
from economat.composition import (
    get_activate_school_year_use_case,
    get_close_school_year_use_case,
    get_create_school_year_use_case,
)
from economat.domain.identity.value_objects import Role
from economat.infrastructure.models import SchoolModel, SchoolYearModel
from economat.interface.decorators import require_membership, require_role

from ..forms import CreateSchoolYearForm
from ._shared import _active_year, base_context


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def manage_years(request, school_id: str, membership=None):
    """Page de gestion des années scolaires (liste + création)."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
    except SchoolModel.DoesNotExist:
        messages.error(request, "École introuvable.")
        return redirect("economat:director_dashboard")

    all_years = SchoolYearModel.objects.filter(school_id=school_id).order_by("-label")
    form = CreateSchoolYearForm(request.POST or None)

    if request.method == "POST" and "create_year" in request.POST and form.is_valid():
        dup = request.POST.get("duplicate_from", "").strip() or None
        result = get_create_school_year_use_case().execute(CreateSchoolYearCommand(
            school_id=school_id,
            label=form.cleaned_data["label"],
            start_date=form.cleaned_data["start_date"],
            end_date=form.cleaned_data["end_date"],
            duplicate_from_year_id=dup,
        ))
        if result.success:
            if result.status == "ACTIVE":
                messages.success(
                    request,
                    f"Année '{result.label}' créée et activée. "
                    "Configurez maintenant vos niveaux.",
                )
                return redirect("economat:add_level", school_id=school_id, year_id=result.year_id)
            else:
                messages.success(
                    request,
                    f"Année '{result.label}' créée. Activez-la quand vous êtes prêt.",
                )
                return redirect("economat:manage_years", school_id=school_id)
        messages.error(request, f"{result.error_message}")

    active_year = _active_year(school_id)
    ctx = base_context(
        request, school, active_year, "annees",
        membership=membership,
        all_years=all_years,
        form=form,
        page_title=f"Années scolaires — {school.name}",
    )
    return render(request, "economat/director/manage_years.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def activate_year(request, school_id: str, year_id: str, membership=None):
    """Activation d'une année scolaire (POST uniquement)."""
    if request.method != "POST":
        return redirect("economat:manage_years", school_id=school_id)
    result = get_activate_school_year_use_case().execute(
        ActivateSchoolYearCommand(school_id=school_id, year_id=year_id)
    )
    if result.success:
        messages.success(request, f"Année '{result.label}' maintenant ACTIVE.")
    else:
        messages.error(request, f"{result.error_message}")
    return redirect("economat:manage_years", school_id=school_id)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def close_year(request, school_id: str, year_id: str, membership=None):
    """Clôture d'une année scolaire (POST uniquement, irréversible)."""
    if request.method != "POST":
        return redirect("economat:manage_years", school_id=school_id)
    result = get_close_school_year_use_case().execute(
        CloseSchoolYearCommand(year_id=year_id)
    )
    if result.success:
        messages.success(request, f"Année '{result.label}' clôturée.")
    else:
        messages.error(request, f"{result.error_message}")
    return redirect("economat:manage_years", school_id=school_id)
