"""
application/use_cases/ask_director_chat.py
============================================
USE CASE (Query) : AskDirectorChatQuery — Acteur : Directeur
Action           : Poser une question en langage naturel sur les données de l'école

C'est une QUERY (lecture seule) — pas d'écriture en base.
Le LLM traduit la question en SQL → exécuté en read-only → résultat tabulaire.

Le port LLMPort abstrait la technologie (Groq, OpenAI…).
Le garde-fou SQL (sql_guard) est dans l'implémentation de l'adapter.

Contexte métier injecté dans le prompt LLM :
- Le schéma des tables de l'économat (pour que le LLM génère du SQL pertinent).
- Le vocabulaire métier (élève, classe, niveau, paiement, tranche, solde…).
"""

from __future__ import annotations

from django.conf import settings  # Seule dépendance Django autorisée ici : chemin DB

from economat.application.dto import AskDirectorChatCommand, AskDirectorChatResult
from economat.application.ports.llm_port import LLMPort, ChatMessage

# Contexte métier injecté dans le prompt LLM pour améliorer la qualité du SQL
_ECONOMAT_CONTEXT = """
Tu analyses les données d'un système de gestion d'économat scolaire en Afrique de l'Ouest.
Tables principales :
- economat_student  : élèves (id, first_name, last_name, class_id, level_id, school_id, status, enrollment_date)
- economat_class    : classes (id, name, level_id, capacity)
- economat_level    : niveaux scolaires (id, name, annual_fee, payment_mode)
- economat_payment  : paiements enregistrés (id, student_id, amount, payment_date, method, receipt_number, state, school_year)
- economat_school   : écoles (id, name, city, country)

Vocabulaire métier :
- "frais" ou "scolarité" = annual_fee (montant en FCFA)
- "en retard" = élèves dont le total payé est inférieur aux échéances passées
- "soldé" = élèves ayant payé le montant total annuel
- "économe" = celui qui enregistre les paiements
- "directeur" = utilisateur qui consulte les statistiques
- Les montants sont en FCFA (entiers, pas de décimales).
Génère du SQL SQLite valide, en lecture seule uniquement (SELECT).
""".strip()


class AskDirectorChatQuery:
    """Query d'exploration des données par le directeur via le langage naturel."""

    def __init__(self, llm_port: LLMPort) -> None:
        self._llm = llm_port

    def execute(self, command: AskDirectorChatCommand) -> AskDirectorChatResult:
        try:
            return self._execute(command)
        except Exception as e:  # noqa: BLE001
            return AskDirectorChatResult(
                success=False,
                error_message=f"Erreur lors de l'analyse : {type(e).__name__} — {e}",
            )

    def _execute(self, command: AskDirectorChatCommand) -> AskDirectorChatResult:
        # Reconstruction de l'historique de conversation pour le contexte LLM
        history = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in command.history
            if "role" in m and "content" in m
        ]

        # La question enrichie avec l'année scolaire filtre
        enriched_question = (
            f"{command.question}\n"
            f"[Filtrer sur l'année scolaire : {command.school_year}]"
        )

        # Chemin de la base SQLite (partagée — même db.sqlite3 que tout le projet)
        db_path = str(settings.SQLITE_DB_PATH)

        result = self._llm.answer(
            question=enriched_question,
            db_path=db_path,
            table=None,  # auto-détection parmi les tables economat_*
            history=history,
            system_context=_ECONOMAT_CONTEXT,
        )

        if result.is_error:
            return AskDirectorChatResult(
                success=False, error_message=result.error
            )

        return AskDirectorChatResult(
            success=True,
            intent=result.intent,
            chat_reply=result.chat_reply,
            sql=result.sql,
            columns=result.columns,
            rows=list(result.rows),
        )
