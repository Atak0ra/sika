"""
interface/parent_portal/views.py
===================================
Vues du portail de paiement parent — AUCUNE authentification. La session
Django (sans compte) porte l'identité de l'élève confirmé entre les écrans
(recherche → montant → paiement → reçu).
"""
from __future__ import annotations

import json

from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import OnlinePaymentForm, SchoolMatriculeForm

GENERIC_NOT_FOUND = "École ou matricule introuvable. Vérifiez votre saisie."


def search(request):
    """GET : formulaire vide. POST : recherche exacte, redirige si trouvé."""
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
                return redirect("economat:parent_portal_pay")

            form.add_error(None, GENERIC_NOT_FOUND)
    else:
        form = SchoolMatriculeForm()

    return render(request, "economat/parent_portal/search.html", {
        "form": form, "page_title": "Payer les frais de scolarité",
    })


def pay(request):
    """Écran montant + opérateur — nécessite un élève confirmé en session."""
    student_id = request.session.get("parent_portal_student_id")
    school_id = request.session.get("parent_portal_school_id")
    if not student_id or not school_id:
        return redirect("economat:parent_portal_search")

    from economat.infrastructure.models import EnrollmentModel, StudentModel
    try:
        student = StudentModel.objects.get(pk=student_id, school_id=school_id)
    except StudentModel.DoesNotExist:
        return redirect("economat:parent_portal_search")

    enrollment = (
        EnrollmentModel.objects
        .select_related("level", "klass", "school_year")
        .filter(student_id=student_id, school_year__status="ACTIVE")
        .first()
    )

    balance = None
    if enrollment is not None:
        from django.db.models import Sum
        paid = (
            enrollment.payments.filter(state="VALID").aggregate(total=Sum("amount"))["total"]
            or 0
        )
        balance = max(enrollment.level.annual_fee - paid, 0)

    if request.method == "POST":
        form = OnlinePaymentForm(request.POST, country=student.school.country)
        if form.is_valid() and enrollment is not None:
            from economat.composition import get_initiate_online_payment_use_case
            from economat.application.use_cases.initiate_online_payment import (
                InitiateOnlinePaymentCommand,
            )
            notify_url = request.build_absolute_uri(
                reverse("economat:parent_portal_webhook_cinetpay")
            )
            result = get_initiate_online_payment_use_case().execute(InitiateOnlinePaymentCommand(
                school_id=str(school_id),
                matricule=student.matricule,
                amount_fcfa=form.cleaned_data["amount_fcfa"],
                mobile_operator=form.cleaned_data["mobile_operator"],
                mobile_number=form.cleaned_data["mobile_number"],
                notify_url=notify_url,
            ))
            if result.success:
                request.session["parent_portal_payment_id"] = result.payment_id
                return redirect("economat:parent_portal_waiting", payment_id=result.payment_id)
            form.add_error(None, result.error_message)
    else:
        form = OnlinePaymentForm(country=student.school.country)

    return render(request, "economat/parent_portal/pay.html", {
        "form": form, "student": student, "enrollment": enrollment, "balance": balance,
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
    """Endpoint pollé en JS toutes les 3s par l'écran d'attente."""
    from economat.infrastructure.models import PaymentModel
    payment = PaymentModel.objects.filter(pk=payment_id, channel="PORTAIL_PARENT").first()
    if payment is None:
        return JsonResponse({"state": "UNKNOWN"}, status=404)
    return JsonResponse({"state": payment.state})


@csrf_exempt
@require_POST
def webhook_cinetpay(request):
    """
    Callback serveur-à-serveur de la passerelle de paiement. Aucune session
    ni authentification utilisateur ici — la sécurité tient entièrement à
    la vérification de signature avant tout traitement.
    """
    from economat.composition import get_confirm_online_payment_use_case, get_payment_gateway

    gateway = get_payment_gateway()
    raw_body = request.body

    if not gateway.verify_webhook_signature(raw_body, dict(request.headers)):
        return HttpResponseForbidden("Signature invalide.")

    try:
        event = gateway.parse_webhook_status(raw_body)
    except (json.JSONDecodeError, KeyError, ValueError):
        return JsonResponse({"error": "Corps de requête invalide."}, status=400)

    result = get_confirm_online_payment_use_case().execute(event)
    if not result.success:
        # 200 quand même : évite que le fournisseur ne retente indéfiniment
        # un webhook pour une transaction qu'on ne reconnaît pas (log côté
        # serveur suffisant pour investiguer).
        return JsonResponse({"status": "ignored", "detail": result.error_message})

    return JsonResponse({"status": "ok"})


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


def history(request):
    """Même recherche que l'accueil, liste les paiements VALID de l'élève (tous canaux)."""
    payments = None
    student = None
    if request.method == "POST":
        form = SchoolMatriculeForm(request.POST)
        if form.is_valid():
            school = form.cleaned_data["school"]
            matricule = form.cleaned_data["matricule"]
            from economat.infrastructure.models import PaymentModel, StudentModel
            student = StudentModel.objects.filter(school_id=school.id, matricule=matricule).first()
            if student is not None:
                payments = (
                    PaymentModel.objects
                    .filter(student_id=student.id, state="VALID")
                    .order_by("-payment_date", "-created_at")
                )
            else:
                form.add_error(None, GENERIC_NOT_FOUND)
    else:
        form = SchoolMatriculeForm()

    return render(request, "economat/parent_portal/history.html", {
        "form": form, "student": student, "payments": payments,
        "page_title": "Historique de mes paiements",
    })
