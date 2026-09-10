"""
sql_guard.py — Garde-fous read-only pour les requêtes SQL générées par le LLM.

Double protection :
  1. Validation stricte par regex : seuls les SELECT (et CTE WITH…SELECT) sont autorisés.
  2. Rejet immédiat de toute tentative DML/DDL/administration.

Utilisation :
    from economat.infrastructure.ai.sql_guard import validate_read_only, UnsafeSQLError

    try:
        clean_sql = validate_read_only(raw_sql_from_llm)
    except UnsafeSQLError as e:
        # afficher l'erreur à l'utilisateur, ne pas exécuter
        ...
"""

import re

# ── Mots-clés interdits (DML / DDL / administration SQLite) ──────────────────
_FORBIDDEN_KEYWORDS = re.compile(
    r"""
    \b(
        INSERT      |
        UPDATE      |
        DELETE      |
        DROP        |
        ALTER       |
        CREATE      |
        REPLACE     |
        TRUNCATE    |
        ATTACH      |
        DETACH      |
        PRAGMA      |
        VACUUM      |
        REINDEX     |
        ANALYZE     |
        SAVEPOINT   |
        RELEASE     |
        ROLLBACK    |
        COMMIT      |
        BEGIN       |
        GRANT       |
        REVOKE
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ── Commentaires SQL qui pourraient masquer du code ───────────────────────────
_SQL_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)

# ── La requête nettoyée doit commencer par SELECT ou WITH (pour les CTE) ─────
_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)


class UnsafeSQLError(ValueError):
    """Levée quand le SQL généré contient des opérations non-SELECT."""

    def __init__(self, reason: str, sql: str | None = None):
        self.reason = reason
        self.sql = sql
        super().__init__(reason)


def validate_read_only(sql: str) -> str:
    """
    Valide que *sql* est une requête en lecture seule (SELECT uniquement).

    Retourne le SQL nettoyé (stripped) si valide.
    Lève UnsafeSQLError sinon.
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("La requête SQL est vide.", sql=sql)

    # 1. Supprimer les commentaires pour éviter les injections cachées
    sql_no_comments = _SQL_COMMENT.sub(" ", sql).strip()

    # 2. Vérifier qu'il n'y a pas de multi-statements (injection via ;)
    #    On tolère un seul ; optionnel en fin de requête
    cleaned = sql_no_comments.rstrip("; \t\n\r")
    if ";" in cleaned:
        raise UnsafeSQLError(
            "Requête multi-instructions détectée (présence de ';' en milieu de requête). "
            "Seules les requêtes SELECT simples sont autorisées.",
            sql=sql,
        )

    # 3. Vérifier l'absence de mots-clés DML / DDL
    match = _FORBIDDEN_KEYWORDS.search(cleaned)
    if match:
        raise UnsafeSQLError(
            f"Opération interdite détectée : '{match.group().upper()}'. "
            "Seules les requêtes SELECT sont autorisées (lecture seule).",
            sql=sql,
        )

    # 4. La requête doit commencer par SELECT ou WITH
    if not _ALLOWED_START.match(cleaned):
        raise UnsafeSQLError(
            "La requête générée ne commence pas par SELECT ou WITH. "
            "Seules les requêtes en lecture seule sont acceptées.",
            sql=sql,
        )

    # Retourne le SQL propre (sans ; final)
    return cleaned
