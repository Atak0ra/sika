"""
interface/director/views/structure.py
=========================================
Vues de gestion de la structure pédagogique :
  - add_level         : création des niveaux (ex. CM1, CM2, 6ème…)
  - add_class         : création des classes rattachées à un niveau
  - configure_pricing : configuration des frais de scolarité par niveau
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from economat.application.dto import (
    AddClassCommand,
    AddLevelCommand,
    ConfigureSchoolPricingCommand,
)
from economat.composition import (
    get_add_class_use_case,
    get_add_level_use_case,
    get_configure_pricing_use_case,
)
from economat.domain.identity.value_objects import Role
from economat.infrastructure.models import (
    ClassModel,
    LevelModel,
    SchoolModel,
    SchoolYearModel,
)
from economat.interface.decorators import require_membership, require_role

from ..forms import AddClassForm, AddLevelForm, ConfigurePricingForm
from ._shared import base_context


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def add_level(request, school_id: str, year_id: str, membership=None):
    """Création des niveaux pédagogiques pour une année scolaire donnée."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    form = AddLevelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = get_add_level_use_case().execute(AddLevelCommand(
            school_id=school_id, year_id=year_id,
            user_id=str(request.user.pk),
            level_name=form.cleaned_data["level_name"],
            annual_fee_fcfa=form.cleaned_data["annual_fee_fcfa"],
            payment_mode=form.cleaned_data["payment_mode"],
        ))
        if result.success:
            messages.success(
                request,
                f"Niveau '{result.level_name}' créé. Ajoutez maintenant les classes.",
            )
            return redirect(
                "economat:add_class",
                school_id=school_id, year_id=year_id, level_id=result.level_id,
            )
        messages.error(request, result.error_message)

    ctx = base_context(
        request, school, year, "niveaux", membership=membership,
        form=form, page_title=f"Niveaux — {year.label}",
    )
    return render(request, "economat/director/add_level.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def add_class(request, school_id: str, year_id: str, level_id: str, membership=None):
    """Création des classes dans un niveau."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
        # ✅ Sécurité IDOR : on filtre level par school_year_id
        level  = LevelModel.objects.get(pk=level_id, school_year_id=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist, LevelModel.DoesNotExist):
        messages.error(request, "Niveau ou année introuvable.")
        return redirect("economat:add_level", school_id=school_id, year_id=year_id)

    form = AddClassForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = get_add_class_use_case().execute(AddClassCommand(
            school_id=school_id, year_id=year_id, level_id=level_id,
            user_id=str(request.user.pk),
            class_name=form.cleaned_data["class_name"],
            capacity=form.cleaned_data["capacity"],
        ))
        if result.success:
            messages.success(
                request,
                f"Classe '{result.class_name}' créée dans {result.level_name}.",
            )
            return redirect(
                "economat:add_class",
                school_id=school_id, year_id=year_id, level_id=level_id,
            )
        messages.error(request, result.error_message)

    classes = ClassModel.objects.filter(level_id=level_id).order_by("name")
    ctx = base_context(
        request, school, year, "niveaux", membership=membership,
        form=form, classes=classes, level=level,
        page_title=f"Classes {level.name} — {year.label}",
    )
    return render(request, "economat/director/add_class.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def configure_pricing(request, school_id: str, year_id: str, membership=None):
    """Configuration des frais de scolarité par niveau (DIRECTOR uniquement)."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "Année ou école introuvable.")
        return redirect("economat:director_dashboard")

    if request.method == "POST":
        form = ConfigurePricingForm(request.POST)
        if form.is_valid():
            result = get_configure_pricing_use_case().execute(ConfigureSchoolPricingCommand(
                school_id=school_id, year_id=year_id,
                level_id=form.cleaned_data["level_id"],
                annual_fee_fcfa=form.cleaned_data["annual_fee_fcfa"],
                payment_mode=form.cleaned_data["payment_mode"],
            ))
            if result.success:
                messages.success(request, f"{result.level_name} : {result.new_fee_fcfa:,} FCFA")
            else:
                messages.error(request, f"{result.error_message}")
        return redirect("economat:configure_pricing", school_id=school_id, year_id=year_id)

    ctx = base_context(
        request, school, year, "tarifs", membership=membership,
        page_title=f"Tarifs — {year.label}",
    )
    return render(request, "economat/director/configure_pricing.html", ctx)
