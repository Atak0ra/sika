"""
interface/parent_portal/views.py
===================================
Vues du portail de paiement parent — AUCUNE authentification.

Flux :
  1. search → identifie l'élève → redirige vers portal_dashboard
  2. portal_dashboard → espace parent (solde, 2 boutons : Payer / Historique)
  3. pay → montant + opérateur → attente → reçu
  4. portal_history → historique enrichi (tous paiements, liens reçus PDF)

Confirmation : polling via l'endpoint status (Samirpay/CRPay).
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET

from .forms import OnlinePaymentForm, SchoolMatriculeForm

GENERIC_NOT_FOUND = "École ou matricule introuvable. Vérifiez votre saisie."


def _get_enrollment_and_balance(student_id: str):
    """Retourne (enrollment_actif, total_payé_VALID, solde) pour un student_id."""
    from django.db.models import Sum
    from economat.infrastructure.models import EnrollmentModel
    enrollment = (
        EnrollmentModel.objects
        .select_related("level", "klass", "school_year")
        .filter(student_id=student_id, school_year__status="ACTIVE")
        .first()
    )
    if enrollment is None:
        return None, 0, None
    paid = (
        enrollment.payments.filter(state="VALID")
        .aggregate(total=Sum("amount"))["total"] or 0
    )
    balance = max(enrollment.level.annual_fee - paid, 0)
    return enrollment, paid, balance


def search(request):
    """GET : formulaire vide. POST : recherche exacte → espace parent."""
    if request.method == "POST":
        form = SchoolMatriculeForm(request.POST)
        if form.is_valid():
            school = form.cleaned_data["school"]
            matricule = form.cleaned_data["matricule"]

            from economat.infrastructure.models import StudentModel
            student = StudentModel.objects.filter(
                school_id=school.id, matricule=matricule,
            ).first()

            if student is not None:
                request.session["parent_portal_student_id"] = str(student.id)
                request.session["parent_portal_school_id"] = str(school.id)
                return redirect(
                    "economat:parent_portal_dashboard",
                    student_id=str(student.id),
                )

            form.add_error(None, GENERIC_NOT_FOUND)
    else:
        form = SchoolMatriculeForm()

    return render(request, "economat/parent_portal/search.html", {
        "form": form, "page_title": "Espace parent — Sukulu",
    })


def portal_dashboard(request, student_id: str):
    """Espace parent : carte élève, solde/progression, 2 boutons Payer/Historique."""
    if request.session.get("parent_portal_student_id") != str(student_id):
        return redirect("economat:parent_portal_search")

    from economat.infrastructure.models import StudentModel
    student = get_object_or_404(
        StudentModel.objects.select_related("school", "school__country"),
        pk=student_id,
    )
    enrollment, paid, balance = _get_enrollment_and_balance(student_id)
    annual_fee = enrollment.level.annual_fee if enrollment else 0
    pct_paid = int(paid / annual_fee * 100) if annual_fee else 0

    return render(request, "economat/parent_portal/dashboard.html", {
        "student": student, "enrollment": enrollment,
        "annual_fee": annual_fee, "paid": paid,
        "balance": balance, "pct_paid": pct_paid,
        "page_title": f"Espace parent — {student.first_name} {student.last_name.upper()}",
    })


def pay(request, student_id: str | None = None):
    """
    Écran montant + opérateur.
    Accepte student_id depuis l'URL (nouveau flux depuis dashboard)
    ou depuis la session (compatibilité retour arrière).
    """
    sid = str(student_id) if student_id else request.session.get("parent_portal_student_id")
    school_id = request.session.get("parent_portal_school_id")
    if not sid or not school_id:
        return redirect("economat:parent_portal_search")

    from economat.infrastructure.models import EnrollmentModel, StudentModel
    try:
        student = StudentModel.objects.select_related("school", "school__country").get(
            pk=sid, school_id=school_id
        )
    except StudentModel.DoesNotExist:
        return redirect("economat:parent_portal_search")

    enrollment, paid, balance = _get_enrollment_and_balance(sid)

    if request.method == "POST":
        form = OnlinePaymentForm(request.POST, country=student.school.country)
        if form.is_valid() and enrollment is not None:
            from economat.composition import get_initiate_online_payment_use_case
            from economat.application.use_cases.initiate_online_payment import (
                InitiateOnlinePaymentCommand,
            )
            result = get_initiate_online_payment_use_case(
                country=student.school.country
            ).execute(InitiateOnlinePaymentCommand(
                school_id=str(school_id),
                matricule=student.matricule,
                amount_fcfa=form.cleaned_data["amount_fcfa"],
                mobile_operator=form.cleaned_data["mobile_operator"],
                mobile_number=form.cleaned_data["mobile_number"],
            ))
            if result.success:
                request.session["parent_portal_payment_id"] = result.payment_id
                return redirect(
                    "economat:parent_portal_waiting",
                    payment_id=result.payment_id,
                )
            form.add_error(None, result.error_message)
    else:
        form = OnlinePaymentForm(country=student.school.country)

    return render(request, "economat/parent_portal/pay.html", {
        "form": form, "student": student, "enrollment": enrollment,
        "balance": balance, "student_id": sid,
        "page_title": "Payer les frais de scolarité",
    })


def waiting(request, payment_id: str):
    """Écran d'attente — poll /payer/statut/<id>/ en JS jusqu'à confirmation."""
    from economat.infrastructure.models import PaymentModel
    payment = PaymentModel.objects.filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return redirect("economat:parent_portal_search")
    if payment.state == "VALID":
        return redirect("economat:parent_portal_receipt", payment_id=payment_id)
    return render(request, "economat/parent_portal/waiting.html", {
        "payment": payment, "page_title": "Confirmation du paiement",
    })


@require_GET
def status(request, payment_id: str):
    """
    Endpoint pollé en JS toutes les 3s par l'écran d'attente.
    Interroge la passerelle en direct pour les paiements PENDING et applique
    la transition idempotente si la passerelle confirme ou refuse.
    """
    from economat.infrastructure.models import PaymentModel, StudentModel
    payment = PaymentModel.objects.filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return JsonResponse({"state": "UNKNOWN"}, status=404)

    if payment.state != "PENDING":
        return JsonResponse({"state": payment.state})

    country = None
    try:
        student = StudentModel.objects.select_related("school").get(pk=payment.student_id)
        country = student.school.country
    except StudentModel.DoesNotExist:
        pass

    from economat.composition import get_poll_online_payment_use_case
    result = get_poll_online_payment_use_case(country=country).execute(str(payment_id))
    state = result.new_state if result.success else payment.state
    return JsonResponse({"state": state})


def receipt(request, payment_id: str):
    """Reçu — uniquement si le paiement est confirmé (VALID)."""
    from economat.infrastructure.models import PaymentModel
    payment = PaymentModel.objects.select_related(
        "student", "enrollment__klass", "enrollment__klass__level", "enrollment__school_year",
    ).filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return redirect("economat:parent_portal_search")
    if payment.state != "VALID":
        return redirect("economat:parent_portal_waiting", payment_id=payment_id)

    return render(request, "economat/parent_portal/receipt.html", {
        "payment": payment, "school": payment.enrollment.school_year.school,
        "klass": payment.enrollment.klass, "level": payment.enrollment.klass.level,
        "school_year": payment.enrollment.school_year,
        "page_title": f"Reçu {payment.receipt_number}",
    })


def portal_history(request, student_id: str):
    """
    Historique complet : récapitulatif solde/progression + tableau
    de tous les paiements avec liens reçu PDF (VALID/PORTAIL_PARENT).
    Accessible uniquement si student_id est en session.
    """
    if request.session.get("parent_portal_student_id") != str(student_id):
        return redirect("economat:parent_portal_search")

    from economat.infrastructure.models import PaymentModel, StudentModel
    student = get_object_or_404(
        StudentModel.objects.select_related("school"),
        pk=student_id,
    )
    enrollment, paid, balance = _get_enrollment_and_balance(student_id)
    annual_fee = enrollment.level.annual_fee if enrollment else 0
    pct_paid = int(paid / annual_fee * 100) if annual_fee else 0

    payments = (
        PaymentModel.objects
        .filter(student_id=student_id)
        .select_related("enrollment__school_year")
        .order_by("-payment_date", "-created_at")
    )

    return render(request, "economat/parent_portal/student_history.html", {
        "student": student, "enrollment": enrollment,
        "annual_fee": annual_fee, "paid": paid,
        "balance": balance, "pct_paid": pct_paid,
        "payments": payments,
        "page_title": f"Historique — {student.first_name} {student.last_name.upper()}",
    })


def history(request):
    """Redirige vers la recherche (l'historique est dans l'espace parent)."""
    return redirect("economat:parent_portal_search")
