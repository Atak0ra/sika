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

Schéma réel des tables (SQLite) :
- economat_school      : écoles        (id UUID, name, city, country, tolerance_days)
- economat_school_year : années sco.   (id UUID, school_id→school, label ex."2025-2026", status ACTIVE/DRAFT/CLOSED)
- economat_level       : niveaux       (id UUID, school_year_id→school_year, name, annual_fee entier FCFA, payment_mode)
- economat_class       : classes       (id UUID, level_id→level, name, capacity)
- economat_student     : identité élève (id UUID, school_id→school, first_name, last_name, date_of_birth)
- economat_enrollment  : inscription   (id UUID, student_id→student, school_year_id→school_year,
                                        level_id→level, class_id→class, enrollment_date, status ACTIVE/INACTIVE/PROMOTED)
- economat_payment     : paiements     (id UUID, enrollment_id→enrollment, amount entier FCFA,
                                        payment_date, method ESPECES/MOBILE/VIREMENT/CHEQUE,
                                        receipt_number, state VALID/CANCELLED, created_at)

Règles importantes :
- Un élève = une ligne dans economat_student. Son inscription annuelle = economat_enrollment.
- Pour compter les élèves d'une année : COUNT sur economat_enrollment WHERE school_year_id=? AND status='ACTIVE'.
- Pour les paiements : SUM(amount) sur economat_payment WHERE state='VALID'.
- Les montants sont en FCFA (entiers).
- Toujours filtrer par school_year_id pour isoler une année scolaire.
- Génère du SQL SQLite valide, SELECT uniquement (pas d'INSERT/UPDATE/DELETE).
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

        # La question enrichie avec le contexte de l'année scolaire et de l'école
        enriched_question = (
            f"{command.question}\n"
            f"[Contexte : school_id='{command.school_id}', year_id='{command.year_id}'"
            + (f", année scolaire='{command.school_year_label}'" if command.school_year_label else "")
            + "]"
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
