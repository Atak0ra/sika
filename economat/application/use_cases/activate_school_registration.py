"""
application/use_cases/activate_school_registration.py
=======================================================
USE CASE : ActivateSchoolRegistrationUseCase
Acteur   : Opérateur interne (via commande manage.py activate_school)
Action   : Valider un dossier PENDING → crée User + School + Membership
           + envoie email d'identifiants via Resend.

Flux :
  1. Charger et vérifier le dossier (PENDING seulement).
  2. Générer un mot de passe temporaire sécurisé (secrets).
  3. Dériver un username unique (prenom.nom, suffixe si collision).
  4. Créer le compte User (UserRepository).
  5. Créer l'école + Membership DIRECTOR (CreateSchoolUseCase).
  6. Marquer la registration ACTIVATED.
  7. Envoyer l'email d'identifiants via EmailSender.
  8. Retourner ActivateSchoolResult (username + temp_password pour la CLI).

Si dry_run=True : calcule username + temp_password mais ne persiste rien
et n'envoie pas l'email.
"""
from __future__ import annotations
import secrets
import string

from economat.application.dto_identity import (
    ActivateSchoolCommand, ActivateSchoolResult, CreateSchoolCommand,
)
from economat.application.ports.email_sender import EmailSender, EmailSendError
from economat.application.ports.identity_repositories import UserRepository
from economat.application.ports.registration_repository import SchoolRegistrationRepository
from economat.application.use_cases.create_school import CreateSchoolUseCase
from economat.domain.shared.errors import DomainError

_PWD_ALPHABET = string.ascii_letters + string.digits + "!@#$%"
_PWD_LENGTH   = 12


class ActivateSchoolRegistrationUseCase:

    def __init__(self, registration_repo, user_repo, create_school_uc, email_sender):
        self._registrations = registration_repo
        self._users         = user_repo
        self._create_school = create_school_uc
        self._email         = email_sender

    def execute(self, command: ActivateSchoolCommand) -> ActivateSchoolResult:
        try:
            return self._execute(command)
        except DomainError as e:
            return ActivateSchoolResult(success=False, error_message=str(e))
        except Exception as e:  # noqa: BLE001
            return ActivateSchoolResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, command: ActivateSchoolCommand) -> ActivateSchoolResult:
        reg = self._registrations.get(command.registration_id)
        if reg is None:
            raise DomainError(f"Aucun dossier trouvé pour l'ID {command.registration_id!r}.")
        if reg["status"] == "ACTIVATED":
            raise DomainError(
                f"Le dossier {command.registration_id!r} est déjà activé "
                f"(école : {reg['school_name']})."
            )
        if reg["status"] == "REJECTED":
            raise DomainError(
                f"Le dossier {command.registration_id!r} a été rejeté et ne peut pas être activé."
            )

        temp_password = "".join(secrets.choice(_PWD_ALPHABET) for _ in range(_PWD_LENGTH))
        username = self._make_unique_username(reg["manager_first_name"], reg["manager_last_name"])

        if command.dry_run:
            return ActivateSchoolResult(
                success=True, registration_id=command.registration_id,
                school_name=reg["school_name"], username=username,
                temp_password=temp_password, manager_email=reg["manager_email"],
                email_sent=False, dry_run=True,
            )

        user_id = self._users.create_user(
            username=username, password=temp_password,
            first_name=reg["manager_first_name"], last_name=reg["manager_last_name"],
            email=reg["manager_email"],
        )

        display_name = f"{reg['manager_first_name']} {reg['manager_last_name'].upper()}"
        school_result = self._create_school.execute(CreateSchoolCommand(
            director_user_id=user_id,
            school_name=reg["school_name"],
            city=reg["city"],
            country=reg["country_code"] or "SN",
            currency=reg["currency"] or "XOF",
            director_display_name=display_name,
            director_login=username,
        ))
        if not school_result.success:
            raise DomainError(f"Échec création école : {school_result.error_message}")

        self._registrations.mark_activated(
            registration_id=command.registration_id,
            school_id=school_result.school_id,
            user_id=user_id,
        )

        try:
            self._email.send(
                to=reg["manager_email"],
                subject=f"Vos identifiants Sukulu — {reg['school_name']}",
                html=_build_welcome_email(
                    first_name=reg["manager_first_name"], school_name=reg["school_name"],
                    username=username, temp_password=temp_password,
                ),
            )
            email_sent = True
        except EmailSendError as exc:
            return ActivateSchoolResult(
                success=True, registration_id=command.registration_id,
                school_id=school_result.school_id, school_name=reg["school_name"],
                username=username, temp_password=temp_password,
                manager_email=reg["manager_email"], email_sent=False,
                error_message=f"École créée mais email non envoyé : {exc}",
            )

        return ActivateSchoolResult(
            success=True, registration_id=command.registration_id,
            school_id=school_result.school_id, school_name=reg["school_name"],
            username=username, temp_password=temp_password,
            manager_email=reg["manager_email"], email_sent=email_sent,
        )

    def _make_unique_username(self, first_name: str, last_name: str) -> str:
        base = _slugify(f"{first_name}.{last_name}")
        candidate, counter = base, 2
        while self._users.username_exists(candidate):
            candidate = f"{base}{counter}"
            counter += 1
        return candidate




# ── Helpers ────────────────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    allowed = string.ascii_lowercase + string.digits + "."
    return "".join(c for c in ascii_text.lower() if c in allowed) or "user"


def _build_welcome_email(first_name: str, school_name: str, username: str, temp_password: str) -> str:
    from django.conf import settings
    from django.template.loader import render_to_string
    return render_to_string("economat/emails/welcome_school.html", {
        "first_name":    first_name,
        "school_name":   school_name,
        "username":      username,
        "temp_password": temp_password,
        "login_url":     getattr(settings, "PLATFORM_LOGIN_URL", "https://sukulu.app/eco/login/"),
        "year":          __import__("datetime").date.today().year,
    })

