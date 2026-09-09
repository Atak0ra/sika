"""
llm_service.py — Service LangChain + Groq pour le Text-to-SQL.

Etapes :
  1. Classification d'intention (analytique vs conversationnel)
  2a. Si conversationnel -> reponse directe en langage naturel
  2b. Si analytique     -> generation SQL + validation read-only + execution SQLite

Retourne :
  { "intent", "chat_reply", "sql", "columns", "rows", "error" }
"""

import os
import re
import sqlite3
from typing import Any

from django.conf import settings
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*langchain.*", category=UserWarning)

from langchain_community.utilities import SQLDatabase
from langchain_classic.chains import create_sql_query_chain
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from .sql_guard import validate_read_only, UnsafeSQLError


_INTENT_SYSTEM = (
    "Tu es un classificateur d'intention pour une application d'analyse de transactions financieres. "
    "Reponds UNIQUEMENT par un seul mot : "
    "'analytical' si la question porte sur des donnees (transactions, montants, commissions, agents, pays, statuts, dates, statistiques). "
    "'conversational' pour tout le reste (salutations, blagues, questions sur toi, hors-sujet). "
    "Aucune ponctuation, aucune explication. Un seul mot."
)

_CHAT_SYSTEM = (
    "Tu es un assistant sympathique integre a une application d'analyse de transactions financieres. "
    "L'utilisateur t'a envoye un message qui n'est pas analytique. "
    "Reponds de facon chaleureuse et concise (2-3 phrases max). "
    "Si c'est une salutation, salue-le et propose de l'aider a analyser ses donnees de transactions. "
    "Reponds toujours en francais."
)


def _make_llm(api_key: str) -> ChatGroq:
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    return ChatGroq(model=model, api_key=api_key, temperature=0)


def _clean_sql(raw: str) -> str:
    raw = re.sub(r"```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"```", "", raw)
    raw = re.sub(r"(?i)^(sql\s*query\s*:|sql\s*:|sqlquery\s*:)\s*", "", raw.strip())
    return raw.strip()


# Colonnes à ne jamais afficher (identifiants techniques internes)
_ID_COLS = re.compile(r"^(id|uuid|guid|pk)$", re.IGNORECASE)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _filter_id_columns(cols: list, rows: list) -> tuple[list, list]:
    """Retire les colonnes id/UUID des résultats avant affichage."""
    if not cols:
        return cols, rows
    keep = [
        i for i, col in enumerate(cols)
        if not _ID_COLS.match(col)
        and not all(
            _UUID_RE.match(str(r[i])) for r in rows[:5] if r[i] is not None
        )
    ]
    if len(keep) == len(cols):
        return cols, rows          # rien à filtrer
    filtered_cols = [cols[i] for i in keep]
    filtered_rows = [tuple(r[i] for i in keep) for r in rows]
    return filtered_cols, filtered_rows


def _classify(question: str, llm: ChatGroq) -> str:
    """Retourne 'analytical' ou 'conversational'. Fallback sur 'analytical'."""
    try:
        resp = llm.invoke([
            SystemMessage(content=_INTENT_SYSTEM),
            HumanMessage(content=question),
        ])
        word = resp.content.strip().lower().rstrip(".")
        return "conversational" if "conversational" in word else "analytical"
    except Exception:
        return "analytical"


def _converse(question: str, llm: ChatGroq) -> str:
    """Genere une reponse conversationnelle naturelle."""
    try:
        resp = llm.invoke([
            SystemMessage(content=_CHAT_SYSTEM),
            HumanMessage(content=question),
        ])
        return resp.content.strip()
    except Exception:
        return "Bonjour ! Je suis votre assistant d'analyse de transactions. Posez-moi une question sur vos donnees."


def answer_question(question: str, db_path: str = None, table: str = None) -> dict[str, Any]:
    """
    Traduit une question en SQL, l'exécute et retourne les données.

    Args:
        question : question en langage naturel
        db_path  : chemin vers la base SQLite (None = base interne du projet)
        table    : table à interroger (None = auto-détecté depuis la base)
    """
    from django.conf import settings as dj_settings
    _db_path = db_path or str(dj_settings.SQLITE_DB_PATH)

    result: dict[str, Any] = {
        "intent": "analytical", "chat_reply": None,
        "sql": "", "columns": [], "rows": [], "error": None,
    }

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key or api_key.startswith("gsk_xxx"):
        result["error"] = (
            "Cle API Groq manquante ou invalide. "
            "Definissez GROQ_API_KEY dans votre fichier .env "
            "(obtenez une cle gratuite sur https://console.groq.com/keys)."
        )
        return result

    try:
        llm = _make_llm(api_key)

        # Etape 1 : classification d'intention
        intent = _classify(question, llm)
        result["intent"] = intent

        # Etape 2a : reponse conversationnelle
        if intent == "conversational":
            result["chat_reply"] = _converse(question, llm)
            return result

        # Etape 2b : pipeline analytique
        # Détermine la table active dynamiquement
        with sqlite3.connect(f"file:{_db_path}?mode=ro", uri=True) as _c:
            _tables = [r[0] for r in _c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE 'django_%' AND name NOT LIKE 'auth_%'"
            ).fetchall()]
        _active_table = table if (table and table in _tables) else (_tables[0] if _tables else "data")

        db = SQLDatabase.from_uri(
            f"sqlite:///{_db_path}",
            include_tables=[_active_table],
            sample_rows_in_table_info=3,
        )
        chain = create_sql_query_chain(llm, db)
        enriched = (
            f"{question}\n\n"
            f"IMPORTANT: generate ONLY a valid SQLite SELECT query. "
            f"The table name is '{_active_table}'. "
            "NEVER select the 'id' column — it is an internal UUID with no value for the user. "
            "Select only meaningful columns relevant to the question. "
            "Output raw SQL only, no explanation."
        )
        raw_sql = chain.invoke({"question": enriched})
        sql = _clean_sql(str(raw_sql))
        result["sql"] = sql

        safe_sql = validate_read_only(sql)

        with sqlite3.connect(f"file:{_db_path}?mode=ro", uri=True) as conn:
            cursor = conn.execute(safe_sql)
            cols = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(500)

        # Filtre défensif UUID/id
        cols, rows = _filter_id_columns(cols, rows)

        result["columns"] = cols
        result["rows"]    = rows

    except UnsafeSQLError as e:
        result["error"] = f"Requete bloquee par le garde-fous : {e.reason}"
    except sqlite3.OperationalError as e:
        result["error"] = f"Erreur SQLite : {e}\nSQL : {result.get('sql', 'N/A')}"
    except Exception as e:  # noqa: BLE001
        result["error"] = f"Erreur ({type(e).__name__}) : {e}"

    return result
