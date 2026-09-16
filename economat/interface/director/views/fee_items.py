"""
interface/director/views/fee_items.py
=======================================
Vues de gestion des postes de frais de scolarité.
Accessibles à DIRECTOR, SECRETARY et ECONOME.
"""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django import forms as _forms

from economat.application.dto import (
    CreateFeeItemCommand, DeactivateFeeItemCommand, UpdateFeeItemCommand,
)
from economat.composition import (
    get_create_fee_item_use_case, get_deactivate_fee_item_use_case,
    get_update_fee_item_use_case,
)
from economat.domain.fee.value_objects import FeeCategory
from economat.domain.identity.value_objects import Role
from economat.infrastructure.models import FeeItemModel, SchoolModel, SchoolYearModel
from economat.interface.decorators import require_membership, require_role
from ._shared import base_context


_PAYMENT_MODE_CHOICES = [
    ("UNIQUE",   "Paiement unique"),
    ("MENSUEL",  "Mensualités"),
    ("TRANCHES", "3 tranches (40 % + 30 % + 30 %)"),
]


class FeeItemForm(_forms.Form):
    name = _forms.CharField(
        label="Libellé", max_length=200,
        widget=_forms.TextInput(attrs={"class": "form-input",
                                       "placeholder": "Ex : Cantine T1, Sortie zoo…"}),
    )
    category = _forms.ChoiceField(
        label="Catégorie", choices=FeeCategory.manual_choices(),
        widget=_forms.Select(attrs={"class": "form-select"}),
    )
    amount_fcfa = _forms.IntegerField(
        label="Montant (FCFA)", min_value=1,
        widget=_forms.NumberInput(attrs={"class": "form-input", "placeholder": "Ex : 15000"}),
    )
    payment_mode = _forms.ChoiceField(
        label="Mode de paiement", choices=_PAYMENT_MODE_CHOICES,
        widget=_forms.Select(attrs={"class": "form-select"}), initial="UNIQUE",
    )
    nb_months = _forms.IntegerField(
        label="Nombre de mensualités", min_value=1, max_value=24, initial=10, required=False,
        widget=_forms.NumberInput(attrs={"class": "form-input",
                                         "placeholder": "Ex : 10", "min": "1", "max": "24"}),
        help_text="Uniquement si mode = Mensualités.",
    )
    scope_type = _forms.ChoiceField(
        label="Portée",
        choices=[("LEVEL", "Tous les élèves du niveau"), ("CLASS", "Une classe précise")],
        widget=_forms.RadioSelect(), initial="LEVEL",
    )
    target_level_id = _forms.ChoiceField(
        label="Niveau", choices=[], required=False,
        widget=_forms.Select(attrs={"class": "form-select"}),
    )
    target_class_id = _forms.ChoiceField(
        label="Classe", choices=[], required=False,
        widget=_forms.Select(attrs={"class": "form-select"}),
    )
    is_mandatory = _forms.BooleanField(label="Frais obligatoire", required=False, initial=True)

    def __init__(self, *args, year_orm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if year_orm:
            from economat.infrastructure.models import ClassModel, LevelModel
            levels = LevelModel.objects.filter(school_year_id=year_orm.id).order_by("name")
            self.fields["target_level_id"].choices = [("", "— Choisir —")] + [
                (str(l.id), l.name) for l in levels
            ]
            classes = ClassModel.objects.filter(
                level__school_year_id=year_orm.id
            ).select_related("level").order_by("level__name", "name")
            self.fields["target_class_id"].choices = [("", "— Choisir —")] + [
                (str(c.id), f"{c.level.name} — {c.name}") for c in classes
            ]

    def clean(self):
        data = super().clean()
        scope = data.get("scope_type")
        if scope == "LEVEL" and not data.get("target_level_id"):
            self.add_error("target_level_id", "Choisissez un niveau.")
        if scope == "CLASS" and not data.get("target_class_id"):
            self.add_error("target_class_id", "Choisissez une classe.")
        if not data.get("nb_months"):
            data["nb_months"] = 10
        return data


# ── Vues ──────────────────────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY, Role.ECONOME)
def fee_items_list(request, school_id: str, year_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels").get(pk=year_id)
    except Exception:
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    items = (
        FeeItemModel.objects
        .filter(school_year_id=year_id)
        .select_related("level", "klass", "klass__level")
        .order_by("is_system", "category", "name")
    )
    ctx = base_context(request, school, year, "frais", membership=membership,
                       fee_items=items, page_title=f"Frais — {year.label}")
    return render(request, "economat/director/fee_items_list.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY, Role.ECONOME)
def fee_item_create(request, school_id: str, year_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
    except Exception:
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    form = FeeItemForm(request.POST or None, year_orm=year)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        scope_type = d["scope_type"]
        target_id  = d["target_level_id"] if scope_type == "LEVEL" else d["target_class_id"]
        result = get_create_fee_item_use_case().execute(CreateFeeItemCommand(
            school_year_id=year_id, name=d["name"], category=d["category"],
            amount_fcfa=d["amount_fcfa"], scope_type=scope_type, target_id=target_id,
            payment_mode=d["payment_mode"], nb_months=d["nb_months"],
            is_mandatory=d.get("is_mandatory", True), created_by=request.user.username,
        ))
        if result.success:
            messages.success(request, f"Poste « {result.name} » créé.")
            return redirect("economat:fee_items_list", school_id=school_id, year_id=year_id)
        messages.error(request, result.error_message)

    ctx = base_context(request, school, year, "frais", membership=membership,
                       form=form, page_title="Nouveau poste de frais")
    return render(request, "economat/director/fee_item_form.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY, Role.ECONOME)
def fee_item_edit(request, school_id: str, year_id: str, fee_item_id: str, membership=None):
    try:
        school   = SchoolModel.objects.get(pk=school_id)
        year     = SchoolYearModel.objects.get(pk=year_id)
        fee_item = FeeItemModel.objects.get(pk=fee_item_id, school_year_id=year_id)
    except Exception:
        messages.error(request, "Poste de frais introuvable.")
        return redirect("economat:fee_items_list", school_id=school_id, year_id=year_id)

    if fee_item.is_system:
        messages.error(request, "La ligne scolarité se configure via les tarifs du niveau.")
        return redirect("economat:fee_items_list", school_id=school_id, year_id=year_id)

    initial = {
        "name": fee_item.name, "category": fee_item.category,
        "amount_fcfa": fee_item.amount, "payment_mode": fee_item.payment_mode,
        "nb_months": fee_item.nb_months, "is_mandatory": fee_item.is_mandatory,
        "scope_type": fee_item.scope_type,
        "target_level_id": str(fee_item.level_id) if fee_item.level_id else "",
        "target_class_id": str(fee_item.klass_id) if fee_item.klass_id else "",
    }
    form = FeeItemForm(request.POST or None, initial=initial, year_orm=year)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        result = get_update_fee_item_use_case().execute(UpdateFeeItemCommand(
            fee_item_id=fee_item_id, name=d["name"], amount_fcfa=d["amount_fcfa"],
            payment_mode=d["payment_mode"], nb_months=d["nb_months"],
            is_mandatory=d.get("is_mandatory", True), updated_by=request.user.username,
        ))
        if result.success:
            messages.success(request, f"Poste « {result.name} » mis à jour.")
            return redirect("economat:fee_items_list", school_id=school_id, year_id=year_id)
        messages.error(request, result.error_message)

    ctx = base_context(request, school, year, "frais", membership=membership,
                       form=form, fee_item=fee_item, page_title=f"Modifier — {fee_item.name}")
    return render(request, "economat/director/fee_item_form.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY, Role.ECONOME)
def fee_item_deactivate(request, school_id: str, year_id: str, fee_item_id: str, membership=None):
    if request.method != "POST":
        return redirect("economat:fee_items_list", school_id=school_id, year_id=year_id)
    result = get_deactivate_fee_item_use_case().execute(
        DeactivateFeeItemCommand(fee_item_id=fee_item_id, updated_by=request.user.username)
    )
    if result.success:
        messages.success(request, f"Poste « {result.name} » archivé.")
    else:
        messages.error(request, result.error_message)
    return redirect("economat:fee_items_list", school_id=school_id, year_id=year_id)

