"""
economat/admin.py — Administration Django (NOUVEAU SCHEMA avec SchoolYear).
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html

from economat.infrastructure.models import (
    ClassModel, CountryModel, EnrollmentModel, LevelModel, MembershipModel,
    PaymentModel, SchoolModel, SchoolYearModel, StudentModel,
)


def _badge(role):
    colors = {"DIRECTOR":"background:#e0e7ff;color:#3730a3",
              "SECRETARY":"background:#d1fae5;color:#065f46",
              "ECONOME":"background:#fef3c7;color:#92400e"}
    labels = {"DIRECTOR":"Directeur","SECRETARY":"Secrétaire","ECONOME":"Économe"}
    return format_html(
        '<span style="{}; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600">{}</span>',
        colors.get(role,"background:#f3f4f6;color:#374151"), labels.get(role,role)
    )


# ─ Inlines ──────────────────────────────────────────────────────────────

class SchoolYearInline(admin.TabularInline):
    model = SchoolYearModel; extra = 0
    fields = ("label", "start_date", "end_date", "status")
    show_change_link = True

class MembershipInline(admin.TabularInline):
    model = MembershipModel; extra = 1; fk_name = "school"
    fields = ("user", "role", "display_name", "login", "is_active")
    autocomplete_fields = ("user",)

class SchoolMembershipInline(admin.TabularInline):
    model = MembershipModel; extra = 1; fk_name = "user"
    fields = ("school", "role", "is_active")
    verbose_name = "Accès école"; verbose_name_plural = "Accès aux écoles"
    autocomplete_fields = ("school",)

class LevelInline(admin.TabularInline):
    model = LevelModel; extra = 1
    fields = ("name", "annual_fee", "payment_mode")
    show_change_link = True

class ClassInline(admin.TabularInline):
    model = ClassModel; extra = 1; fields = ("name", "capacity")

class EnrollmentInline(admin.TabularInline):
    model = EnrollmentModel; extra = 0
    fields = ("school_year", "level", "klass", "status", "enrollment_date")
    readonly_fields = ("enrollment_date",)
    show_change_link = True


# ─ User Admin ──────────────────────────────────────────────────────────────

class EconomatUserAdmin(BaseUserAdmin):
    inlines = [SchoolMembershipInline]
    list_display  = ("username","first_name","last_name","ecoles_roles","is_active","is_staff")
    list_filter   = ("is_active","is_staff","school_memberships__role")
    search_fields = ("username","first_name","last_name","email")
    fieldsets = (
        (None, {"fields": ("username","password")}),
        ("Infos", {"fields": ("first_name","last_name","email")}),
        ("Permissions", {
            "fields": ("is_active","is_staff","is_superuser"),
            "description": "⚠️ Directeurs : is_staff=NON, is_superuser=NON.",
        }),
        ("Dates", {"fields": ("last_login","date_joined"), "classes": ("collapse",)}),
    )

    @admin.display(description="Écoles / Rôles")
    def ecoles_roles(self, obj):
        ms = obj.school_memberships.select_related("school").filter(is_active=True)
        if not ms: return format_html('<span style="color:#9ca3af">—</span>')
        return ", ".join(f"{m.school.name} → {m.role}" for m in ms) or "—"

admin.site.unregister(User)
admin.site.register(User, EconomatUserAdmin)


# ─ Country Admin ─────────────────────────────────────────────────────────────

@admin.register(CountryModel)
class CountryAdmin(admin.ModelAdmin):
    list_display  = ("code", "name", "currency", "payment_provider", "operators_preview", "is_active")
    list_filter   = ("payment_provider", "currency", "is_active")
    search_fields = ("code", "name")
    list_editable = ("is_active",)
    ordering      = ("name",)

    @admin.display(description="Opérateurs Mobile Money")
    def operators_preview(self, obj):
        ops = obj.mobile_operators or []
        return ", ".join(ops[:3]) + ("…" if len(ops) > 3 else "")


# ─ School Admin ──────────────────────────────────────────────────────────────

@admin.register(SchoolModel)
class SchoolAdmin(admin.ModelAdmin):
    list_display  = ("name", "city", "country", "currency", "tolerance_days", "nb_years")
    search_fields = ("name", "city")
    list_filter   = ("country", "currency")
    inlines       = [SchoolYearInline, MembershipInline]

    @admin.display(description="Années")
    def nb_years(self, obj): return obj.school_years.count()


@admin.register(SchoolYearModel)
class SchoolYearAdmin(admin.ModelAdmin):
    list_display  = ("label","school","status","start_date","end_date","nb_levels","nb_enrollments")
    list_filter   = ("status","school")
    search_fields = ("label","school__name")
    inlines       = [LevelInline]

    @admin.display(description="Niveaux")
    def nb_levels(self, obj): return obj.levels.count()

    @admin.display(description="Inscriptions")
    def nb_enrollments(self, obj): return obj.enrollments.count()


@admin.register(LevelModel)
class LevelAdmin(admin.ModelAdmin):
    list_display  = ("name","school_year","annual_fee_fcfa","payment_mode")
    list_filter   = ("payment_mode","school_year__school")
    search_fields = ("name","school_year__label")
    inlines       = [ClassInline]

    @admin.display(description="Frais annuels", ordering="annual_fee")
    def annual_fee_fcfa(self, obj):
        return format_html('<strong>{}</strong> FCFA', f"{obj.annual_fee:,}".replace(",","\u202f"))


@admin.register(MembershipModel)
class MembershipAdmin(admin.ModelAdmin):
    list_display  = ("user_display","role_badge","school","is_active","joined_at")
    list_filter   = ("role","is_active","school")
    search_fields = ("user__username","school__name")
    autocomplete_fields = ("user","school")
    readonly_fields = ("joined_at","created_at")

    @admin.display(description="Utilisateur", ordering="user__username")
    def user_display(self, obj):
        return format_html('<strong>{}</strong> <span style="color:#9ca3af">@{}</span>',
                           obj.display_name or obj.user.get_full_name() or obj.user.username,
                           obj.user.username)

    @admin.display(description="Rôle")
    def role_badge(self, obj): return _badge(obj.role)


@admin.register(StudentModel)
class StudentAdmin(admin.ModelAdmin):
    list_display  = ("full_name","school","nb_enrollments")
    list_filter   = ("school",)
    search_fields = ("first_name","last_name")
    readonly_fields = ("created_at","updated_at")
    inlines = [EnrollmentInline]

    @admin.display(description="Élève", ordering="last_name")
    def full_name(self, obj): return f"{obj.first_name} {obj.last_name.upper()}"

    @admin.display(description="Inscriptions")
    def nb_enrollments(self, obj): return obj.enrollments.count()


@admin.register(EnrollmentModel)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display  = ("student","school_year","klass","level","status","enrollment_date")
    list_filter   = ("status","school_year","level")
    search_fields = ("student__first_name","student__last_name")
    readonly_fields = ("created_at",)


@admin.register(PaymentModel)
class PaymentAdmin(admin.ModelAdmin):
    list_display   = ("receipt_number","student_name","montant","payment_date","method","state")
    list_filter    = ("state","method")
    search_fields  = ("receipt_number","student__first_name","student__last_name")
    readonly_fields = ("created_at",)
    date_hierarchy  = "payment_date"

    @admin.display(description="Élève", ordering="student__last_name")
    def student_name(self, obj): return f"{obj.student.first_name} {obj.student.last_name.upper()}"

    @admin.display(description="Montant", ordering="amount")
    def montant(self, obj):
        return format_html('<strong>{}</strong> FCFA', f"{obj.amount:,}".replace(",","\u202f"))


admin.site.site_header = "🏫 Sukulu — Administration"
admin.site.site_title  = "Sukulu Admin"
admin.site.index_title = "Panneau de gestion"
