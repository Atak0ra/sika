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
from django.views.decorators.http import require_GET, require_POST

from economat.application.dto import RecordPaymentCommand
from economat.composition import get_record_payment_use_case
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, MembershipModel, PaymentModel, SchoolYearModel,
)
from .forms import RecordPaymentForm, StudentSearchForm


def _get_user_active_year(request):
    """Récupère l'école + l'année active de l'utilisateur connecté."""
    m = MembershipModel.objects.filter(user=request.user, is_active=True).first()
    if not m:
        return None, None
    year = SchoolYearModel.objects.filter(school_id=m.school_id, status="ACTIVE").first()
    return m.school, year


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
    school, active_year = _get_user_active_year(request)
    recent_payments = []
    if active_year:
        recent_payments = (
            PaymentModel.objects
            .filter(state="VALID", enrollment__school_year=active_year)
            .select_related("student", "enrollment__klass")
            .order_by("-created_at")[:10]
        )
    classes = []
    if active_year:
        classes = ClassModel.objects.filter(
            level__school_year=active_year
        ).select_related("level").order_by("level__name", "name")

    return render(request, "economat/econome/dashboard.html", {
        "form":            RecordPaymentForm(initial={"year_id": str(active_year.id)} if active_year else {}),
        "search_form":     StudentSearchForm(),
        "recent_payments": recent_payments,
        "school":          school,
        "school_year":     active_year,
        "classes":         classes,
        "stats":           _activity_stats(active_year),
        "page_title":      "Saisie des encaissements",
    })


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

    # "date_from" et "date_to" présents dans la query string → l'utilisateur
    # a explicitement choisi une plage (même vide = tout l'historique de l'année).
    # Absents → première visite, on affiche aujourd'hui par défaut.
    params_in_qs = "date_from" in request.GET

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

    return render(request, "economat/econome/payments_list.html", {
        "page_obj":     page_obj,
        "paginator":    paginator,
        "school":       school,
        "school_year":  active_year,
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
        "page_title":   "Encaissements",
    })


@login_required
@require_POST
def record_payment(request):
    form = RecordPaymentForm(request.POST)
    school, active_year = _get_user_active_year(request)
    if not form.is_valid():
        return render(request, "economat/econome/dashboard.html", {
            "form": form, "search_form": StudentSearchForm(),
            "page_title": "Saisie des encaissements",
        })
    if not active_year:
        messages.error(request, "Aucune année scolaire active. Contactez le directeur.")
        return redirect("economat:econome_dashboard")

    command = RecordPaymentCommand(
        student_id=form.cleaned_data["student_id"],
        year_id=str(active_year.id),
        amount_fcfa=form.cleaned_data["amount_fcfa"],
        payment_date=form.cleaned_data["payment_date"],
        method=form.cleaned_data["method"],
        recorded_by=request.user.username,
        notes=form.cleaned_data.get("notes", ""),
        paid_by=form.cleaned_data.get("paid_by", ""),
    )
    result = get_record_payment_use_case().execute(command)
    if result.success:
        messages.success(
            request,
            f"Reçu {result.receipt_number} | {result.amount_paid:,} FCFA | "
            f"{result.student_name} | {result.payment_status}",
        )
        return redirect("economat:econome_dashboard")
    messages.error(request, f"{result.error_message}")
    return render(request, "economat/econome/dashboard.html", {
        "form": form, "search_form": StudentSearchForm(),
        "page_title": "Saisie des encaissements",
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
