"""
infrastructure/ai/groq_llm_adapter.py
=======================================
Adapter LLM — implémentation du port LLMPort via Groq + LangChain.

Réutilise le pattern de analytics/llm_service.py mais :
- Implémente l'interface LLMPort (contrat du domaine/application).
- Accepte un system_context métier injecté (vocabulaire économat).
- Filtre les tables pour ne cibler que les tables economat_*.
- Protégé par le garde-fous sql_guard (read-only).
"""

from __future__ import annotations
import os, re, sqlite3, warnings
from typing import List, Optional

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*langchain.*", category=UserWarning)

from langchain_community.utilities import SQLDatabase
from langchain_classic.chains import create_sql_query_chain
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from analytics.sql_guard import validate_read_only, UnsafeSQLError
from economat.application.ports.llm_port import ChatMessage, LLMPort, LLMQueryResult

_SKIP_PREFIXES = ("sqlite_%", "django_%", "auth_%", "analytics_%", "contenttypes%", "sessions_%")


def _make_llm(api_key: str) -> ChatGroq:
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip()
    return ChatGroq(model=model, api_key=api_key, temperature=0)


def _clean_sql(raw: str) -> str:
    raw = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```", "", raw)
    raw = re.sub(r"(?i)^(sql\s*query\s*:|sql\s*:|sqlquery\s*:)\s*", "", raw.strip())
    return raw.strip()


def _get_economat_tables(db_path: str) -> list:
    skip_where = " AND ".join(f"name NOT LIKE '{p}'" for p in _SKIP_PREFIXES)
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows = conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' "
                f"AND name LIKE 'economat_%' AND {skip_where} ORDER BY name"
            ).fetchall()
            return [r[0] for r in rows]
    except Exception:
        return []


class GroqLLMAdapter(LLMPort):
    """Adapter LLM concret — Groq via LangChain pour le Text-to-SQL économat."""

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
        db_path: str,
        table: Optional[str] = None,
        history: Optional[List[ChatMessage]] = None,
        system_context: Optional[str] = None,
    ) -> LLMQueryResult:
        result = LLMQueryResult(intent="analytical", chat_reply=None)
        api_key = os.environ.get("GROQ_API_KEY", "").strip()
        if not api_key or api_key.startswith("gsk_xxx"):
            result.error = "Clé API Groq manquante. Définissez GROQ_API_KEY dans .env."
            return result

        try:
            llm = _make_llm(api_key)
            intent_resp = llm.invoke([
                SystemMessage(content=self._INTENT_SYSTEM),
                HumanMessage(content=question),
            ])
            intent = intent_resp.content.strip().lower().rstrip(".")
            result.intent = "conversational" if "conv" in intent else "analytical"

            if result.intent == "conversational":
                resp = llm.invoke([SystemMessage(content=self._CHAT_SYSTEM),
                                   HumanMessage(content=question)])
                result.chat_reply = resp.content.strip()
                return result

            tables = _get_economat_tables(db_path)
            if not tables:
                result.error = "Aucune table economat_ trouvée. Lancez d'abord migrate."
                return result
            active_table = table if (table and table in tables) else tables[0]

            db = SQLDatabase.from_uri(
                f"sqlite:///{db_path}", include_tables=[active_table], sample_rows_in_table_info=2,
            )
            chain = create_sql_query_chain(llm, db)
            ctx = system_context or ""
            enriched = (
                f"{ctx}\n\n{question}\n\n"
                f"IMPORTANT: génère UNIQUEMENT un SELECT SQLite. "
                f"Table principale : '{active_table}'. Ne sélectionne PAS 'id'. SQL brut uniquement."
            )
            raw_sql = chain.invoke({"question": enriched})
            result.sql = _clean_sql(str(raw_sql))
            safe_sql = validate_read_only(result.sql)

            with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
                cursor = conn.execute(safe_sql)
                result.columns = [d[0] for d in cursor.description] if cursor.description else []
                result.rows = list(cursor.fetchmany(500))

        except UnsafeSQLError as e:
            result.error = f"Requête bloquée (garde-fous) : {e.reason}"
        except sqlite3.OperationalError as e:
            result.error = f"Erreur SQLite : {e}\nSQL : {result.sql or 'N/A'}"
        except Exception as e:  # noqa: BLE001
            result.error = f"Erreur ({type(e).__name__}) : {e}"

        return result
