"""
management/commands/backfill_matricule.py
=============================================
Commande Django : python manage.py backfill_matricule

Attribue un matricule (format sécurisé, cf. domain/student/matricule.py)
à tous les élèves qui n'en ont pas encore — élèves créés avant l'ajout du
champ, ou via un chemin qui ne passait pas par register_student.py (ex.
seed_demo.py avant sa mise à jour).

Sans danger à relancer plusieurs fois : ne touche jamais un élève qui a
déjà un matricule.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from economat.domain.student.matricule import generate_matricule
from economat.infrastructure.models import StudentModel


class Command(BaseCommand):
    help = "Attribue un matricule aux élèves qui n'en ont pas."

    @transaction.atomic
    def handle(self, *args, **options):
        students = StudentModel.objects.filter(matricule__isnull=True) | \
            StudentModel.objects.filter(matricule="")
        count = 0
        for student in students.distinct():
            student.matricule = generate_matricule(student.last_name, student.first_name)
            student.save(update_fields=["matricule"])
            count += 1

        self.stdout.write(self.style.SUCCESS(f"{count} élève(s) mis à jour avec un matricule."))
