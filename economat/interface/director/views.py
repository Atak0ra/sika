"""
interface/director/views.py — REFONTE (SchoolYear comme racine temporelle).
"""
from __future__ import annotations
import csv, datetime, json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from economat.application.dto import (
    ActivateSchoolYearCommand, AddClassCommand, AddLevelCommand,
    AskDirectorChatCommand, CloseSchoolYearCommand,
    ConfigureSchoolPricingCommand, CreateSchoolYearCommand,
    RegisterStudentCommand,
)
from economat.composition import (
    get_activate_school_year_use_case, get_add_class_use_case, get_add_level_use_case,
    get_ask_director_chat_query, get_close_school_year_use_case,
    get_configure_pricing_use_case, get_create_school_year_use_case,
    get_financial_dashboard_query, get_list_memberships_query,
    get_promote_class_use_case, get_register_student_use_case,
)
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, PaymentModel,
    SchoolModel, SchoolYearModel, StudentModel,
)
from economat.interface.decorators import require_membership, require_role
from economat.domain.identity.value_objects import Role
from .forms import (
    AddClassForm, AddLevelForm, CloseYearForm, ConfigurePricingForm, CreateSchoolYearForm,
    DirectorChatForm, RegisterStudentForm, SchoolSettingsForm,
)


def _director_schools(user):
    result = get_list_memberships_query().execute(user_id=str(user.pk))
    ids = [m["school_id"] for m in result.memberships if m["role"] in ("DIRECTOR", "SECRETARY")]
    return SchoolModel.objects.filter(id__in=ids).order_by("name")


def _active_year(school_id: str):
    """Retourne l'année active ou None."""
    return SchoolYearModel.objects.filter(school_id=school_id, status="ACTIVE").first()


def _sidebar_ctx(school, year):
    """Contexte commun injecté dans toutes les vues directeur pour alimenter la sidebar.
    Fournit : school, school_year, all_years, schools, sidebar_levels (arborescence Niveaux > Classes).
    """
    if school is None:
        return {"all_years": [], "schools": _director_schools(None), "sidebar_levels": []}
    sidebar_levels = []
    if year:
        levels_qs = (LevelModel.objects
                     .filter(school_year_id=year.id)
                     .prefetch_related("classes")
                     .order_by("name"))
        for lvl in levels_qs:
            sidebar_levels.append({
                "level": lvl,
                "classes": lvl.classes.order_by("name"),
            })
    return {
        "all_years":     SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "schools":       _director_schools(None),
        "sidebar_levels": sidebar_levels,
    }

def _user_role(request) -> str:
    """Retourne le rôle de l'utilisateur connecté ('DIRECTOR', 'SECRETARY', 'ECONOME' ou '')."""
    from economat.infrastructure.models import MembershipModel as _MM
    m = _MM.objects.filter(user=request.user, is_active=True).first()
    return m.role if m else ""


def _sidebar_levels(year):
    """Retourne la liste [{level, classes}] pour l'arborescence de la sidebar."""
    if not year:
        return []
    levels_qs = (LevelModel.objects
                 .filter(school_year_id=year.id)
                 .prefetch_related("classes")
                 .order_by("name"))
    return [{"level": lvl, "classes": lvl.classes.order_by("name")} for lvl in levels_qs]



@login_required
def dashboard(request):
    result  = get_list_memberships_query().execute(user_id=str(request.user.pk))
    my_ids  = [m["school_id"] for m in result.memberships if m["role"] in ("DIRECTOR", "SECRETARY")]
    schools = SchoolModel.objects.prefetch_related("school_years").filter(id__in=my_ids)

    school_id_p = request.GET.get("school")
    active_school = (schools.filter(id=school_id_p).first() if school_id_p else schools.first())

    today = datetime.date.today()
    year_id_p = request.GET.get("year")
    active_year_orm = None
    if active_school:
        if year_id_p:
            active_year_orm = SchoolYearModel.objects.filter(
                id=year_id_p, school_id=active_school.id
            ).first()
        if not active_year_orm:
            active_year_orm = _active_year(str(active_school.id))

    collected_today = 0
    bi_data = None
    period_labels = period_expected = period_real = "[]"
    class_labels = class_objectives = class_collected = class_rates = "[]"

    if active_school and active_year_orm:
        collected_today = (
            PaymentModel.objects
            .filter(state="VALID", payment_date=today,
                    enrollment__school_year_id=active_year_orm.id)
            .aggregate(t=Sum("amount"))["t"] or 0
        )
        bi_data = get_financial_dashboard_query().execute(
            school_id=str(active_school.id),
            year_id=str(active_year_orm.id),
            collected_today=collected_today,
        )
        if bi_data:
            period_labels   = json.dumps(bi_data.period_series.labels)
            period_expected = json.dumps(bi_data.period_series.expected)
            period_real     = json.dumps(bi_data.period_series.collected)
            class_labels     = json.dumps([f"{b.level} \u2013 {b.label}" for b in bi_data.class_bars])
            class_objectives = json.dumps([b.objective for b in bi_data.class_bars])
            class_collected  = json.dumps([b.collected for b in bi_data.class_bars])
            class_rates      = json.dumps([b.rate      for b in bi_data.class_bars])

    all_years_qs = SchoolYearModel.objects.filter(school_id=active_school.id).order_by("-label") if active_school else []

    return render(request, "economat/director/dashboard.html", {
        "schools": schools, "school": active_school,
        "school_year": active_year_orm, "all_years": all_years_qs,
        "active_nav": "dashboard", "bi": bi_data,
        "period_labels": period_labels, "period_expected": period_expected, "period_real": period_real,
        "class_labels": class_labels, "class_objectives": class_objectives,
        "class_collected": class_collected, "class_rates": class_rates,
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(active_year_orm),
        "page_title": "Tableau de bord — Directeur",
    })


# ─ Gestion des années scolaires ─────────────────────────────────────────────────


# ─ Switch année depuis le bandeau ───────────────────────────────────────────

@login_required
@require_membership
def switch_year(request, school_id: str, membership=None):
    """Reçoit year_id + next (URL courante), remplace le year_id dans l'URL et redirige."""
    import re as _re
    year_id  = request.GET.get("year_id", "").strip()
    next_url = request.GET.get("next", "").strip()

    if not year_id:
        return redirect("economat:director_dashboard")

    # Vérifie que l'année appartient bien à cette école
    year = SchoolYearModel.objects.filter(pk=year_id, school_id=school_id).first()
    if not year:
        return redirect("economat:director_dashboard")

    # Tous les year_ids de cette école pour identifier lequel remplacer dans l'URL
    UUID_RE = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    if next_url:
        year_ids = set(str(y) for y in SchoolYearModel.objects
                       .filter(school_id=school_id).values_list("id", flat=True))
        for uid in _re.findall(UUID_RE, next_url):
            if uid in year_ids and uid != year_id:
                return redirect(next_url.replace(uid, year_id, 1))

    # Fallback : liste des élèves de la nouvelle année
    return redirect("economat:students_list", school_id=school_id, year_id=year_id)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def manage_years(request, school_id: str, membership=None):
    """Page de gestion des années scolaires (liste + création + activation)."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
    except SchoolModel.DoesNotExist:
        messages.error(request, "École introuvable.")
        return redirect("economat:director_dashboard")

    all_years = SchoolYearModel.objects.filter(school_id=school_id).order_by("-label")
    form = CreateSchoolYearForm(request.POST or None)

    if request.method == "POST" and "create_year" in request.POST and form.is_valid():
        dup = request.POST.get("duplicate_from", "").strip() or None
        result = get_create_school_year_use_case().execute(CreateSchoolYearCommand(
            school_id=school_id,
            label=form.cleaned_data["label"],
            start_date=form.cleaned_data["start_date"],
            end_date=form.cleaned_data["end_date"],
            duplicate_from_year_id=dup,
        ))
        if result.success:
            # Si c'est la 1ère année (auto-activée), aller directement aux niveaux
            # Sinon, rester sur la page des années (l'utilisateur devra activer manuellement)
            if result.status == "ACTIVE":
                messages.success(request,
                    f"✅ Année '{result.label}' créée et activée. Configurez maintenant vos niveaux.")
                return redirect("economat:add_level", school_id=school_id, year_id=result.year_id)
            else:
                messages.success(request,
                    f"✅ Année '{result.label}' créée. Activez-la quand vous êtes prêt.")
                return redirect("economat:manage_years", school_id=school_id)
        messages.error(request, f"❌ {result.error_message}")

    return render(request, "economat/director/manage_years.html", {
        "school": school, "schools": _director_schools(request.user),
        "all_years": all_years, "form": form,
        "active_nav": "annees",
        "school_year": _active_year(school_id),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(_active_year(school_id)),
        "page_title": f"Années scolaires — {school.name}",
    })


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def activate_year(request, school_id: str, year_id: str, membership=None):
    if request.method != "POST":
        return redirect("economat:manage_years", school_id=school_id)
    result = get_activate_school_year_use_case().execute(
        ActivateSchoolYearCommand(school_id=school_id, year_id=year_id)
    )
    if result.success:
        messages.success(request, f"✅ Année '{result.label}' maintenant ACTIVE.")
    else:
        messages.error(request, f"❌ {result.error_message}")
    return redirect("economat:manage_years", school_id=school_id)


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def close_year(request, school_id: str, year_id: str, membership=None):
    if request.method != "POST":
        return redirect("economat:manage_years", school_id=school_id)
    result = get_close_school_year_use_case().execute(
        CloseSchoolYearCommand(school_id=school_id, year_id=year_id)
    )
    if result.success:
        messages.success(request, f"✅ Année '{result.label}' clôturée.")
    else:
        messages.error(request, f"❌ {result.error_message}")
    return redirect("economat:manage_years", school_id=school_id)


# ─ Niveaux, Classes, Tarifs ─────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def add_level(request, school_id: str, year_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "Année ou école introuvable.")
        return redirect("economat:director_dashboard")
    form = AddLevelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = get_add_level_use_case().execute(AddLevelCommand(
            school_id=school_id, year_id=year_id, user_id=str(request.user.pk),
            level_name=form.cleaned_data["level_name"],
            annual_fee_fcfa=form.cleaned_data["annual_fee_fcfa"],
            payment_mode=form.cleaned_data["payment_mode"],
        ))
        if result.success:
            messages.success(request, f"✅ Niveau '{result.level_name}' créé.")
            return redirect("economat:add_level", school_id=school_id, year_id=year_id)
        messages.error(request, result.error_message)
    levels = LevelModel.objects.filter(school_year_id=year_id).order_by("name")
    return render(request, "economat/director/add_level.html", {
        "school": school, "year": year, "schools": _director_schools(request.user),
        "active_nav": "niveaux", "form": form, "levels": levels,
        "school_year": year, "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Niveaux — {year.label}",
    })


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def add_class(request, school_id: str, year_id: str, level_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
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
            messages.success(request, f"✅ Classe '{result.class_name}' créée dans {result.level_name}.")
            return redirect("economat:add_class", school_id=school_id, year_id=year_id, level_id=level_id)
        messages.error(request, result.error_message)
    classes = ClassModel.objects.filter(level_id=level_id).order_by("name")
    return render(request, "economat/director/add_class.html", {
        "school": school, "year": year, "level": level,
        "schools": _director_schools(request.user),
        "active_nav": "niveaux", "form": form, "classes": classes,
        "school_year": year, "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Classes {level.name} — {year.label}",
    })


@login_required
@require_membership
@require_role(Role.DIRECTOR)
def configure_pricing(request, school_id: str, year_id: str, membership=None):
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
                messages.success(request, f"✅ {result.level_name} : {result.new_fee_fcfa:,} FCFA")
            else:
                messages.error(request, f"❌ {result.error_message}")
        return redirect("economat:configure_pricing", school_id=school_id, year_id=year_id)
    return render(request, "economat/director/configure_pricing.html", {
        "school": school, "year": year, "schools": _director_schools(request.user),
        "active_nav": "tarifs", "school_year": year,
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Tarifs — {year.label}",
    })


# ─ Élèves ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def students_list(request, school_id: str, year_id: str, membership=None):
    from django.core.paginator import Paginator
    from django.db.models import OuterRef, Subquery, Sum as DSum, Value, IntegerField
    from django.db.models.functions import Coalesce
    from django.db import models as dj_models
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

    # Base : enrollments de cette année
    qs = (EnrollmentModel.objects
          .filter(school_year_id=year_id)
          .select_related("student", "level", "klass"))
    if status_f != "all":
        qs = qs.filter(status=status_f)
    if level_id:
        qs = qs.filter(level_id=level_id)
    if class_id:
        qs = qs.filter(klass_id=class_id)
    if q:
        qs = qs.filter(
            dj_models.Q(student__last_name__icontains=q) |
            dj_models.Q(student__first_name__icontains=q)
        )

    # Annotation paiement rapide
    paid_subq = (
        PaymentModel.objects
        .filter(enrollment=OuterRef("pk"), state="VALID")
        .values("enrollment")
        .annotate(s=DSum("amount")).values("s")
    )
    qs = qs.annotate(
        paid_total=Coalesce(
            Subquery(paid_subq, output_field=IntegerField()),
            Value(0, output_field=IntegerField()),
        )
    ).order_by("student__last_name", "student__first_name")

    paginator   = Paginator(qs, 30)
    page_obj    = paginator.get_page(request.GET.get("page", 1))

    levels  = LevelModel.objects.filter(school_year_id=year_id).order_by("name")
    classes = ClassModel.objects.filter(level__school_year_id=year_id).select_related("level").order_by("level__name", "name")
    if level_id:
        classes = classes.filter(level_id=level_id)

    total_all      = EnrollmentModel.objects.filter(school_year_id=year_id).count()
    total_active   = EnrollmentModel.objects.filter(school_year_id=year_id, status="ACTIVE").count()
    total_inactive = total_all - total_active

    return render(request, "economat/director/students_list.html", {
        "school": school, "year": year, "schools": _director_schools(request.user),
        "active_nav": "eleves", "school_year": year,
        "page_obj": page_obj, "paginator": paginator,
        "q": q, "level_id": level_id, "class_id_f": class_id, "status_f": status_f,
        "levels": levels, "classes": classes,
        "total_all": total_all, "total_active": total_active, "total_inactive": total_inactive,
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Élèves — {year.label}",
    })


@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def register_student(request, school_id: str, year_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")
    form = RegisterStudentForm(
        request.POST or None,
        initial={"school_id": school_id, "year_id": year_id},
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
        ))
        if result.success:
            messages.success(request, f"✅ {result.student_name} inscrit(e) en {result.class_name}.")
            return redirect("economat:students_list", school_id=school_id, year_id=year_id)
        messages.error(request, result.error_message)
    return render(request, "economat/director/register_student.html", {
        "form": form, "school": school, "year": year,
        "schools": _director_schools(request.user),
        "active_nav": "eleves", "school_year": year,
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Nouvel élève — {year.label}",
    })


# ─ Fiche élève ──────────────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def student_detail(request, school_id: str, year_id: str, enrollment_id: str, membership=None):
    """Fiche complète d'un élève : infos de l'année en cours + historique de paiement."""
    from django.db.models import Sum as DSum2
    try:
        school     = SchoolModel.objects.get(pk=school_id)
        year       = SchoolYearModel.objects.get(pk=year_id)
        enrollment = EnrollmentModel.objects.select_related(
            "student", "level", "klass", "school_year"
        ).get(pk=enrollment_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist, EnrollmentModel.DoesNotExist):
        messages.error(request, "Élève ou inscription introuvable.")
        return redirect("economat:students_list", school_id=school_id, year_id=year_id)

    student = enrollment.student

    # Paiements de l'année en cours (validés)
    payments_year = (PaymentModel.objects
                     .filter(enrollment=enrollment, state="VALID")
                     .order_by("-payment_date"))
    paid_year  = payments_year.aggregate(t=DSum2("amount"))["t"] or 0
    total_due  = enrollment.level.annual_fee
    balance    = max(total_due - paid_year, 0)

    if balance == 0:
        pay_status, pay_badge = "Soldé", "badge-success"
    elif paid_year > 0:
        pay_status, pay_badge = "En cours", "badge-info"
    else:
        pay_status, pay_badge = "Non payé", "badge-danger"

    # Historique toutes années : tous les enrollments de cet élève
    all_enrollments = (EnrollmentModel.objects
                       .filter(student=student)
                       .select_related("school_year", "level", "klass")
                       .order_by("-school_year__label"))

    history = []
    for enr in all_enrollments:
        pays = (PaymentModel.objects
                .filter(enrollment=enr, state="VALID")
                .order_by("payment_date"))
        total_paid_enr = pays.aggregate(t=DSum2("amount"))["t"] or 0
        history.append({
            "enrollment": enr,
            "payments":   list(pays),
            "total_paid": total_paid_enr,
            "total_due":  enr.level.annual_fee,
            "balance":    max(enr.level.annual_fee - total_paid_enr, 0),
            "is_current": enr.id == enrollment.id,
        })

    return render(request, "economat/director/student_detail.html", {
        "school": school, "year": year,
        "schools": _director_schools(request.user),
        "active_nav": "eleves", "school_year": year,
        "enrollment": enrollment, "student": student,
        "payments_year": payments_year,
        "paid_year": paid_year, "total_due": total_due,
        "balance": balance, "pay_status": pay_status, "pay_badge": pay_badge,
        "history": history,
        "active_class_id": str(enrollment.klass_id),
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"{student.first_name} {student.last_name.upper()}",
    })


# ─ Vue dédiée par classe ──────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR, Role.SECRETARY)
def class_detail(request, school_id: str, year_id: str, class_id: str, membership=None):
    """Vue dédiée à une classe : liste des élèves + stats financières (encaissé vs attendu)."""
    from django.db.models import OuterRef, Subquery, Sum as DSum, Value, IntegerField
    from django.db.models.functions import Coalesce
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
        klass  = ClassModel.objects.select_related("level").get(pk=class_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist, ClassModel.DoesNotExist):
        return redirect("economat:director_dashboard")

    paid_subq = (
        PaymentModel.objects
        .filter(enrollment=OuterRef("pk"), state="VALID")
        .values("enrollment")
        .annotate(s=DSum("amount")).values("s")
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
    total_collected = sum(e.paid_total for e in enrollments)
    total_balance   = total_expected - total_collected
    rate            = round(total_collected / total_expected * 100) if total_expected else 0

    return render(request, "economat/director/class_detail.html", {
        "school": school, "school_year": year,
        "klass": klass, "level": klass.level,
        "enrollments": enrollments,
        "total_students": total_students,
        "total_expected": total_expected,
        "total_collected": total_collected,
        "total_balance": total_balance,
        "rate": rate,
        "active_nav": "eleves",
        "active_class_id": str(class_id),
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"{klass.name} — {year.label}",
    })


# ─ Promotion en masse ───────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR)
def promote_class(request, school_id: str, year_id: str, membership=None):
    """Affiche les classes de l'année active + formulaire de réinscription en masse vers l'année suivante."""
    from economat.application.dto import PromoteClassCommand
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "Année introuvable.")
        return redirect("economat:director_dashboard")

    # Années DRAFT disponibles comme cible
    target_years = SchoolYearModel.objects.filter(school_id=school_id).exclude(
        status="CLOSED"
    ).exclude(id=year_id).order_by("-label")

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
                f"✅ {result.promoted_count} élève(s) réinscrit(s). {result.skipped_count} ignoré(s)."
            )
            return redirect("economat:students_list", school_id=school_id, year_id=to_year_id or year_id)
        messages.error(request, f"❌ {result.error_message}")

    # Classes de l'année source avec leurs élèves
    classes_with_enrollments = []
    for level in year.levels.all() if hasattr(year, 'levels') else LevelModel.objects.filter(school_year_id=year_id):
        for klass in (level.classes.all() if hasattr(level, 'classes') else ClassModel.objects.filter(level=level)):
            enrollments = EnrollmentModel.objects.filter(
                klass=klass, school_year_id=year_id, status="ACTIVE"
            ).select_related("student").order_by("student__last_name")
            if enrollments.exists():
                classes_with_enrollments.append({"klass": klass, "level": level,
                                                  "enrollments": list(enrollments)})

    return render(request, "economat/director/promote_class.html", {
        "school": school, "year": year, "target_years": target_years,
        "classes_with_enrollments": classes_with_enrollments,
        "schools": _director_schools(request.user),
        "active_nav": "eleves", "school_year": year,
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "page_title": f"Promotion — {year.label}",
    })


# ─ Alertes de paiement ──────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR)
def alerts(request, school_id: str, year_id: str, membership=None):
    """Page dédiée aux alertes de paiement."""
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        messages.error(request, "École ou année introuvable.")
        return redirect("economat:director_dashboard")

    bi_data = get_financial_dashboard_query().execute(
        school_id=school_id, year_id=year_id, collected_today=0
    )
    return render(request, "economat/director/alerts.html", {
        "school": school, "year": year,
        "schools": _director_schools(request.user),
        "active_nav": "alertes", "school_year": year, "bi": bi_data,
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Alertes — {year.label}",
    })


# ─ Export CSV alertes prioritaires ─────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR)
def export_renvoyables(request, school_id: str, year_id: str, membership=None):
    bi_data = get_financial_dashboard_query().execute(
        school_id=school_id, year_id=year_id, collected_today=0
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="alertes_prioritaires_{school_id[:8]}_{year_id[:8]}.csv"'
    )
    response.write("\ufeff")
    writer = csv.writer(response, delimiter=";")
    writer.writerow(["Nom","Niveau","Classe","Montant dû (FCFA)","Jours de retard",
                     "1ère échéance impayée","Statut"])
    if bi_data:
        for a in bi_data.alert_students:
            if a.alert_level == "critical":
                writer.writerow([a.full_name, a.level, a.class_name,
                                 a.overdue_amount, a.days_late,
                                 a.oldest_overdue_date or "", "ALERTE PRIORITAIRE"])
    return response


# ─ Paramètres ──────────────────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR)
def school_settings(request, school_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
    except SchoolModel.DoesNotExist:
        return redirect("economat:director_dashboard")
    form = SchoolSettingsForm(request.POST or None, initial={"tolerance_days": school.tolerance_days})
    if request.method == "POST" and form.is_valid():
        school.tolerance_days = form.cleaned_data["tolerance_days"]
        school.save(update_fields=["tolerance_days"])
        messages.success(request, f"✅ Seuil mis à jour : {school.tolerance_days} jours.")
        return redirect("economat:school_settings", school_id=school_id)
    return render(request, "economat/director/school_settings.html", {
        "school": school, "schools": _director_schools(request.user),
        "form": form, "active_nav": "settings",
        "school_year": _active_year(school_id),
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(_active_year(school_id)),
        "page_title": f"Paramètres — {school.name}",
    })


# ─ Chat IA ──────────────────────────────────────────────────────────────────

@login_required
@require_membership
@require_role(Role.DIRECTOR)
def chat(request, school_id: str, year_id: str, membership=None):
    try:
        school = SchoolModel.objects.get(pk=school_id)
        year   = SchoolYearModel.objects.get(pk=year_id)
    except (SchoolModel.DoesNotExist, SchoolYearModel.DoesNotExist):
        return redirect("economat:director_dashboard")
    chat_history = request.session.get(f"chat_{school_id}_{year_id}", [])
    form = DirectorChatForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = get_ask_director_chat_query().execute(AskDirectorChatCommand(
            question=form.cleaned_data["question"],
            school_id=school_id,
            year_id=year_id,
            school_year_label=year.label,
            history=chat_history,
        ))
        chat_history.append({"role":"user","content":form.cleaned_data["question"]})
        chat_history.append({
            "role":"assistant",
            "content": result.chat_reply or ("Voici les données :" if result.success else f"❌ {result.error_message}"),
            "columns": result.columns if result.success else [],
            "rows": [list(r) for r in result.rows] if result.success else [],
            "sql": result.sql if result.success else "",
        })
        request.session[f"chat_{school_id}_{year_id}"] = chat_history[-20:]
        request.session.modified = True
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": result.success, "message": chat_history[-1]})
    return render(request, "economat/director/chat.html", {
        "school": school, "year": year, "schools": _director_schools(request.user),
        "active_nav": "chat", "school_year": year,
        "form": form, "chat_history": chat_history,
        "all_years": SchoolYearModel.objects.filter(school_id=school.id).order_by("-label"),
        "user_role": _user_role(request), "sidebar_levels": _sidebar_levels(year),
        "page_title": f"Chat IA — {year.label}",
    })
