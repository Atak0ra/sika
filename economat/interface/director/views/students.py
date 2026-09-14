"""
interface/director/views/students.py
========================================
Vues de gestion des élèves :
  - students_list   : liste paginée avec filtres
  - register_student: inscription d'un nouvel élève
  - student_detail  : fiche élève + historique paiements (correctif N+1)
  - class_detail    : vue classe avec stats financières
  - promote_class   : réinscription en masse (correctif N+1)

Sécurité (IDOR corrigé) :
  Chaque chargement d'objet enfant (enrollment, klass) inclut un filtre
  parent (school_year_id ou level__school_year_id) pour empêcher l'accès
  cross-school en forgeant un UUID dans l'URL (OWASP A01).

Performance :
  - student_detail : Prefetch + annotate Sum → 2 requêtes au lieu de 1+2N.
  - class_detail   : aggregate SQL au lieu de sum() Python.
  - promote_class  : prefetch_related groupé au lieu d'une boucle N+1.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import (
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.shortcuts import redirect, render

from economat.application.dto import (
    CancelPaymentCommand,
    PromoteClassCommand,
    RecordPaymentCommand,
    RegisterStudentCommand,
)
from economat.composition import (
    get_cancel_payment_use_case,
    get_promote_class_use_case,
    get_record_payment_use_case,
    get_register_student_use_case,
)
from economat.domain.identity.value_objects import Role
from economat.domain.payment.value_objects import (
    PaymentStatus,
    mobile_operator_style,
    mobile_operators_for_country,
)
from economat.infrastructure.models import (
    ClassModel,
    EnrollmentModel,
    LevelModel,
    PaymentModel,
    SchoolModel,
    SchoolYearModel,
    StudentModel,
)
from economat.interface.decorators import require_membership, require_role

from ..forms import RegisterStudentForm
from ._shared import base_context

logger = logging.getLogger(__name__)

# ─ Utilitaires de présentation ───────────────────────────────────────────────


def _payment_badge(status_str: str) -> tuple[str, str]:
    """
    Mappe un statut de paiement (string) vers (label, css_class).
    Sépare la logique de présentation de la vue.
    """
    return {
        PaymentStatus.SOLDE.value:    ("Soldé",    "badge-success"),
        PaymentStatus.EN_COURS.value: ("En cours", "badge-info"),
        PaymentStatus.EN_RETARD.value:("En retard","badge-warning"),
        PaymentStatus.NON_PAYE.value: ("Non payé", "badge-danger"),
    }.get(status_str, ("Non payé", "badge-danger"))


# ─ Vues ──────────────────────────────────────────────────────────────────────


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def students_list(request, school_id: str, year_id: str, membership=None):
    """Liste paginée des élèves avec filtres (niveau, classe, statut, recherche)."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    q        = request.GET.get("q", "").strip()
    level_id = request.GET.get("level", "")
    class_id = request.GET.get("class", "")
    status_f = request.GET.get("status", "ACTIVE")

    qs = (
        EnrollmentModel.objects
        .filter(school_year_id=year_id)
        .select_related("student", "level", "klass")
    )
    if status_f != "all":
        qs = qs.filter(status=status_f)
    if level_id:
        qs = qs.filter(level_id=level_id)
    if class_id:
        qs = qs.filter(klass_id=class_id)
    if q:
        qs = qs.filter(
            Q(student__last_name__icontains=q) | Q(student__first_name__icontains=q)
        )

    # Annotation paiement : Subquery → 0 requête supplémentaire par élève
    paid_subq = (
        PaymentModel.objects
        .filter(enrollment=OuterRef("pk"), state="VALID")
        .values("enrollment")
        .annotate(s=Sum("amount"))
        .values("s")
    )
    qs = qs.annotate(
        paid_total=Coalesce(
            Subquery(paid_subq, output_field=IntegerField()),
            Value(0, output_field=IntegerField()),
        )
    ).order_by("student__last_name", "student__first_name")

    paginator = Paginator(qs, 30)
    page_obj  = paginator.get_page(request.GET.get("page", 1))

    levels  = LevelModel.objects.filter(school_year_id=year_id).order_by("name")
    classes = (
        ClassModel.objects
        .filter(level__school_year_id=year_id)
        .select_related("level")
        .order_by("level__name", "name")
    )
    if level_id:
        classes = classes.filter(level_id=level_id)

    total_all    = EnrollmentModel.objects.filter(school_year_id=year_id).count()
    total_active = EnrollmentModel.objects.filter(school_year_id=year_id, status="ACTIVE").count()

    ctx = base_context(
        request, school, year, "eleves", membership=membership,
        page_obj=page_obj, paginator=paginator,
        q=q, level_id=level_id, class_id_f=class_id, status_f=status_f,
        levels=levels, classes=classes,
        total_all=total_all, total_active=total_active,
        total_inactive=total_all - total_active,
        page_title=f"Élèves — {year.label}",
    )
    return render(request, "economat/director/students_list.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def register_student(request, school_id: str, year_id: str, membership=None):
    """Inscription d'un nouvel élève."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    form = RegisterStudentForm(
        request.POST or None,
        initial={
            "school_id": school_id, "year_id": year_id,
            "level_id":  request.GET.get("level_id", ""),
            "class_id":  request.GET.get("class_id", ""),
        },
        year_orm=year,
    )
    if request.method == "POST" and form.is_valid():
        result = get_register_student_use_case().execute(RegisterStudentCommand(
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            school_id=school_id, year_id=year_id,
            level_id=form.cleaned_data["level_id"],
            class_id=form.cleaned_data["class_id"],
            date_of_birth=form.cleaned_data.get("date_of_birth"),
            enrollment_date=form.cleaned_data.get("enrollment_date"),
            notes=form.cleaned_data.get("notes", ""),
            parent_name=form.cleaned_data.get("parent_name", ""),
            parent_phone=form.cleaned_data.get("parent_phone", ""),
            parent_relation=form.cleaned_data.get("parent_relation", ""),
        ))
        if result.success:
            messages.success(
                request,
                f"{result.student_name} inscrit(e) en {result.class_name}.",
            )
            return redirect("economat:students_list", school_id=school_id, year_id=year_id)
        messages.error(request, result.error_message)

    ctx = base_context(
        request, school, year, "eleves", membership=membership,
        form=form, page_title=f"Nouvel élève — {year.label}",
    )
    return render(request, "economat/director/register_student.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def student_detail(request, school_id: str, year_id: str, enrollment_id: str, membership=None):
    """
    Fiche complète d'un élève : infos + historique de paiement multi-années.

    Sécurité IDOR (OWASP A01) : enrollment filtré par school_year_id.
    Performance N+1 corrigée : Prefetch + Sum → 2 requêtes au lieu de 1+2N.
    """
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
        # ✅ Sécurité IDOR : filtre enrollment par school_year_id
        enrollment = EnrollmentModel.objects.select_related(
            "student", "level", "klass", "school_year"
        ).get(pk=enrollment_id, school_year_id=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist, EnrollmentModel.DoesNotExist):
        messages.error(request, "Élève ou inscription introuvable.")
        return redirect("economat:students_list", school_id=school_id, year_id=year_id)

    student = enrollment.student

    # ── Annulation d'un paiement (POST action=cancel_payment, DIRECTOR only) ─
    if request.method == "POST" and request.POST.get("_action") == "cancel_payment":
        try:
            membership.guard_cancel_payment()
        except Exception as e:
            messages.error(request, str(e))
            return redirect(
                "economat:student_detail",
                school_id=school_id, year_id=year_id, enrollment_id=enrollment_id,
            )
        payment_id = request.POST.get("payment_id", "").strip()
        reason     = request.POST.get("reason", "").strip()
        if not payment_id:
            messages.error(request, "Identifiant du paiement manquant.")
            return redirect(
                "economat:student_detail",
                school_id=school_id, year_id=year_id, enrollment_id=enrollment_id,
            )
        result = get_cancel_payment_use_case().execute(CancelPaymentCommand(
            payment_id=payment_id,
            school_id=school_id,
            director_user_id=str(request.user.pk),
            reason=reason,
        ))
        if result.success:
            messages.success(
                request,
                f"Paiement {result.receipt_number} annulé avec succès.",
            )
        else:
            messages.error(request, result.error_message)
        return redirect(
            "economat:student_detail",
            school_id=school_id, year_id=year_id, enrollment_id=enrollment_id,
        )

    # ── Encaissement depuis la fiche élève (POST action=record_payment) ──────
    if request.method == "POST" and request.POST.get("_action") == "record_payment":
        try:
            membership.guard_record_payment()
        except Exception as e:
            messages.error(request, str(e))
            return redirect(
                "economat:student_detail",
                school_id=school_id, year_id=year_id, enrollment_id=enrollment_id,
            )

        import datetime as _dt

        method = request.POST.get("method", "ESPECES").strip()
        try:
            amount_fcfa = int(request.POST.get("amount_fcfa", "0"))
        except ValueError:
            amount_fcfa = 0

        result = get_record_payment_use_case().execute(RecordPaymentCommand(
            student_id=str(student.id),
            year_id=year_id,
            amount_fcfa=amount_fcfa,
            payment_date=_dt.date.today(),
            method=method,
            recorded_by=request.user.username,
            notes=request.POST.get("notes", "").strip(),
            paid_by=request.POST.get("paid_by", "").strip(),
            mobile_operator=request.POST.get("mobile_operator", "").strip(),
            mobile_number=request.POST.get("mobile_number", "").strip(),
        ))
        if result.success:
            messages.success(
                request,
                f"Reçu {result.receipt_number} · {result.amount_paid:,} FCFA enregistré.".replace(",", " "),
            )
        else:
            messages.error(request, result.error_message)
        return redirect(
            "economat:student_detail",
            school_id=school_id, year_id=year_id, enrollment_id=enrollment_id,
        )

    # ── Modification des infos élève (POST action=edit_student) ──────────────
    if request.method == "POST" and request.POST.get("_action") == "edit_student":
        first_name      = request.POST.get("first_name", "").strip()
        last_name       = request.POST.get("last_name", "").strip()
        parent_name     = request.POST.get("parent_name", "").strip()
        parent_phone    = request.POST.get("parent_phone", "").strip()
        parent_relation = request.POST.get("parent_relation", "").strip()

        if not first_name or not last_name:
            messages.error(request, "Le prénom et le nom sont obligatoires.")
        else:
            StudentModel.objects.filter(pk=student.pk).update(
                first_name=first_name, last_name=last_name,
                parent_name=parent_name, parent_phone=parent_phone,
                parent_relation=parent_relation,
            )
            messages.success(request, "Informations mises à jour.")
        return redirect(
            "economat:student_detail",
            school_id=school_id, year_id=year_id, enrollment_id=enrollment_id,
        )

    # Recharger après un éventuel POST
    student = StudentModel.objects.get(pk=student.pk)

    # ── Paiements de l'année en cours ─────────────────────────────────────────
    payments_year = (
        PaymentModel.objects
        .filter(enrollment=enrollment, state="VALID")
        .order_by("-payment_date")
    )
    paid_year = payments_year.aggregate(t=Sum("amount"))["t"] or 0
    total_due = enrollment.level.annual_fee
    balance   = max(total_due - paid_year, 0)

    if balance == 0:
        pay_status, pay_badge = "Soldé",    "badge-success"
    elif paid_year > 0:
        pay_status, pay_badge = "En cours", "badge-info"
    else:
        pay_status, pay_badge = "Non payé", "badge-danger"

    # ── Historique toutes années — ⚡ Prefetch → 2 requêtes au lieu de 1+2N ──
    # On charge TOUS les paiements (VALID + CANCELLED) pour la traçabilité.
    # Les totaux/balances sont calculés uniquement sur les VALID.
    all_pays_qs = PaymentModel.objects.order_by("payment_date")
    all_enrollments = (
        EnrollmentModel.objects
        .filter(student=student)
        .select_related("school_year", "level", "klass")
        .prefetch_related(
            Prefetch("payments", queryset=all_pays_qs, to_attr="all_pays")
        )
        .order_by("-school_year__label")
    )
    history = []
    for enr in all_enrollments:
        pays = enr.all_pays
        total_paid_e = sum(p.amount for p in pays if p.state == "VALID")
        history.append({
            "enrollment": enr, "payments": pays,
            "total_paid": total_paid_e, "total_due": enr.level.annual_fee,
            "balance":    max(enr.level.annual_fee - total_paid_e, 0),
            "is_current": enr.id == enrollment.id,
        })

    operators = mobile_operators_for_country(school.country)
    mobile_operator_options = [
        {"value": op, "style": mobile_operator_style(op)} for op in operators
    ]

    ctx = base_context(
        request, school, year, "eleves", membership=membership,
        enrollment=enrollment, student=student,
        payments_year=payments_year, paid_year=paid_year,
        total_due=total_due, balance=balance,
        pay_status=pay_status, pay_badge=pay_badge,
        history=history,
        active_class_id=str(enrollment.klass_id),
        mobile_operator_options=mobile_operator_options,
        page_title=f"{student.first_name} {student.last_name.upper()}",
    )
    return render(request, "economat/director/student_detail.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def class_detail(request, school_id: str, year_id: str, class_id: str, membership=None):
    """
    Vue dédiée à une classe : liste des élèves + stats financières.

    Sécurité IDOR : klass filtré par level__school_year_id.
    Performance : aggregate SQL au lieu de sum() Python.
    """
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
        # ✅ Sécurité IDOR : filtre class par school_year via level
        klass  = ClassModel.objects.select_related("level").get(
            pk=class_id, level__school_year_id=year_id
        )
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist, ClassModel.DoesNotExist):
        return redirect("economat:director_dashboard")

    paid_subq = (
        PaymentModel.objects
        .filter(enrollment=OuterRef("pk"), state="VALID")
        .values("enrollment")
        .annotate(s=Sum("amount"))
        .values("s")
    )
    enrollments = (
        EnrollmentModel.objects
        .filter(school_year_id=year_id, klass_id=class_id)
        .select_related("student", "level", "klass")
        .annotate(
            paid_total=Coalesce(
                Subquery(paid_subq, output_field=IntegerField()),
                Value(0, output_field=IntegerField()),
            )
        )
        .order_by("student__last_name", "student__first_name")
    )

    total_students  = enrollments.count()
    total_expected  = klass.level.annual_fee * total_students
    # ⚡ aggregate SQL — évite la matérialisation complète du queryset
    total_collected = enrollments.aggregate(t=Sum("paid_total"))["t"] or 0
    total_balance   = total_expected - total_collected
    rate            = round(total_collected / total_expected * 100) if total_expected else 0

    ctx = base_context(
        request, school, year, "eleves", membership=membership,
        klass=klass, level=klass.level, enrollments=enrollments,
        total_students=total_students, total_expected=total_expected,
        total_collected=total_collected, total_balance=total_balance, rate=rate,
        active_class_id=str(class_id),
        page_title=f"{klass.name} — {year.label}",
    )
    return render(request, "economat/director/class_detail.html", ctx)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def promote_class(request, school_id: str, year_id: str, membership=None):
    """
    Réinscription en masse des élèves d'une classe vers l'année suivante.

    ⚡ N+1 corrigé : enrollments actifs chargés en 1 requête avec select_related,
    regroupés en Python par classe (sans boucle de requêtes).
    """
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "Année introuvable.")
        return redirect("economat:director_dashboard")

    target_years = (
        SchoolYearModel.objects
        .filter(school_id=school_id)
        .exclude(status="CLOSED")
        .exclude(id=year_id)
        .order_by("-label")
    )

    if request.method == "POST":
        from_class_id = request.POST.get("from_class_id", "")
        to_year_id    = request.POST.get("to_year_id", "")
        to_class_id   = request.POST.get("to_class_id", "")
        excluded      = request.POST.getlist("exclude_students")
        result = get_promote_class_use_case().execute(PromoteClassCommand(
            director_user_id=str(request.user.pk),
            from_year_id=year_id, to_year_id=to_year_id,
            from_class_id=from_class_id, to_class_id=to_class_id,
            excluded_student_ids=excluded,
        ))
        if result.success:
            messages.success(
                request,
                f"{result.promoted_count} élève(s) réinscrit(s). "
                f"{result.skipped_count} ignoré(s).",
            )
            return redirect(
                "economat:students_list",
                school_id=school_id, year_id=to_year_id or year_id,
            )
        messages.error(request, f"{result.error_message}")

    # ⚡ 1 requête groupée au lieu d'une boucle N+1
    active_enrs = (
        EnrollmentModel.objects
        .filter(school_year_id=year_id, status="ACTIVE")
        .select_related("student", "klass", "klass__level")
        .order_by("klass__level__name", "klass__name", "student__last_name")
    )
    klass_map: dict = {}
    classes_with_enrollments: list = []
    for enr in active_enrs:
        key = str(enr.klass_id)
        if key not in klass_map:
            klass_map[key] = {
                "klass":       enr.klass,
                "level":       enr.klass.level,
                "enrollments": [],
            }
            classes_with_enrollments.append(klass_map[key])
        klass_map[key]["enrollments"].append(enr)

    ctx = base_context(
        request, school, year, "eleves", membership=membership,
        target_years=target_years,
        classes_with_enrollments=classes_with_enrollments,
        page_title=f"Promotion — {year.label}",
    )
    return render(request, "economat/director/promote_class.html", ctx)
