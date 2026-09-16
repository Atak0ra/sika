"""
interface/econome/views.py — REFONTE (passe par Enrollment + year_id).
"""
from __future__ import annotations
import datetime
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from economat.application.dto import RecordPaymentCommand
from economat.composition import get_record_payment_use_case
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, MembershipModel, PaymentModel, SchoolYearModel,
)
from economat.interface.director.views._shared import _sidebar_levels
from .forms import RecordPaymentForm, StudentSearchForm


def _get_user_active_year(request):
    """Récupère l'école + l'année active de l'utilisateur connecté."""
    m = MembershipModel.objects.filter(user=request.user, is_active=True).first()
    if not m:
        return None, None
    year = SchoolYearModel.objects.filter(school_id=m.school_id, status="ACTIVE").first()
    return m.school, year


def _sidebar_ctx(school, active_year, active_nav: str) -> dict:
    """
    Contexte de la sidebar partagée avec le directeur/la secrétaire
    (_base_director.html) : école, année, arbre niveaux > classes.
    """
    return {
        "school":         school,
        "school_year":    active_year,
        "sidebar_levels": _sidebar_levels(active_year),
        "user_role":      "ECONOME",
        "active_nav":     active_nav,
        "all_years": (
            SchoolYearModel.objects.filter(school_id=school.id).order_by("-label")
            if school else []
        ),
    }


def _payment_modal_ctx(school, active_year) -> dict:
    """
    Contexte nécessaire au partial _payment_modal.html (formulaire
    d'encaissement en modale), inclus sur le dashboard et la liste des
    encaissements — un seul point de saisie, jamais de page dédiée.

    Clé "modal_classes" (pas "classes") : payments_list a déjà sa propre
    variable "classes" pour sa barre de filtres (parfois restreinte par
    niveau) — la modale a besoin de la liste complète, indépendamment du
    filtre actif sur la page qui l'inclut.
    """
    modal_classes = []
    if active_year:
        modal_classes = ClassModel.objects.filter(
            level__school_year=active_year
        ).select_related("level").order_by("level__name", "name")
    return {
        "form":          RecordPaymentForm(country=school.country if school else None),
        "search_form":   StudentSearchForm(),
        "modal_classes": modal_classes,
    }


def _activity_stats(active_year):
    """
    Indicateurs d'activité de l'économe — 3 requêtes SQL, pas de boucle Python.
    Retourne un dict prêt pour le contexte template.
    """
    if not active_year:
        return {}

    today = datetime.date.today()
    base_qs = PaymentModel.objects.filter(
        state="VALID", enrollment__school_year=active_year
    )

    # Agrégats globaux (année entière + aujourd'hui) en une seule passe
    agg = base_qs.aggregate(
        total_year=Sum("amount"),
        count_year=Count("id"),
        students_year=Count("student_id", distinct=True),
        total_today=Sum("amount", filter=Q(payment_date=today)),
        count_today=Count("id",   filter=Q(payment_date=today)),
    )

    # Répartition par moyen de paiement
    METHOD_LABELS = {
        "ESPECES": "Espèces", "MOBILE_MONEY": "Mobile Money",
        "VIREMENT": "Virement", "CHEQUE": "Chèque",
    }
    methods = [
        {
            "key":   r["method"],
            "label": METHOD_LABELS.get(r["method"], r["method"]),
            "total": r["total"] or 0,
            "cnt":   r["cnt"],
        }
        for r in base_qs.values("method").annotate(
            total=Sum("amount"), cnt=Count("id")
        ).order_by("-total")
    ]

    enrolled_count = EnrollmentModel.objects.filter(
        school_year=active_year, status="ACTIVE"
    ).count()

    return {
        "total_year":     agg["total_year"]    or 0,
        "count_year":     agg["count_year"]    or 0,
        "students_year":  agg["students_year"] or 0,
        "total_today":    agg["total_today"]   or 0,
        "count_today":    agg["count_today"]   or 0,
        "methods":        methods,
        "enrolled_count": enrolled_count,
    }


@login_required
def dashboard(request):
    """Redirige vers le nouveau dashboard de collecte (conservation compatibilité)."""
    return redirect("economat:econome_dashboard")


@login_required
def collection_dashboard(request):
    """
    Tableau de bord de collecte de l'économe.

    Indicateurs financiers opérationnels :
      - Encaissé aujourd'hui + cette année + reste à collecter + taux global
      - Collecte par classe triée par reste décroissant (orienté action)
      - Derniers encaissements (10 plus récents)
      - Raccourcis : Encaisser / Voir tous les encaissements
    """
    school, active_year = _get_user_active_year(request)

    stats           = _activity_stats(active_year)
    classes_data    = []
    total_expected  = 0
    total_collected = 0
    recent_payments = []

    if active_year:
        recent_payments = (
            PaymentModel.objects
            .filter(state="VALID", enrollment__school_year=active_year)
            .select_related("student", "enrollment__klass")
            .order_by("-created_at")[:10]
        )

        # ── Collecte par classe — Subquery anti-N+1 ───────────────────────
        from django.db.models import IntegerField, OuterRef, Subquery, Value
        from django.db.models.functions import Coalesce

        paid_subq = (
            PaymentModel.objects
            .filter(enrollment=OuterRef("pk"), state="VALID")
            .values("enrollment")
            .annotate(s=Sum("amount"))
            .values("s")
        )
        enrollments_qs = (
            EnrollmentModel.objects
            .filter(school_year=active_year, status="ACTIVE")
            .select_related("klass", "klass__level")
            .annotate(
                paid_total=Coalesce(
                    Subquery(paid_subq, output_field=IntegerField()),
                    Value(0, output_field=IntegerField()),
                )
            )
        )

        # Agrégation Python par classe (une seule passe)
        class_map: dict = {}
        for enr in enrollments_qs:
            cid = str(enr.klass_id)
            if cid not in class_map:
                class_map[cid] = {
                    "klass": enr.klass, "level": enr.klass.level,
                    "nb": 0, "collected": 0, "expected": 0,
                }
            class_map[cid]["nb"]        += 1
            class_map[cid]["collected"] += enr.paid_total
            class_map[cid]["expected"]  += enr.klass.level.annual_fee

        # Ajouter les FeeItem manuels au prévisionnel par classe
        from economat.infrastructure.models import FeeItemModel
        fee_items_qs = FeeItemModel.objects.filter(
            school_year=active_year, is_active=True, is_system=False,
        )
        total_enrollments = sum(e["nb"] for e in class_map.values())
        for fi in fee_items_qs:
            ca = fi.class_amounts or {}
            if fi.scope_type == "ALL":
                for cid, entry in class_map.items():
                    montant = ca.get(cid, fi.amount)
                    entry["expected"] += montant
            elif fi.scope_type == "CLASSES" and fi.class_ids:
                for cid in fi.class_ids:
                    if cid in class_map:
                        montant = ca.get(cid, fi.amount)
                        class_map[cid]["expected"] += montant

        for entry in class_map.values():
            entry["balance"] = max(entry["expected"] - entry["collected"], 0)
            entry["rate"]    = (
                round(entry["collected"] / entry["expected"] * 100)
                if entry["expected"] else 0
            )
            total_expected  += entry["expected"]
            total_collected += entry["collected"]

        classes_data = sorted(
            class_map.values(), key=lambda x: x["balance"], reverse=True
        )

    total_balance = max(total_expected - total_collected, 0)
    global_rate   = (
        round(total_collected / total_expected * 100) if total_expected else 0
    )

    # ── Ventilation par catégorie (pour les chips KPI) ────────────────────
    category_breakdown = []
    if active_year:
        from economat.application.use_cases.financial_dashboard import (
            _collected_by_category, _fee_item_expected_by_category,
            _CATEGORY_COLORS, _CATEGORY_LABELS,
        )
        from economat.infrastructure.models import EnrollmentModel as _EM
        active_enrollments = list(_EM.objects.filter(
            school_year=active_year, status="ACTIVE"
        ).only("level_id", "klass_id"))

        # scol_expected dérivé via _fee_item_expected_by_category
        # (le calcul détaillé se fait dans febc)

        cbc = _collected_by_category(str(active_year.id))
        febc = _fee_item_expected_by_category(str(active_year.id), active_enrollments)

        scol_col = cbc.get("SCOLARITE", 0)
        scol_exp = total_expected - sum(febc.values())
        if scol_exp > 0 or scol_col > 0:
            category_breakdown.append({
                "category": "SCOLARITE", "label": "Scolarité",
                "collected": scol_col, "expected": scol_exp,
                "rate": round(scol_col / scol_exp * 100) if scol_exp else 0,
                "color": _CATEGORY_COLORS["SCOLARITE"],
            })
        for cat, exp in sorted(febc.items()):
            coll = cbc.get(cat, 0)
            category_breakdown.append({
                "category": cat, "label": _CATEGORY_LABELS.get(cat, cat),
                "collected": coll, "expected": exp,
                "rate": round(coll / exp * 100) if exp else 0,
                "color": _CATEGORY_COLORS.get(cat, "#6b7280"),
            })

    ctx = _sidebar_ctx(school, active_year, "dashboard_econome")
    ctx.update(_payment_modal_ctx(school, active_year))
    ctx.update({
        "stats":              stats,
        "classes_data":       classes_data,
        "total_expected":     total_expected,
        "total_collected":    total_collected,
        "total_balance":      total_balance,
        "global_rate":        global_rate,
        "recent_payments":    recent_payments,
        "category_breakdown": category_breakdown,
        "page_title":         "Tableau de bord — Économe",
    })
    return render(request, "economat/econome/collection_dashboard.html", ctx)


@login_required
def payments_list(request):
    """
    Liste paginée des encaissements de l'économe avec filtres :
      - date_from / date_to  (défaut = aujourd'hui)
      - level                (niveau scolaire)
      - class                (classe)
    Bandeau récap dynamique (total + nombre) qui suit les filtres actifs.
    Lecture seule — aucune action (annulation, etc.) disponible ici.
    """
    school, active_year = _get_user_active_year(request)

    # ── Lecture des paramètres GET ────────────────────────────────────────────
    today       = datetime.date.today()
    date_from_s = request.GET.get("date_from", "").strip()
    date_to_s   = request.GET.get("date_to",   "").strip()
    level_id    = request.GET.get("level",  "").strip()
    class_id    = request.GET.get("class",  "").strip()

    # "date_from" présent dans la query string → l'utilisateur a explicitement
    # choisi une plage (même vide = tout l'historique de l'année). Un filtre
    # niveau/classe sans date (ex. clic sur une classe depuis la sidebar) est
    # traité pareil : l'intention est de voir l'historique de cette classe,
    # pas seulement ses encaissements du jour. Absent de tout ça → première
    # visite, on affiche aujourd'hui par défaut.
    params_in_qs = "date_from" in request.GET or bool(level_id) or bool(class_id)

    # Valeurs par défaut : aujourd'hui dans les deux champs
    date_from = today
    date_to   = today
    if params_in_qs:
        # L'utilisateur a soumis le formulaire ou cliqué "Tout l'historique"
        if date_from_s:
            try:
                date_from = datetime.date.fromisoformat(date_from_s)
            except ValueError:
                pass
        else:
            # Champ vide explicitement → pas de borne inférieure (début de l'année)
            date_from = None
        if date_to_s:
            try:
                date_to = datetime.date.fromisoformat(date_to_s)
            except ValueError:
                pass
        else:
            date_to = None

    # Normalise l'ordre si l'utilisateur a inversé les dates (seulement si les deux sont définies)
    if date_from is not None and date_to is not None and date_from > date_to:
        date_from, date_to = date_to, date_from

    # ── Queryset de base ──────────────────────────────────────────────────────
    qs = PaymentModel.objects.none()
    if active_year:
        qs = (
            PaymentModel.objects
            .filter(state="VALID", enrollment__school_year=active_year)
            .select_related(
                "student",
                "enrollment__klass",
                "enrollment__klass__level",
            )
        )
        # Filtres date (None = pas de borne)
        if date_from is not None:
            qs = qs.filter(payment_date__gte=date_from)
        if date_to is not None:
            qs = qs.filter(payment_date__lte=date_to)
        # Filtres niveau / classe
        if level_id:
            qs = qs.filter(enrollment__klass__level_id=level_id)
        if class_id:
            qs = qs.filter(enrollment__klass_id=class_id)
        qs = qs.order_by("-payment_date", "-created_at")

    # ── Bandeau récap (total + nb) — agrégat SQL sur la sélection filtrée ────
    recap = qs.aggregate(total=Sum("amount"), count=Count("id"))
    recap_total = recap["total"] or 0
    recap_count = recap["count"] or 0

    # ── Pagination ────────────────────────────────────────────────────────────
    paginator = Paginator(qs, 30)
    page_obj  = paginator.get_page(request.GET.get("page", 1))

    # ── Selects filtres (niveau + classes de l'année active) ─────────────────
    levels  = []
    classes = []
    if active_year:
        levels = LevelModel.objects.filter(
            school_year=active_year
        ).order_by("name")
        classes = ClassModel.objects.filter(
            level__school_year=active_year
        ).select_related("level").order_by("level__name", "name")
        # Si un niveau est sélectionné, on restreint les classes disponibles
        if level_id:
            classes = classes.filter(level_id=level_id)

    # Valeurs affichées dans les inputs date (chaîne vide si pas de borne)
    f_date_from = date_from.isoformat() if date_from else ""
    f_date_to   = date_to.isoformat()   if date_to   else ""
    is_today    = (date_from == today and date_to == today and not level_id and not class_id)

    # Nom lisible du filtre actif (classe cliquée depuis la sidebar, etc.)
    # — affiché explicitement dans l'en-tête plutôt qu'un vague "· filtré".
    active_filter_label = ""
    if class_id:
        active_klass = ClassModel.objects.filter(pk=class_id).select_related("level").first()
        if active_klass:
            active_filter_label = f"{active_klass.level.name} {active_klass.name}"
    elif level_id:
        active_level = LevelModel.objects.filter(pk=level_id).first()
        if active_level:
            active_filter_label = active_level.name

    ctx = _sidebar_ctx(school, active_year, "encaissements")
    ctx.update(_payment_modal_ctx(school, active_year))
    ctx.update({
        "page_obj":     page_obj,
        "paginator":    paginator,
        "recap_total":  recap_total,
        "recap_count":  recap_count,
        "levels":       levels,
        "classes":      classes,
        # Valeurs des filtres actifs (pour re-remplir le formulaire)
        "f_date_from":  f_date_from,
        "f_date_to":    f_date_to,
        "f_level_id":   level_id,
        "f_class_id":   class_id,
        "is_today":     is_today,
        "active_filter_label": active_filter_label,
        "page_title":   "Encaissements",
    })
    return render(request, "economat/econome/payments_list.html", ctx)


@login_required
def record_payment(request):
    """
    Enregistrement d'un encaissement — POST uniquement, soumis depuis la
    modale d'encaissement (partial _payment_modal.html, incluse sur le
    dashboard et la liste des encaissements). Pas de page dédiée : un GET
    ramène simplement à l'accueil.

    Le form id="paymentForm" et le name record_payment sont conservés
    pour la compatibilité avec offline-sync.js.

    En cas d'erreur, on redirige vers le référent (ou le dashboard) avec un
    message — la modale ne se rouvre pas pré-remplie (compromis assumé :
    évite de refaire tout le flux en AJAX pour le cas d'erreur, rare).
    """
    school, active_year = _get_user_active_year(request)
    fallback_url = reverse("economat:econome_dashboard")
    referer = request.META.get("HTTP_REFERER", "")
    if referer and request.get_host() in referer:
        fallback_url = referer

    if request.method == "GET":
        return redirect("economat:econome_dashboard")

    # ── POST : enregistrer le paiement ───────────────────────────────────────
    form = RecordPaymentForm(request.POST, country=school.country if school else None)
    if not form.is_valid():
        first_error = next(iter(form.errors.values()))[0]
        messages.error(request, first_error)
        return redirect(fallback_url)
    if not active_year:
        messages.error(request, "Aucune année scolaire active. Contactez le directeur.")
        return redirect(fallback_url)

    command = RecordPaymentCommand(
        student_id=form.cleaned_data["student_id"],
        year_id=str(active_year.id),
        amount_fcfa=form.cleaned_data["amount_fcfa"],
        payment_date=form.cleaned_data["payment_date"],
        method=form.cleaned_data["method"],
        recorded_by=request.user.username,
        notes=form.cleaned_data.get("notes", ""),
        paid_by=form.cleaned_data.get("paid_by", ""),
        mobile_operator=form.cleaned_data.get("mobile_operator", ""),
        mobile_number=form.cleaned_data.get("mobile_number", ""),
        fee_item_id=request.POST.get("fee_item_id", ""),
    )
    result = get_record_payment_use_case().execute(command)
    if result.success:
        messages.success(
            request,
            f"Reçu {result.receipt_number} | {result.amount_paid:,} FCFA | "
            f"{result.student_name} | {result.payment_status}",
        )
        return redirect("economat:receipt_view", payment_id=result.payment_id)
    messages.error(request, f"{result.error_message}")
    return redirect(fallback_url)


@login_required
@require_GET
def receipt_view(request, payment_id: str):
    """
    Page de reçu dédiée — imprimable / PDF.
    Charge le paiement par ID, vérifie l'appartenance à l'école de l'économe,
    et rend un reçu propre prêt à imprimer.
    """
    school, active_year = _get_user_active_year(request)

    # Sécurité IDOR : le paiement doit appartenir à l'école de l'économe
    try:
        payment = (
            PaymentModel.objects
            .select_related(
                "student",
                "enrollment__klass",
                "enrollment__klass__level",
                "enrollment__school_year",
                "enrollment__school_year__school",
            )
            .get(pk=payment_id)
        )
    except PaymentModel.DoesNotExist:
        from django.http import Http404
        raise Http404("Reçu introuvable.")

    # Vérification que ce paiement appartient bien à l'école de l'utilisateur
    if school and str(payment.enrollment.school_year.school_id) != str(school.id):
        from django.http import Http404
        raise Http404("Reçu introuvable.")

    # Méthode de paiement lisible
    method_labels = {
        "ESPECES":      "Espèces",
        "MOBILE_MONEY": "Mobile Money",
        "VIREMENT":     "Virement bancaire",
        "CHEQUE":       "Chèque",
    }

    return render(request, "economat/econome/receipt.html", {
        "payment":       payment,
        "school":        payment.enrollment.school_year.school,
        "school_year":   payment.enrollment.school_year,
        "klass":         payment.enrollment.klass,
        "level":         payment.enrollment.klass.level,
        "method_label":  method_labels.get(payment.method, payment.method),
        "page_title":    f"Reçu {payment.receipt_number}",
    })


@login_required
@require_GET
def student_search_api(request):
    """Recherche AJAX : renvoie les inscriptions actives de l'année active."""
    query    = request.GET.get("q", "").strip()
    class_id = request.GET.get("class_id", "").strip()

    if len(query) < 1:
        return JsonResponse({"results": []})

    _, active_year = _get_user_active_year(request)
    if not active_year:
        return JsonResponse({"results": []})

    qs = EnrollmentModel.objects.filter(
        school_year=active_year, status="ACTIVE"
    ).filter(
        Q(student__last_name__icontains=query) | Q(student__first_name__icontains=query)
    ).select_related("student", "klass")

    if class_id:
        qs = qs.filter(klass_id=class_id)

    results = [
        {
            "id":        str(e.student_id),
            "name":      f"{e.student.first_name} {e.student.last_name.upper()}",
            "class":     e.klass.name if e.klass_id else "",
            "matricule": e.student.matricule or "",
        }
        for e in qs[:10]
    ]
    return JsonResponse({"results": results})

@login_required
@require_GET
def fee_items_api(request):
    """
    AJAX : retourne les postes de frais dus pour un élève.
    ?student_id=<uuid>
    Utilisé par la modale d'encaissement pour peupler le dropdown.
    """
    student_id = request.GET.get("student_id", "").strip()
    if not student_id:
        return JsonResponse({"lines": []})

    _, active_year = _get_user_active_year(request)
    if not active_year:
        return JsonResponse({"lines": []})

    from economat.composition import get_list_payable_items_use_case
    result = get_list_payable_items_use_case().execute(
        student_id=student_id, year_id=str(active_year.id)
    )
    if not result.success:
        return JsonResponse({"lines": [], "error": result.error_message})

    lines = [
        {
            "fee_item_id":    ln.fee_item_id,
            "name":           ln.name,
            "category_label": ln.category_label,
            "remaining":      ln.remaining,
            "amount_due":     ln.amount_due,
            "amount_paid":    ln.amount_paid,
            "payment_status": ln.payment_status,
            "is_system":      ln.is_system,
        }
        for ln in result.lines
        if ln.remaining > 0   # n'afficher que ce qui reste à payer
    ]
    return JsonResponse({"lines": lines})




# ── Synchronisation offline batch ─────────────────────────────────────────────

@login_required
@require_POST
def sync_payments(request):
    """
    Endpoint de synchronisation batch pour les paiements enregistrés offline.

    Reçoit : {"payments": [{client_uuid, student_id, year_id, amount_fcfa,
                             payment_date, method, notes, paid_by,
                             receipt_number, installment_label}, ...]}

    Retourne : {"results": [{client_uuid, status: "synced"|"duplicate"|"failed",
                              receipt_number?, error?}]}

    Chaque item est traité indépendamment dans sa propre transaction pour éviter
    qu'un échec unique ne bloque les autres.

    Idempotence : le RecordPaymentUseCase détecte les client_uuid déjà en base
    et retourne status="duplicate" sans créer de doublon.
    """
    if request.content_type and "application/json" not in request.content_type:
        return JsonResponse({"error": "Content-Type application/json requis."}, status=400)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "JSON invalide."}, status=400)

    payments_data = body.get("payments", [])
    if not isinstance(payments_data, list):
        return JsonResponse({"error": "payments doit être une liste."}, status=400)

    if len(payments_data) > 100:
        return JsonResponse({"error": "Trop d'items (max 100 par batch)."}, status=400)

    _, active_year = _get_user_active_year(request)
    results = []

    for item in payments_data:
        client_uuid = item.get("client_uuid", "")
        if not client_uuid:
            results.append({"client_uuid": "", "status": "failed",
                             "error": "client_uuid manquant."})
            continue

        try:
            # Validation minimale des champs obligatoires
            amount = int(item.get("amount_fcfa", 0))
            if amount <= 0:
                raise ValueError("Montant invalide.")

            payment_date_str = item.get("payment_date", "")
            payment_date = datetime.date.fromisoformat(payment_date_str)

            method = item.get("method", "ESPECES")
            if method not in ("ESPECES", "MOBILE_MONEY", "VIREMENT", "CHEQUE"):
                raise ValueError(f"Méthode inconnue : {method}")

            year_id = item.get("year_id", "")
            if not year_id and active_year:
                year_id = str(active_year.id)
            if not year_id:
                raise ValueError("year_id manquant et aucune année active.")

            cmd = RecordPaymentCommand(
                student_id=item.get("student_id", ""),
                year_id=year_id,
                amount_fcfa=amount,
                payment_date=payment_date,
                method=method,
                recorded_by=request.user.username,
                notes=item.get("notes", ""),
                paid_by=item.get("paid_by", ""),
                receipt_number=item.get("receipt_number", ""),
                installment_label=item.get("installment_label", ""),
                client_uuid=client_uuid,
                mobile_operator=item.get("mobile_operator", ""),
                mobile_number=item.get("mobile_number", ""),
            )

            with transaction.atomic():
                result = get_record_payment_use_case().execute(cmd)

            if not result.success:
                results.append({
                    "client_uuid": client_uuid,
                    "status": "failed",
                    "error": result.error_message,
                })
            elif result.payment_status == "already_synced":
                results.append({
                    "client_uuid":    client_uuid,
                    "status":         "duplicate",
                    "receipt_number": result.receipt_number,
                })
            else:
                results.append({
                    "client_uuid":    client_uuid,
                    "status":         "synced",
                    "receipt_number": result.receipt_number,
                    "student_name":   result.student_name,
                    "amount_paid":    result.amount_paid,
                })

        except (ValueError, TypeError, KeyError) as e:
            results.append({
                "client_uuid": client_uuid,
                "status":      "failed",
                "error":       f"Validation : {e}",
            })
        except Exception as e:  # noqa: BLE001
            results.append({
                "client_uuid": client_uuid,
                "status":      "failed",
                "error":       f"Erreur serveur : {type(e).__name__}",
            })

    return JsonResponse({"results": results})
