"""
management/commands/activate_school.py
=========================================
Commande Django : python manage.py activate_school

Usages :
  python manage.py activate_school --list
      → Liste tous les dossiers PENDING avec leur UUID.

  python manage.py activate_school <registration_uuid>
      → Active le dossier : crée User + School + Membership + envoie l'email.

  python manage.py activate_school <registration_uuid> --dry-run
      → Simule l'activation (calcule username + mot de passe) sans rien persister
        ni envoyer d'email. Utile pour vérifier avant d'activer pour de vrai.
"""
from django.core.management.base import BaseCommand, CommandError

from economat.application.dto_identity import ActivateSchoolCommand
from economat.composition import get_activate_school_registration_use_case, get_registration_repo


class Command(BaseCommand):
    help = "Active un dossier d'inscription d'école (crée le compte + l'école + envoie l'email)"

    def add_arguments(self, parser):
        parser.add_argument(
            "registration_id", nargs="?", default=None,
            help="UUID du dossier SchoolRegistration à activer",
        )
        parser.add_argument(
            "--list", action="store_true",
            help="Affiche tous les dossiers en attente (PENDING)",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Simule l'activation sans persister ni envoyer l'email",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self._list_pending()
            return

        registration_id = options.get("registration_id")
        if not registration_id:
            raise CommandError(
                "Fournissez un UUID de dossier ou utilisez --list pour voir les dossiers en attente.\n"
                "Usage : python manage.py activate_school <uuid>\n"
                "        python manage.py activate_school --list"
            )

        self._activate(registration_id, dry_run=options["dry_run"])

    # ── Sous-commandes ─────────────────────────────────────────────────────────

    def _list_pending(self):
        pending = get_registration_repo().list_pending()
        if not pending:
            self.stdout.write(self.style.SUCCESS("✅ Aucun dossier en attente."))
            return

        self.stdout.write(self.style.WARNING(f"\n{'─'*72}"))
        self.stdout.write(self.style.WARNING(f"  Dossiers en attente (PENDING) — {len(pending)} dossier(s)"))
        self.stdout.write(self.style.WARNING(f"{'─'*72}"))
        for r in pending:
            date = r["created_at"][:10] if r["created_at"] else "?"
            country = f" [{r['country_code']}]" if r["country_code"] else ""
            self.stdout.write(
                f"  {self.style.HTTP_INFO(r['id'])}"
                f"   {r['school_name']} ({r['city']}{country})"
                f"   {r['manager_email']}"
                f"   — soumis le {date}"
            )
        self.stdout.write(f"{'─'*72}\n")
        self.stdout.write(
            "  Pour activer : "
            + self.style.SQL_KEYWORD("python manage.py activate_school <uuid>")
        )
        self.stdout.write("")

    def _activate(self, registration_id: str, dry_run: bool):
        use_case = get_activate_school_registration_use_case()
        command  = ActivateSchoolCommand(registration_id=registration_id, dry_run=dry_run)
        result   = use_case.execute(command)

        sep = "─" * 60

        if not result.success:
            raise CommandError(f"❌  Échec de l'activation :\n    {result.error_message}")

        if dry_run:
            self.stdout.write(self.style.WARNING(f"\n{sep}"))
            self.stdout.write(self.style.WARNING("  [DRY-RUN] Simulation — rien n'a été persisté"))
            self.stdout.write(self.style.WARNING(f"{sep}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\n{sep}"))
            self.stdout.write(self.style.SUCCESS(f"  ✅  École activée avec succès !"))
            self.stdout.write(self.style.SUCCESS(f"{sep}"))

        self.stdout.write(f"  École     : {result.school_name}")
        self.stdout.write(f"  Email     : {result.manager_email}")
        self.stdout.write(f"  Identif.  : {self.style.SQL_KEYWORD(result.username)}")
        self.stdout.write(
            f"  Mot passe : {self.style.SQL_KEYWORD(result.temp_password)}"
            + ("  ⚠️  À transmettre manuellement si l'email a échoué." if not result.email_sent else "")
        )

        if result.email_sent:
            self.stdout.write(f"  Email     : {self.style.SUCCESS('✅ Envoyé via Resend')}")
        else:
            self.stdout.write(
                f"  Email     : {self.style.ERROR('⚠️  Non envoyé')}"
                + (f" — {result.error_message}" if result.error_message else "")
            )

        self.stdout.write(f"{sep}\n")
