"""
interface/director/views/misc.py
====================================
Vues diverses du directeur :
  - alerts              : page alertes de paiement
  - export_renvoyables  : export CSV alertes prioritaires
  - school_settings     : paramètres de l'école
"""
from __future__ import annotations

import csv
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from economat.composition import get_financial_dashboard_query
from economat.domain.identity.value_objects import Role
from economat.infrastructure.models import SchoolModel, SchoolYearModel
from economat.interface.decorators import require_membership, require_role

from ..forms import SchoolSettingsForm
from ._shared import _active_year, base_context

logger = logging.getLogger(__name__)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def alerts(request, school_id: str, year_id: str, membership=None):
    """Page dédiée aux alertes de paiement (retards, prioritaires)."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    bi_data = get_financial_dashboard_query().execute(
        school_id=school_id, year_id=year_id, collected_today=0
    )
    ctx = base_context(
        request, school, year, "alertes", membership=membership,
        bi=bi_data, page_title=f"Alertes — {year.label}",
    )
    return render(request, "economat/director/alerts.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def export_renvoyables(request, school_id: str, year_id: str, membership=None):
    """Export CSV des élèves en alerte prioritaire (retard > seuil)."""
    bi_data = get_financial_dashboard_query().execute(
        school_id=school_id, year_id=year_id, collected_today=0
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="alertes_prioritaires_{school_id[:8]}_{year_id[:8]}.csv"'
    )
    response.write("\ufeff")  # BOM UTF-8 pour Excel
    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Nom", "Niveau", "Classe",
        "Montant dû (FCFA)", "Jours de retard",
        "1ère échéance impayée", "Statut",
    ])
    if bi_data:
        for a in bi_data.alert_students:
            if a.alert_level == "critical":
                writer.writerow([
                    a.full_name, a.level, a.class_name,
                    a.overdue_amount, a.days_late,
                    a.oldest_overdue_date or "", "ALERTE PRIORITAIRE",
                ])
    return response


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def school_settings(request, school_id: str, membership=None):
    """Paramètres de l'école (seuil de tolérance en jours avant alerte prioritaire)."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
    except SchoolModel.DoesNotExist:
        return redirect("economat:director_dashboard")

    form = SchoolSettingsForm(
        request.POST or None,
        initial={"tolerance_days": school.tolerance_days, "country": school.country},
    )
    if request.method == "POST" and form.is_valid():
        school.tolerance_days = form.cleaned_data["tolerance_days"]
        school.country        = form.cleaned_data["country"]  # CountryModel instance
        school.save(update_fields=["tolerance_days", "country"])
        messages.success(request, f"Seuil mis à jour : {school.tolerance_days} jours.")
        return redirect("economat:school_settings", school_id=school_id)

    # _active_year() appelé une seule fois → partagé avec base_context
    active_year = _active_year(school_id)
    ctx = base_context(
        request, school, active_year, "settings", membership=membership,
        form=form, page_title=f"Paramètres — {school.name}",
    )
    return render(request, "economat/director/school_settings.html", ctx)



