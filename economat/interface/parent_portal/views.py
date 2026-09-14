"""
interface/parent_portal/views.py
===================================
Vues du portail de paiement parent — AUCUNE authentification. La session
Django (sans compte) porte l'identité de l'élève confirmé entre les écrans
(recherche → montant → paiement → reçu).

Confirmation : Samirpay (Sénégal) et CRPay (Guinée Conakry) confirment par
polling. L'endpoint `status` interroge la passerelle à chaque appel JS
depuis l'écran d'attente et applique la transition idempotente si confirmé.
"""
from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

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
        student = StudentModel.objects.select_related("school").get(
            pk=student_id, school_id=school_id
        )
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
