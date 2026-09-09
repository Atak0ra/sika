"""
application/use_cases/create_collaborator.py
==============================================
USE CASE : CreateCollaboratorUseCase
Acteur   : Directeur (depuis la page Équipe)
Action   : Créer directement le compte d'un collaborateur (secrétaire / économe)
           avec identifiant + mot de passe provisoire fournis par le directeur.

Flux :
  1. Vérifier que l'appelant est bien DIRECTOR de l'école.
  2. Valider le username (non vide, non déjà pris).
  3. Créer le compte via UserRepository.
  4. Créer le Membership(role=SECRETARY|ECONOME) lié à l'école.
  5. Retourner CreateCollaboratorResult.

Règle : un collaborateur peut être rattaché à plusieurs écoles (un économe
multi-établissements). Le username est global (unicité Django).
"""

from __future__ import annotations

from economat.application.dto_identity import CreateCollaboratorCommand, CreateCollaboratorResult
from economat.application.ports.identity_repositories import MembershipRepository, UserRepository
from economat.domain.identity.entities import Membership, UnauthorizedError
from economat.domain.identity.value_objects import Role
from economat.domain.school.value_objects import SchoolId
from economat.domain.shared.errors import DomainError, DuplicateEntityError, EntityNotFoundError


class CreateCollaboratorUseCase:

    def __init__(
        self,
        user_repo: UserRepository,
        membership_repo: MembershipRepository,
    ) -> None:
        self._users       = user_repo
        self._memberships = membership_repo

    def execute(self, command: CreateCollaboratorCommand) -> CreateCollaboratorResult:
        try:
            return self._execute(command)
        except (DomainError, UnauthorizedError) as e:
            return CreateCollaboratorResult(success=False, error_message=str(e))
        except Exception as e:  # noqa: BLE001
            return CreateCollaboratorResult(success=False, error_message=f"Erreur inattendue : {e}")

    def _execute(self, command: CreateCollaboratorCommand) -> CreateCollaboratorResult:
        school_id = SchoolId(command.school_id)

        # 1. Vérifier que l'appelant est DIRECTOR de cette école
        director_membership = self._memberships.find_by_user_and_school(
            command.director_user_id, school_id
        )
        if director_membership is None:
            raise EntityNotFoundError("Vous n'êtes pas membre de cette école.")
        director_membership.guard_manage_team()

        # 2. Validation du username
        username = command.username.strip().lower()
        if not username:
            raise DomainError("L'identifiant de connexion est obligatoire.")
        if len(command.password) < 6:
            raise DomainError("Le mot de passe doit contenir au moins 6 caractères.")
        if not command.first_name.strip() or not command.last_name.strip():
            raise DomainError("Le prénom et le nom sont obligatoires.")
        if command.role not in (Role.SECRETARY.value, Role.ECONOME.value):
            raise DomainError(f"Rôle invalide : {command.role!r}. Choisir SECRETARY ou ECONOME.")
        if self._users.username_exists(username):
            raise DuplicateEntityError(
                f"L'identifiant « {username} » est déjà utilisé. Choisissez-en un autre."
            )

        # 3. Création du compte utilisateur
        display_name = f"{command.first_name.strip()} {command.last_name.strip().upper()}"
        user_id = self._users.create_user(
            username=username,
            password=command.password,
            first_name=command.first_name.strip(),
            last_name=command.last_name.strip(),
        )

        # 4. Création du Membership
        membership = Membership(
            id=self._memberships.next_id(),
            user_id=user_id,
            school_id=school_id,
            role=Role(command.role),
            display_name=display_name,
            login=username,
            is_active=True,
            created_by=command.director_user_id,
        )
        self._memberships.save(membership)

        return CreateCollaboratorResult(
            success=True,
            user_id=user_id,
            username=username,
            display_name=display_name,
            role=command.role,
        )
