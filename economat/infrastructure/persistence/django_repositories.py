"""
infrastructure/persistence/django_repositories.py
====================================================
Implémentations Django ORM des ports repositories (NOUVEAU SCHEMA).
"""
from __future__ import annotations
from typing import Dict, List, Optional

from economat.application.ports.repositories import (
    EnrollmentRepository, PaymentRepository, SchoolRepository,
    SchoolYearRepository, StudentRepository,
)
from economat.domain.enrollment.entities import Enrollment
from economat.domain.enrollment.value_objects import EnrollmentId
from economat.domain.payment.entities import Payment
from economat.domain.payment.value_objects import PaymentId
from economat.domain.school.entities import School, SchoolYear
from economat.domain.school.value_objects import ClassId, SchoolId, SchoolYearId
from economat.domain.student.entities import Student
from economat.domain.student.value_objects import StudentId
from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel, PaymentModel,
    SchoolModel, SchoolYearModel, StudentModel,
)
from economat.infrastructure.persistence.mappers import (
    class_to_orm, enrollment_to_domain, enrollment_to_orm,
    level_to_orm, payment_to_domain, payment_to_orm,
    school_to_domain, school_to_orm, school_year_to_domain, school_year_to_orm,
    student_to_domain, student_to_orm,
)


class DjangoSchoolRepository(SchoolRepository):
    def find_by_id(self, school_id: SchoolId) -> Optional[School]:
        try:
            orm = SchoolModel.objects.prefetch_related(
                "school_years__levels__classes"
            ).get(pk=school_id.value)
            return school_to_domain(orm)
        except SchoolModel.DoesNotExist:
            return None

    def save(self, school: School) -> None:
        from economat.infrastructure.models import CountryModel
        # Résoudre la FK pays depuis le code ISO du domaine
        try:
            country_obj = CountryModel.objects.get(code=school.country)
        except CountryModel.DoesNotExist:
            country_obj = CountryModel.objects.filter(is_active=True).first()
        SchoolModel.objects.update_or_create(
            pk=str(school.id.value),
            defaults={"name": school.name, "city": school.city,
                      "country": country_obj,
                      "currency": school.currency.value,
                      "tolerance_days": school.tolerance_days},
        )

    def find_all(self) -> List[School]:
        return [school_to_domain(o)
                for o in SchoolModel.objects.prefetch_related("school_years__levels__classes").all()]


class DjangoSchoolYearRepository(SchoolYearRepository):
    def find_by_id(self, year_id: SchoolYearId) -> Optional[SchoolYear]:
        try:
            orm = SchoolYearModel.objects.prefetch_related("levels__classes").get(pk=year_id.value)
            return school_year_to_domain(orm)
        except SchoolYearModel.DoesNotExist:
            return None

    def find_by_school(self, school_id: SchoolId) -> List[SchoolYear]:
        return [school_year_to_domain(o)
                for o in SchoolYearModel.objects
                .prefetch_related("levels__classes")
                .filter(school_id=school_id.value)
                .order_by("-label")]

    def find_active(self, school_id: SchoolId) -> Optional[SchoolYear]:
        try:
            orm = SchoolYearModel.objects.prefetch_related("levels__classes").get(
                school_id=school_id.value, status="ACTIVE"
            )
            return school_year_to_domain(orm)
        except SchoolYearModel.DoesNotExist:
            return None

    def save(self, year: SchoolYear) -> None:
        orm = school_year_to_orm(year)
        SchoolYearModel.objects.update_or_create(
            pk=orm.id,
            defaults={"school_id": orm.school_id, "label": orm.label,
                      "start_date": orm.start_date, "end_date": orm.end_date,
                      "status": orm.status},
        )
        for level in year.levels:
            l_orm = level_to_orm(level)
            LevelModel.objects.update_or_create(
                pk=l_orm.id,
                defaults={"school_year_id": l_orm.school_year_id, "name": l_orm.name,
                          "annual_fee": l_orm.annual_fee, "payment_mode": l_orm.payment_mode,
                          "nb_months": l_orm.nb_months},
            )
            for klass in level.classes:
                c_orm = class_to_orm(klass)
                ClassModel.objects.update_or_create(
                    pk=c_orm.id,
                    defaults={"level_id": c_orm.level_id, "name": c_orm.name,
                              "capacity": c_orm.capacity},
                )

    def next_id(self) -> SchoolYearId:
        return SchoolYearId.generate()


class DjangoStudentRepository(StudentRepository):
    def find_by_id(self, student_id: StudentId) -> Optional[Student]:
        try:
            return student_to_domain(StudentModel.objects.get(pk=student_id.value))
        except StudentModel.DoesNotExist:
            return None

    def find_by_school(self, school_id: SchoolId) -> List[Student]:
        return [student_to_domain(o)
                for o in StudentModel.objects.filter(school_id=school_id.value)]

    def save(self, student: Student) -> None:
        orm = student_to_orm(student)
        StudentModel.objects.update_or_create(
            pk=orm.id,
            defaults={"first_name": orm.first_name, "last_name": orm.last_name,
                      "school_id": orm.school_id, "date_of_birth": orm.date_of_birth,
                      "notes": orm.notes},
        )

    def next_id(self) -> StudentId: return StudentId.generate()
    def exists(self, sid: StudentId) -> bool:
        return StudentModel.objects.filter(pk=sid.value).exists()


class DjangoEnrollmentRepository(EnrollmentRepository):
    def find_by_id(self, eid: EnrollmentId) -> Optional[Enrollment]:
        try:
            return enrollment_to_domain(
                EnrollmentModel.objects.select_related("school_year").get(pk=eid.value)
            )
        except EnrollmentModel.DoesNotExist:
            return None

    def find_by_student_and_year(self, student_id: StudentId, year_id: SchoolYearId) -> Optional[Enrollment]:
        try:
            return enrollment_to_domain(
                EnrollmentModel.objects.select_related("school_year").get(
                    student_id=student_id.value, school_year_id=year_id.value
                )
            )
        except EnrollmentModel.DoesNotExist:
            return None

    def find_by_year(self, year_id: SchoolYearId) -> List[Enrollment]:
        return [enrollment_to_domain(o)
                for o in EnrollmentModel.objects.select_related("school_year")
                .filter(school_year_id=year_id.value)]

    def find_active_by_year(self, year_id: SchoolYearId) -> List[Enrollment]:
        return [enrollment_to_domain(o)
                for o in EnrollmentModel.objects.select_related("school_year")
                .filter(school_year_id=year_id.value, status="ACTIVE")]

    def find_by_class_and_year(self, class_id: ClassId, year_id: SchoolYearId) -> List[Enrollment]:
        return [enrollment_to_domain(o)
                for o in EnrollmentModel.objects.select_related("school_year")
                .filter(klass_id=class_id.value, school_year_id=year_id.value, status="ACTIVE")]

    def save(self, enrollment: Enrollment) -> None:
        orm = enrollment_to_orm(enrollment)
        EnrollmentModel.objects.update_or_create(
            pk=orm.id,
            defaults={"student_id": orm.student_id, "school_year_id": orm.school_year_id,
                      "level_id": orm.level_id, "klass_id": orm.klass_id,
                      "enrollment_date": orm.enrollment_date,
                      "status": orm.status, "notes": orm.notes},
        )

    def next_id(self) -> EnrollmentId: return EnrollmentId.generate()


class DjangoPaymentRepository(PaymentRepository):
    def find_by_id(self, payment_id: PaymentId) -> Optional[Payment]:
        try:
            return payment_to_domain(PaymentModel.objects.get(pk=payment_id.value))
        except PaymentModel.DoesNotExist:
            return None

    def find_by_fee_item(self, fee_item_id) -> list:
        from economat.domain.fee.value_objects import FeeItemId
        fid = fee_item_id.value if hasattr(fee_item_id, "value") else str(fee_item_id)
        return [payment_to_domain(o)
                for o in PaymentModel.objects.filter(fee_item_id=fid)]



    def find_by_enrollment(self, enrollment_id: EnrollmentId) -> List[Payment]:
        return [payment_to_domain(o)
                for o in PaymentModel.objects.filter(enrollment_id=enrollment_id.value)]

    def find_by_school_and_year(self, school_id: SchoolId, year_id: SchoolYearId) -> Dict[str, List[Payment]]:
        qs = PaymentModel.objects.filter(
            enrollment__school_year_id=year_id.value,
            enrollment__school_year__school_id=school_id.value,
        )
        result: Dict[str, List[Payment]] = {}
        for orm in qs:
            key = str(orm.enrollment_id)
            result.setdefault(key, []).append(payment_to_domain(orm))
        return result

    def save(self, payment: Payment) -> None:
        orm = payment_to_orm(payment)
        PaymentModel.objects.update_or_create(
            pk=orm.id,
            defaults={"enrollment_id": orm.enrollment_id, "student_id": orm.student_id,
                      "amount": orm.amount, "payment_date": orm.payment_date,
                      "method": orm.method, "receipt_number": orm.receipt_number,
                      "recorded_by": orm.recorded_by, "state": orm.state,
                      "notes": orm.notes},
        )

    def next_id(self) -> PaymentId: return PaymentId.generate()

    def last_receipt_number(self, school_id: SchoolId) -> int:
        prefix = f"REC-{school_id.value[:8].upper()}-"
        last = (PaymentModel.objects.filter(receipt_number__startswith=prefix)
                .order_by("-receipt_number").values_list("receipt_number", flat=True).first())
        if last:
            try: return int(last.split("-")[-1])
            except (ValueError, IndexError): return 0
        return 0


class DjangoFeeItemRepository:
    """Implémentation Django ORM du port FeeItemRepository."""

    def find_by_id(self, fee_item_id):
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.infrastructure.persistence.mappers import fee_item_to_domain
        try:
            return fee_item_to_domain(_FIM.objects.get(pk=str(fee_item_id)))
        except _FIM.DoesNotExist:
            return None

    def find_by_year(self, year_id):
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.infrastructure.persistence.mappers import fee_item_to_domain
        return [fee_item_to_domain(o) for o in _FIM.objects.filter(school_year_id=str(year_id))]

    def find_active_by_year(self, year_id):
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.infrastructure.persistence.mappers import fee_item_to_domain
        return [fee_item_to_domain(o)
                for o in _FIM.objects.filter(school_year_id=str(year_id), is_active=True)]

    def find_applicable_to_enrollment(self, year_id, class_id):
        """Retourne les FeeItem actifs qui s'appliquent à une classe donnée.
        - scope_type=ALL → toujours applicable
        - scope_type=CLASSES → applicable si class_id est dans class_ids (JSON)
        Le filtrage CLASSES se fait côté Python car le JSON n'est pas requêtable
        en SQLite avec un filtre standard contains (cf. JSONField limitations).
        """
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.infrastructure.persistence.mappers import fee_item_to_domain
        cid = str(class_id)
        # Charger toutes les lignes actives de l'année (peu nombreuses en pratique)
        qs = _FIM.objects.filter(school_year_id=str(year_id), is_active=True, is_system=False)
        result = []
        for orm in qs:
            if orm.scope_type == "ALL":
                result.append(fee_item_to_domain(orm))
            elif orm.scope_type == "CLASSES" and cid in (orm.class_ids or []):
                result.append(fee_item_to_domain(orm))
        return result

    def find_system_for_level(self, level_id, year_id):
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.infrastructure.persistence.mappers import fee_item_to_domain
        obj = _FIM.objects.filter(
            level_id=str(level_id),
            school_year_id=str(year_id),
            is_system=True, category="SCOLARITE",
        ).first()
        return fee_item_to_domain(obj) if obj else None

    def ensure_system_fee_for_level(self, level_id, level_name, year_id,
                                    annual_fee_fcfa, payment_mode, nb_months, scope):
        import uuid as _uuid
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.infrastructure.persistence.mappers import fee_item_to_domain
        fee_item_orm, _ = _FIM.objects.update_or_create(
            school_year_id=str(year_id),
            level_id=str(level_id),
            is_system=True,
            category="SCOLARITE",
            defaults={
                "name":         f"Scolarité — {level_name}",
                "amount":       annual_fee_fcfa,
                "scope_type":   "ALL",
                "class_ids":    [],
                "payment_mode": payment_mode,
                "nb_months":    nb_months,
                "is_mandatory": True,
                "is_active":    True,
            },
        )
        # S'assurer qu'un id est généré si c'est une création
        if not fee_item_orm.id:
            fee_item_orm.id = _uuid.uuid4()
            fee_item_orm.save(update_fields=["id"])
        return fee_item_to_domain(fee_item_orm)

    def save(self, fee_item):
        from economat.infrastructure.models import FeeItemModel as _FIM
        from economat.domain.fee.value_objects import FeeScopeType
        scope_type = fee_item.scope.scope_type.value
        class_ids  = list(fee_item.scope.class_ids) if scope_type == "CLASSES" else []
        _FIM.objects.update_or_create(
            pk=str(fee_item.id),
            defaults={
                "school_year_id": str(fee_item.school_year_id),
                "name":           fee_item.name,
                "category":       fee_item.category.value,
                "amount":         fee_item.amount.amount,
                "scope_type":     scope_type,
                "class_ids":      class_ids,
                "payment_mode":   fee_item.payment_mode.value,
                "nb_months":      fee_item.nb_months,
                "is_mandatory":   fee_item.is_mandatory,
                "is_active":      fee_item.is_active,
                "is_system":      fee_item.is_system,
            },
        )

    def next_id(self):
        from economat.domain.fee.value_objects import FeeItemId
        return FeeItemId.generate()

