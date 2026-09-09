"""
management/commands/seed_demo.py
==================================
Commande Django : python manage.py seed_demo

Crée des données de démo réalistes pour le Collège NDA :
  - Niveaux CP à 3ème (10 niveaux)
  - 2 classes par niveau (A et B)
  - ~20 élèves par classe avec noms africains
  - Tarifs distincts primaire / collège
  - Paiements variés (soldés, en retard, en cours)
"""
import datetime
import random
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from economat.infrastructure.models import (
    ClassModel, EnrollmentModel, LevelModel,
    PaymentModel, SchoolModel, SchoolYearModel, StudentModel,
)


# ─ Données de référence ───────────────────────────────────────────────────────────

PRENOMS = [
    "Aminata", "Fatou", "Mariama", "Aissatou", "Kadiatou",
    "Fatoumata", "Hawa", "Oumou", "Binta", "Rokhaya",
    "Moussa", "Ibrahima", "Mamadou", "Alpha", "Oumar",
    "Seydou", "Abdoulaye", "Cheikh", "Lamine", "Boubacar",
    "Adama", "Samba", "Modibo", "Aliou", "Thierno",
    "Ndaye", "Coumba", "Bineta", "Yacine", "Astou",
]

NOMS = [
    "Diallo", "Bah", "Barry", "Camara", "Conde",
    "Sylla", "Toure", "Kouyate", "Sow", "Keita",
    "Traore", "Coulibaly", "Diabate", "Konate", "Sangare",
    "Ndiaye", "Diop", "Fall", "Mbaye", "Thiam",
    "Sene", "Sarr", "Faye", "Gueye", "Dione",
]

METHODS = ["ESPECES", "ESPECES", "ESPECES", "MOBILE_MONEY", "MOBILE_MONEY", "VIREMENT"]

# Niveaux : (nom, type, frais_annuels_FCFA, mode)
LEVELS = [
    # PRIMAIRE — mensuel (10 mois), frais plus bas
    ("CP",   "primaire",  45_000, "MENSUEL"),
    ("CE1",  "primaire",  50_000, "MENSUEL"),
    ("CE2",  "primaire",  50_000, "MENSUEL"),
    ("CM1",  "primaire",  55_000, "MENSUEL"),
    ("CM2",  "primaire",  55_000, "MENSUEL"),
    # COLLEGE — tranches (40/30/30), frais plus élevés
    ("6ème", "college", 120_000, "TRANCHES"),
    ("5ème", "college", 125_000, "TRANCHES"),
    ("4ème", "college", 130_000, "TRANCHES"),
    ("3ème", "college", 135_000, "TRANCHES"),
]


class Command(BaseCommand):
    help = "Injecte des données de démo réalistes (niveaux, classes, élèves, paiements)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="Supprime toutes les données economat avant de réinsérer"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write(self.style.WARNING("Reset : suppression des données existantes..."))
            PaymentModel.objects.all().delete()
            EnrollmentModel.objects.all().delete()
            StudentModel.objects.all().delete()
            ClassModel.objects.all().delete()
            LevelModel.objects.all().delete()

        # ─ Récupérer l’école et l’année active ───────────────────────
        school = SchoolModel.objects.first()
        if not school:
            self.stdout.write(self.style.ERROR("Aucune école trouvée. Créez-en une d’abord."))
            return

        year = SchoolYearModel.objects.filter(school=school, status="ACTIVE").first()
        if not year:
            self.stdout.write(self.style.ERROR("Aucune année ACTIVE trouvée."))
            return

        self.stdout.write(f"École    : {school.name}")
        self.stdout.write(f"Année     : {year.label} (début {year.start_date})")
        self.stdout.write("")

        year_start = year.start_date
        random.seed(42)   # reproductible
        receipt_counter = [0]

        total_enrollments = total_payments = 0

        for level_name, level_type, fee, mode in LEVELS:

            # ─ Niveau ──────────────────────────────────────────────────
            level, _ = LevelModel.objects.get_or_create(
                school_year=year, name=level_name,
                defaults={"annual_fee": fee, "payment_mode": mode}
            )
            self.stdout.write(f"  Niveau {level_name:6s} ({mode:8s}) {fee:>9,} FCFA")

            for suffix in ("A", "B"):
                class_name = f"{level_name} {suffix}"
                klass, _ = ClassModel.objects.get_or_create(
                    level=level, name=class_name,
                    defaults={"capacity": 25}
                )

                # ─ 20 élèves par classe ──────────────────────────
                for _ in range(20):
                    prenom = random.choice(PRENOMS)
                    nom    = random.choice(NOMS)

                    # Vérifier qu’une inscription n’existe pas déjà dans cette classe
                    student = StudentModel.objects.create(
                        id=uuid.uuid4(),
                        first_name=prenom, last_name=nom.upper(),
                        school=school,
                        date_of_birth=_random_dob(level_type),
                    )

                    enrollment_date = year_start + datetime.timedelta(days=random.randint(0, 14))
                    enrollment = EnrollmentModel.objects.create(
                        id=uuid.uuid4(),
                        student=student, school_year=year,
                        level=level, klass=klass,
                        enrollment_date=enrollment_date,
                        status="ACTIVE",
                    )
                    total_enrollments += 1

                    # ─ Paiements fake variés ─────────────────────────
                    pays = _generate_payments(
                        enrollment, school, fee, mode,
                        year_start, receipt_counter
                    )
                    total_payments += len(pays)

            self.stdout.write(
                self.style.SUCCESS(f"    → 2 classes × 20 élèves créées")
            )

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"DONE — {total_enrollments} inscriptions, {total_payments} paiements"
        ))


def _random_dob(level_type: str) -> datetime.date:
    """Date de naissance aléatoire cohérente avec le niveau."""
    today = datetime.date.today()
    if level_type == "primaire":
        age = random.randint(6, 13)
    else:
        age = random.randint(11, 17)
    return today.replace(year=today.year - age) - datetime.timedelta(days=random.randint(0, 364))


def _generate_payments(
    enrollment, school, annual_fee, mode,
    year_start, receipt_counter
):
    """Génère des paiements réalistes selon le mode et un profil aléatoire.

    Profils :
      40% : soldé (tout payé)
      30% : en cours (partiellement payé, dans les délais)
      20% : en retard (une ou plusieurs échéances impayées)
      10% : rien payé
    """
    profile = random.choices(
        ["solde", "en_cours", "retard", "rien"],
        weights=[40, 30, 20, 10], k=1
    )[0]

    payments = []
    today = datetime.date.today()

    def make_payment(amount, pay_date):
        receipt_counter[0] += 1
        receipt = f"REC-{school.id.hex[:8].upper()}-{receipt_counter[0]:04d}"
        p = PaymentModel.objects.create(
            id=uuid.uuid4(),
            enrollment=enrollment,
            student=enrollment.student,
            amount=amount,
            payment_date=min(pay_date, today),
            method=random.choice(METHODS),
            receipt_number=receipt,
            recorded_by="econome_demo",
            state="VALID",
        )
        payments.append(p)
        return p

    if mode == "MENSUEL":
        monthly = annual_fee // 10
        rest    = annual_fee - monthly * 10
        # 10 mensualités, la dernière absorbe l’arrondi
        installments = [monthly] * 9 + [monthly + rest]
        due_dates = [
            year_start.replace(day=5) + _add_months(i)
            for i in range(10)
        ]

        if profile == "solde":
            for amt, due in zip(installments, due_dates):
                jitter = random.randint(-2, 5)
                make_payment(amt, due + datetime.timedelta(days=jitter))

        elif profile == "en_cours":
            # Payer jusqu’au mois en cours
            paid_up_to = min(
                sum(1 for d in due_dates if d <= today),
                len(due_dates)
            )
            for amt, due in zip(installments[:paid_up_to], due_dates[:paid_up_to]):
                jitter = random.randint(-1, 7)
                make_payment(amt, due + datetime.timedelta(days=jitter))

        elif profile == "retard":
            # Payer seulement les 2–3 premiers mois, rien après
            n_paid = random.randint(1, 3)
            for amt, due in zip(installments[:n_paid], due_dates[:n_paid]):
                make_payment(amt, due + datetime.timedelta(days=random.randint(0, 3)))

        # rien : aucun paiement

    else:  # TRANCHES
        t1 = round(annual_fee * 0.40)
        t3 = round(annual_fee * 0.30)
        t2 = annual_fee - t1 - t3
        tranches = [t1, t2, t3]
        due_dates = [
            year_start,
            year_start + _add_months(3),
            year_start + _add_months(6),
        ]

        if profile == "solde":
            for amt, due in zip(tranches, due_dates):
                jitter = random.randint(-2, 10)
                make_payment(amt, due + datetime.timedelta(days=jitter))

        elif profile == "en_cours":
            # Tranche 1 payée, tranche 2 en cours ou pas encore due
            make_payment(t1, due_dates[0] + datetime.timedelta(days=random.randint(-2, 5)))
            if due_dates[1] <= today:
                make_payment(t2, due_dates[1] + datetime.timedelta(days=random.randint(0, 10)))

        elif profile == "retard":
            # Tranche 1 payée, tranche 2 en retard (due mais pas payée)
            if random.random() < 0.5:
                # Seulement tranche 1
                make_payment(t1, due_dates[0] + datetime.timedelta(days=random.randint(-2, 5)))
            # sinon rien du tout

        # rien : aucun paiement

    return payments


def _add_months(n: int) -> datetime.timedelta:
    """Approximation : n mois = n * 30 jours (suffisant pour les seeds)."""
    return datetime.timedelta(days=n * 30)
