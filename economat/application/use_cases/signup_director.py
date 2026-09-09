"""
application/use_cases/signup_director.py
==========================================
USE CASE : SignUpDirectorUseCase
Acteur   : Visiteur (futur directeur)
Action   : Créer son compte utilisateur

Flux :
  1. Valider que le username n'est pas déjà pris.
  2. Créer le compte via UserRepository.
  3. Retourner l'user_id pour que la vue connecte l'utilisateur.

NOTE : Pas d'école créée ici — l'onboarding est en 2 étapes séparées :
  1. SignUp (ce use case)     → crée le compte
  2. CreateSchoolUseCase      → crée l'école + Membership DIRECTOR
Cela permet d'inviter un collaborateur sur une école existante sans SignUp.
"""

from __future__ import annotations
from economat.application.dto_identity import SignUpDirectorCommand, SignUpResult
from economat.application.ports.identity_repositories import UserRepository
from economat.domain.shared.errors import DomainError, DuplicateEntityError


class SignUpDirectorUseCase:

    def __init__(self, user_repo: UserRepository) -> None:
        self._users = user_repo

    def execute(self, command: SignUpDirectorCommand) -> SignUpResult:
        try:
            return self._execute(command)
        except DomainError as e:
            return SignUpResult(success=False, error_message=str(e))
        except Exception as e:  # noqa: BLE001
            return SignUpResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, command: SignUpDirectorCommand) -> SignUpResult:
        # 1. Validation primitive
        if not command.username.strip():
            raise DomainError("L'identifiant de connexion ne peut pas être vide.")
        if len(command.password) < 6:
            raise DomainError("Le mot de passe doit contenir au moins 6 caractères.")
        if not command.first_name.strip() or not command.last_name.strip():
            raise DomainError("Le prénom et le nom sont obligatoires.")

        # 2. Unicité du username
        if self._users.username_exists(command.username.strip()):
            raise DuplicateEntityError(
                f"L'identifiant « {command.username} » est déjà utilisé. "
                "Choisissez-en un autre."
            )

        # 3. Création du compte
        user_id = self._users.create_user(
            username=command.username.strip().lower(),
            password=command.password,
            first_name=command.first_name.strip(),
            last_name=command.last_name.strip(),
            email=command.email.strip().lower(),
        )

        return SignUpResult(
            success=True,
            user_id=user_id,
            username=command.username.strip().lower(),
        )
