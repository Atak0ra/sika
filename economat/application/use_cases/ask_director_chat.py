"""
application/use_cases/ask_director_chat.py
============================================
USE CASE (Query) : AskDirectorChatQuery — Acteur : Directeur
Action           : Poser une question en langage naturel sur les données de l'école

C'est une QUERY (lecture seule) — pas d'écriture en base.
Le LLM traduit la question en SQL → exécuté via django.db.connection
(la vraie base du projet : SQLite en dev, Postgres en prod).
"""

from __future__ import annotations

from economat.application.dto import AskDirectorChatCommand, AskDirectorChatResult
from economat.application.ports.llm_port import ChatMessage, LLMPort

# Contexte métier injecté dans le prompt LLM
_ECONOMAT_CONTEXT = """
Tu analyses les données d'un système de gestion d'économat scolaire en Afrique de l'Ouest.

Schéma des tables :
- economat_school      : écoles        (id, name, city, country, tolerance_days)
- economat_school_year : années sco.   (id, school_id, label ex."2025-2026", status ACTIVE/DRAFT/CLOSED)
- economat_level       : niveaux       (id, school_year_id, name, annual_fee entier FCFA, payment_mode)
- economat_class       : classes       (id, level_id, name, capacity)
- economat_student     : identité élève (id, school_id, first_name, last_name, date_of_birth)
- economat_enrollment  : inscription   (id, student_id, school_year_id, level_id,
                                        class_id, enrollment_date, status ACTIVE/INACTIVE/PROMOTED)
- economat_payment     : paiements     (id, enrollment_id, student_id, amount entier FCFA,
                                        payment_date, method ESPECES/MOBILE_MONEY/VIREMENT/CHEQUE,
                                        receipt_number, state VALID/CANCELLED, recorded_by, created_at)

Règles importantes :
- Un élève = une ligne dans economat_student. Son inscription annuelle = economat_enrollment.
- Pour compter les élèves d'une année : COUNT sur economat_enrollment WHERE school_year_id=? AND status='ACTIVE'.
- Pour les paiements : SUM(amount) sur economat_payment WHERE state='VALID'.
- Les montants sont en FCFA (entiers).
- Toujours filtrer par school_year_id pour isoler une année scolaire.
- Génère du SQL standard (compatible PostgreSQL et SQLite), SELECT uniquement.
- Ne génère PAS de INSERT, UPDATE, DELETE, DROP, ALTER.
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
        history = [
            ChatMessage(role=m["role"], content=m["content"])
            for m in command.history
            if "role" in m and "content" in m
        ]

        enriched_question = (
            f"{command.question}\n"
            f"[Contexte : school_id='{command.school_id}', year_id='{command.year_id}'"
            + (f", année scolaire='{command.school_year_label}'" if command.school_year_label else "")
            + "]"
        )

        result = self._llm.answer(
            question=enriched_question,
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
