"""
infrastructure/ai/groq_llm_adapter.py
=======================================
Adapter LLM — Groq via LangChain pour le Text-to-SQL économat.

- Implémente LLMPort (contrat domaine/application).
- Exécute le SQL via django.db.connection — la vraie base du projet
  (SQLite en dev, Postgres en prod). Plus de db_path SQLite codé en dur.
- Protégé par sql_guard (read-only).
- Historique de conversation intégré au contexte LLM.
"""

from __future__ import annotations

import os
import re
import warnings
from typing import List, Optional

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*langchain.*", category=UserWarning)

from django.db import connection

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq

from economat.application.ports.llm_port import ChatMessage, LLMPort, LLMQueryResult
from economat.infrastructure.ai.sql_guard import UnsafeSQLError, validate_read_only


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_llm(api_key: str) -> ChatGroq:
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    return ChatGroq(model=model, api_key=api_key, temperature=0)


def _clean_sql(raw: str) -> str:
    """Supprime les balises markdown et préfixes parasites générés par le LLM."""
    raw = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```", "", raw)
    raw = re.sub(r"(?i)^(sql\s*query\s*:|sql\s*:|sqlquery\s*:)\s*", "", raw.strip())
    return raw.strip()


def _get_economat_table_schema() -> str:
    """
    Introspecte le schéma des tables economat_* via django.db.connection.
    Fonctionne avec SQLite ET Postgres.
    Retourne une chaîne décrivant les colonnes de chaque table
    pour alimenter le prompt LLM.
    """
    schema_lines = []
    table_names = [
        name for name in connection.introspection.table_names()
        if name.startswith("economat_")
    ]
    for table in sorted(table_names):
        try:
            cols = connection.introspection.get_table_description(connection.cursor(), table)
            col_list = ", ".join(c.name for c in cols)
            schema_lines.append(f"- {table} ({col_list})")
        except Exception:
            schema_lines.append(f"- {table}")
    return "\n".join(schema_lines) if schema_lines else "(aucune table economat_ trouvée)"


def _execute_sql(sql: str) -> tuple[list[str], list[tuple]]:
    """
    Exécute le SQL via django.db.connection (read-only coté applicatif —
    le garde-fous sql_guard a déjà validé que c'est un SELECT).
    Fonctionne avec SQLite ET Postgres.
    """
    with connection.cursor() as cursor:
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(500)
    return columns, rows


def _build_history_messages(history: List[ChatMessage]) -> list:
    """Convertit l'historique ChatMessage en messages LangChain (Human/AI)."""
    msgs = []
    for msg in history:
        if msg.role == "user":
            msgs.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            msgs.append(AIMessage(content=msg.content))
    return msgs


# ── Adapter ───────────────────────────────────────────────────────────────────

class GroqLLMAdapter(LLMPort):
    """Adapter LLM concret — Groq pour le Text-to-SQL économat.

    SQL exécuté via django.db.connection → base du projet
    (SQLite en dev, Postgres en prod).
    """

    _INTENT_SYSTEM = (
        "Tu es un classificateur d'intention pour une application de gestion d'économat scolaire. "
        "Réponds UNIQUEMENT par un seul mot : 'analytical' si la question porte sur des données "
        "(élèves, paiements, montants, retards, classes, niveaux), 'conversational' sinon. "
        "Un seul mot, sans ponctuation."
    )
    _CHAT_SYSTEM = (
        "Tu es l'assistant du directeur d'école. Réponds en français, 2-3 phrases max. "
        "Propose de l'aider à analyser les données de l'économat scolaire."
    )

    def answer(
        self,
        question: str,
        history: Optional[List[ChatMessage]] = None,
        system_context: Optional[str] = None,
    ) -> LLMQueryResult:
        result = LLMQueryResult(intent="analytical", chat_reply=None)
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key or api_key.startswith("gsk_xxx"):
            result.error = "Clé API Groq manquante. Définissez GROQ_API_KEY dans .env."
            return result

        history_msgs = _build_history_messages(history or [])

        try:
            llm = _make_llm(api_key)

            # ── Classification de l'intention ───────────────────────────
            intent_resp = llm.invoke([
                SystemMessage(content=self._INTENT_SYSTEM),
                *history_msgs[-6:],
                HumanMessage(content=question),
            ])
            intent = intent_resp.content.strip().lower().rstrip(".")
            result.intent = "conversational" if "conv" in intent else "analytical"

            if result.intent == "conversational":
                resp = llm.invoke([
                    SystemMessage(content=self._CHAT_SYSTEM),
                    *history_msgs[-10:],
                    HumanMessage(content=question),
                ])
                result.chat_reply = resp.content.strip()
                return result

            # ── Mode analytique : génération SQL ─────────────────────────
            # Schéma réel introspecté depuis la vraie base (SQLite ou Postgres)
            live_schema = _get_economat_table_schema()
            ctx = system_context or ""
            full_prompt = (
                f"{ctx}\n\n"
                f"Schéma réel des tables disponibles :\n{live_schema}\n\n"
                f"{question}\n\n"
                f"Génère UNIQUEMENT un SELECT SQL standard (compatible PostgreSQL). "
                f"SQL brut uniquement, sans explication, sans balise markdown."
            )

            sql_resp = llm.invoke([
                *history_msgs[-6:],
                HumanMessage(content=full_prompt),
            ])
            result.sql = _clean_sql(sql_resp.content)

            # ── Validation garde-fous ────────────────────────────────
            safe_sql = validate_read_only(result.sql)

            # ── Exécution via django.db.connection ────────────────────
            result.columns, result.rows = _execute_sql(safe_sql)

        except UnsafeSQLError as e:
            result.error = f"Requête bloquée (garde-fous) : {e.reason}"
        except Exception as e:  # noqa: BLE001
            result.error = f"Erreur ({type(e).__name__}) : {e}"

        return result
