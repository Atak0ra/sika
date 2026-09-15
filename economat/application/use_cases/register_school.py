"""
application/use_cases/register_school.py
==========================================
USE CASE : RegisterSchoolUseCase
Acteur   : Visiteur public (futur gérant d'école)
Action   : Soumettre une demande d'inscription — statut PENDING.

Règles métier :
  - Tous les champs obligatoires doivent être fournis.
  - Si MOBILE_MONEY figure dans payment_methods, l'opérateur ET le numéro
    sont obligatoires, et l'opérateur doit appartenir aux opérateurs connus
    du pays sélectionné.
  - Un dossier PENDING ne peut pas exister pour le même email gérant.
  - Idempotence : si client_uuid est fourni et qu'un dossier existe déjà
    avec ce même client_uuid, on retourne ce dossier sans en créer un autre
    (protection contre les re-soumissions après coupure réseau).
"""
from __future__ import annotations

from economat.application.dto_identity import RegisterSchoolCommand, RegisterSchoolResult
from economat.application.ports.registration_repository import SchoolRegistrationRepository
from economat.domain.shared.errors import DomainError


class RegisterSchoolUseCase:

    def __init__(self, registration_repo: SchoolRegistrationRepository) -> None:
        self._repo = registration_repo

    def execute(self, command: RegisterSchoolCommand) -> RegisterSchoolResult:
        try:
            return self._execute(command)
        except DomainError as e:
            return RegisterSchoolResult(success=False, error_message=str(e))
        except Exception as e:  # noqa: BLE001
            return RegisterSchoolResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, command: RegisterSchoolCommand) -> RegisterSchoolResult:
        # 1. Idempotence : même client_uuid = même demande
        if command.client_uuid:
            existing = self._repo.find_by_client_uuid(command.client_uuid)
            if existing:
                return RegisterSchoolResult(
                    success=True,
                    registration_id=existing["id"],
                    already_exists=True,
                )

        # 2. Validation des champs obligatoires
        if not command.school_name.strip():
            raise DomainError("Le nom de l'école est obligatoire.")
        if not command.city.strip():
            raise DomainError("La ville est obligatoire.")
        if not command.country_code.strip():
            raise DomainError("Le pays est obligatoire.")
        if not command.manager_first_name.strip() or not command.manager_last_name.strip():
            raise DomainError("Le prénom et le nom du gérant sont obligatoires.")
        if not command.manager_email.strip():
            raise DomainError("L'adresse email du gérant est obligatoire.")
        if "@" not in command.manager_email:
            raise DomainError("L'adresse email du gérant n'est pas valide.")
        if not command.payment_methods:
            raise DomainError("Sélectionnez au moins un moyen d'encaissement.")

        # 3. Validation Mobile Money
        payment_methods = list(command.payment_methods)
        if "MOBILE_MONEY" in payment_methods:
            if not command.mobile_operator.strip():
                raise DomainError(
                    "L'opérateur Mobile Money est obligatoire quand ce moyen est sélectionné."
                )
            if not command.mobile_number.strip():
                raise DomainError(
                    "Le numéro Mobile Money est obligatoire quand ce moyen est sélectionné."
                )
            self._validate_operator(command.country_code, command.mobile_operator)

        # 4. Pas de doublon email PENDING
        if self._repo.email_has_pending(command.manager_email):
            raise DomainError(
                f"Un dossier est déjà en attente pour l'adresse {command.manager_email!r}. "
                "Vous serez contacté par email dès que votre demande sera traitée."
            )

        # 5. Création du dossier
        registration_id = self._repo.create(
            client_uuid        = command.client_uuid or None,
            school_name        = command.school_name.strip(),
            city               = command.city.strip(),
            country_code       = command.country_code.strip().upper(),
            manager_first_name = command.manager_first_name.strip(),
            manager_last_name  = command.manager_last_name.strip(),
            manager_email      = command.manager_email.strip().lower(),
            manager_phone      = command.manager_phone.strip(),
            payment_methods    = payment_methods,
            mobile_operator    = command.mobile_operator.strip(),
            mobile_number      = command.mobile_number.strip(),
        )

        return RegisterSchoolResult(success=True, registration_id=registration_id)

    def _validate_operator(self, country_code: str, operator: str) -> None:
        from economat.infrastructure.models import CountryModel
        try:
            country = CountryModel.objects.get(code=country_code.upper())
            known = country.mobile_operators or []
            if known and operator not in known:
                raise DomainError(
                    f"L'opérateur « {operator} » n'est pas disponible au {country.name}. "
                    f"Opérateurs disponibles : {', '.join(known)}."
                )
        except CountryModel.DoesNotExist:
            raise DomainError(f"Pays « {country_code} » introuvable.")
