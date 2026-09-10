"""
interface/econome/views.py — REFONTE (passe par Enrollment + year_id).
"""
from __future__ import annotations
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from economat.application.dto import RecordPaymentCommand
from economat.composition import get_record_payment_use_case
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, MembershipModel, PaymentModel, SchoolYearModel,
)
from .forms import RecordPaymentForm, StudentSearchForm


def _get_user_active_year(request):
    """Récupère l'école + l'année active de l'utilisateur connecté."""
    m = MembershipModel.objects.filter(user=request.user, is_active=True).first()
    if not m:
        return None, None
    year = SchoolYearModel.objects.filter(school_id=m.school_id, status="ACTIVE").first()
    return m.school, year


@login_required
def dashboard(request):
    school, active_year = _get_user_active_year(request)
    recent_payments = []
    if active_year:
        recent_payments = (
            PaymentModel.objects
            .filter(state="VALID", enrollment__school_year=active_year)
            .select_related("student", "enrollment__klass")
            .order_by("-created_at")[:20]
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
        "page_title":      "Saisie des encaissements",
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
    )
    result = get_record_payment_use_case().execute(command)
    if result.success:
        messages.success(
            request,
            f"✅ Reçu {result.receipt_number} | {result.amount_paid:,} FCFA | "
            f"{result.student_name} | {result.payment_status}",
        )
        return redirect("economat:econome_dashboard")
    messages.error(request, f"❌ {result.error_message}")
    return render(request, "economat/econome/dashboard.html", {
        "form": form, "search_form": StudentSearchForm(),
        "page_title": "Saisie des encaissements",
    })


@login_required
@require_GET
def student_search_api(request):
    """Recherche AJAX : renvoie les inscriptions actives de l'année active."""
    query   = request.GET.get("q", "").strip()
    class_id = request.GET.get("class_id", "").strip()

    if len(query) < 2:
        return JsonResponse({"results": []})

    _, active_year = _get_user_active_year(request)
    if not active_year:
        return JsonResponse({"results": []})

    from django.db.models import Q
    qs = EnrollmentModel.objects.filter(
        school_year=active_year, status="ACTIVE"
    ).filter(
        Q(student__last_name__icontains=query) | Q(student__first_name__icontains=query)
    ).select_related("student", "klass")

    if class_id:
        qs = qs.filter(klass_id=class_id)

    results = [
        {
            "id": str(e.student_id),
            "name": f"{e.student.first_name} {e.student.last_name.upper()}",
            "class": e.klass.name if e.klass_id else "",
        }
        for e in qs[:10]
    ]
    return JsonResponse({"results": results})
