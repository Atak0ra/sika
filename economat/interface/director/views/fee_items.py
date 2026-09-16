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
    # Portée : ALL (toutes les classes) ou CLASSES (sélection)
    scope_type = _forms.ChoiceField(
        label="Portée",
        choices=[("ALL", "Toutes les classes de l'école"),
                 ("CLASSES", "Classes précises (à sélectionner)")],
        widget=_forms.RadioSelect(), initial="ALL",
    )
    # Sélection multiple de classes — visible seulement si scope_type=CLASSES
    class_ids = _forms.MultipleChoiceField(
        label="Classes concernées", choices=[], required=False,
        widget=_forms.CheckboxSelectMultiple(),
    )
    is_mandatory = _forms.BooleanField(label="Frais obligatoire", required=False, initial=True)
    # class_amounts soumis comme JSON dans un champ caché (rempli par le JS du formulaire)
    class_amounts_json = _forms.CharField(required=False, widget=_forms.HiddenInput())

    def __init__(self, *args, year_orm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if year_orm:
            from economat.infrastructure.models import ClassModel
            classes = ClassModel.objects.filter(
                level__school_year_id=year_orm.id
            ).select_related("level").order_by("level__name", "name")
            self.fields["class_ids"].choices = [
                (str(c.id), f"{c.level.name} — {c.name}") for c in classes
            ]

    def clean(self):
        data = super().clean()
        scope = data.get("scope_type")
        selected_class_ids = set(data.get("class_ids") or [])

        if scope == "CLASSES" and not selected_class_ids:
            self.add_error("class_ids", "Sélectionnez au moins une classe.")
        if not data.get("nb_months"):
            data["nb_months"] = 10

        # Parser les surcharges JSON
        import json
        raw = data.get("class_amounts_json", "").strip()
        try:
            parsed = json.loads(raw) if raw else {}
            data["class_amounts"] = {
                k: int(v) for k, v in parsed.items() if str(v).isdigit() and int(v) > 0
            }
        except (json.JSONDecodeError, ValueError):
            data["class_amounts"] = {}

        # Cohérence : si portée = CLASSES, les surcharges ne peuvent cibler que
        # les classes sélectionnées dans la portée.
        if scope == "CLASSES" and data.get("class_amounts") and selected_class_ids:
            out_of_scope = set(data["class_amounts"].keys()) - selected_class_ids
            if out_of_scope:
                # Nettoyer silencieusement les surcharges hors portée
                # (le JS ne devrait pas en produire, mais par sécurité)
                data["class_amounts"] = {
                    k: v for k, v in data["class_amounts"].items()
                    if k in selected_class_ids
                }

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
        .select_related("level")
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
        result = get_create_fee_item_use_case().execute(CreateFeeItemCommand(
            school_year_id=year_id, name=d["name"], category=d["category"],
            amount_fcfa=d["amount_fcfa"], scope_type=d["scope_type"],
            class_ids=d.get("class_ids") or [],
            class_amounts=d.get("class_amounts") or {},
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
        "name":         fee_item.name,
        "category":     fee_item.category,
        "amount_fcfa":  fee_item.amount,
        "payment_mode": fee_item.payment_mode,
        "nb_months":    fee_item.nb_months,
        "is_mandatory": fee_item.is_mandatory,
        "scope_type":   fee_item.scope_type,
        "class_ids":    fee_item.class_ids or [],
        "class_amounts": fee_item.class_amounts or {},
    }
    form = FeeItemForm(request.POST or None, initial=initial, year_orm=year)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        result = get_update_fee_item_use_case().execute(UpdateFeeItemCommand(
            fee_item_id=fee_item_id, name=d["name"], amount_fcfa=d["amount_fcfa"],
            class_amounts=d.get("class_amounts") or {},
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

