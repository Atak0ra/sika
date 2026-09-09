"""
db_connector.py - Gestion des sources de donnees externes.
Supporte SQLite interne, SQLite externe, CSV (via pandas).
"""
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from django.conf import settings


_EXT_TO_TYPE = {
    ".db": "sqlite", ".sqlite": "sqlite", ".sqlite3": "sqlite",
    ".csv": "csv",
    ".xlsx": "excel", ".xls": "excel",
}


def _detect_source_type(filename: str) -> str | None:
    """Devine le type reel depuis l'extension — plus fiable que l'onglet clique cote client."""
    return _EXT_TO_TYPE.get(Path(filename).suffix.lower())


def _slug(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"[^a-zA-Z0-9_]", "_", stem).strip("_").lower() or "data"


def _as_list(v) -> list:
    """Normalise un champ mono/multi-fichier (str ou list) en liste."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def _concat_same_structure(dfs: list, names: list) -> tuple:
    """Concatene des DataFrames dont les colonnes doivent etre identiques.

    Retourne (df_concatene, None) ou (None, message_erreur).
    """
    ref_cols = None
    for name, df in zip(names, dfs):
        cols = frozenset(str(c).strip().lower() for c in df.columns)
        if ref_cols is None:
            ref_cols = cols
        elif cols != ref_cols:
            return None, (
                f"Colonnes incompatibles : '{name}' n'a pas les memes colonnes que les "
                "autres fichiers. Verifiez que tous les fichiers ont la meme structure."
            )
    import pandas as pd
    return pd.concat(dfs, ignore_index=True), None


def _sqlite_tables(conn: sqlite3.Connection) -> list:
    skip = ("sqlite_%", "django_%", "auth_%", "contenttypes%", "sessions_%", "admin_%")
    where = " AND ".join(f"name NOT LIKE '{p}'" for p in skip)
    cur = conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND {where} ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def _table_info(conn: sqlite3.Connection, table: str) -> dict:
    try:
        cols = [{"name": r[1], "type": r[2]} for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
        rows = [list(r) for r in conn.execute(f'SELECT * FROM "{table}" LIMIT 3').fetchall()]
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        return {"columns": cols, "preview_rows": rows, "row_count": count}
    except Exception as e:
        return {"columns": [], "preview_rows": [], "row_count": 0, "error": str(e)}


def _read_csv_df(csv_path: str):
    import pandas as pd
    with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
        sample = f.read(4096)
    sep = ";" if sample.count(";") > sample.count(",") else ","
    return pd.read_csv(csv_path, sep=sep, encoding="utf-8-sig", on_bad_lines="skip")


def csv_to_sqlite(csv_paths, table_name: str = None) -> dict:
    """Convertit un ou plusieurs CSV (meme structure) en une table sqlite.

    *csv_paths* : chemin unique (str) ou liste de chemins a concatener.
    """
    result = {"sqlite_path": None, "table_name": None, "columns": [], "row_count": 0, "error": None}
    paths = _as_list(csv_paths)
    try:
        dfs = [_read_csv_df(p) for p in paths]
        if len(dfs) > 1:
            df, err = _concat_same_structure(dfs, [Path(p).name for p in paths])
            if err:
                result["error"] = err
                return result
        else:
            df = dfs[0]
        return _df_to_sqlite(df, paths[0], table_name)
    except Exception as e:
        result["error"] = str(e)
        return result


def _excel_sheets(xlsx_path: str) -> list:
    import pandas as pd
    return pd.ExcelFile(xlsx_path).sheet_names


def excel_to_sqlite(xlsx_paths, sheet_name: str, table_name: str = None) -> dict:
    """Convertit une feuille (meme nom) d'un ou plusieurs fichiers Excel en une table sqlite.

    *xlsx_paths* : chemin unique (str) ou liste de chemins a concatener.
    """
    result = {"sqlite_path": None, "table_name": None, "columns": [], "row_count": 0, "error": None}
    paths = _as_list(xlsx_paths)
    try:
        import pandas as pd
        dfs = [pd.read_excel(p, sheet_name=sheet_name) for p in paths]
        if len(dfs) > 1:
            df, err = _concat_same_structure(dfs, [Path(p).name for p in paths])
            if err:
                result["error"] = err
                return result
        else:
            df = dfs[0]
        return _df_to_sqlite(df, table_name or sheet_name, table_name)
    except Exception as e:
        result["error"] = str(e)
        return result


def _df_to_sqlite(df, name_hint: str, table_name: str = None) -> dict:
    """Ecrit *df* dans un nouveau fichier sqlite temporaire, retourne les metadonnees."""
    df.columns = [re.sub(r"[^a-zA-Z0-9_]", "_", str(c)).strip("_").lower() or f"col_{i}" for i, c in enumerate(df.columns)]
    tname = table_name or _slug(name_hint)
    tmp_dir = Path(settings.MEDIA_ROOT) / "tmp_dbs"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    sqlite_path = str(tmp_dir / f"{uuid.uuid4().hex}.db")
    conn = sqlite3.connect(sqlite_path)
    df.to_sql(tname, conn, if_exists="replace", index=False)
    conn.close()
    return {
        "sqlite_path": sqlite_path, "table_name": tname,
        "columns": list(df.columns), "row_count": len(df), "error": None,
    }


def _json_safe(v):
    """Remplace NaN/NaT (non serialisables en JSON strict) par None."""
    try:
        import pandas as pd
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _excel_preview(xlsx_path: str, sheet_name: str) -> dict:
    try:
        import pandas as pd
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
        cols = [{"name": str(c), "type": str(t)} for c, t in zip(df.columns, df.dtypes)]
        preview_rows = [[_json_safe(v) for v in row] for row in df.head(3).values.tolist()]
        return {"columns": cols, "preview_rows": preview_rows, "row_count": len(df)}
    except Exception as e:
        return {"columns": [], "preview_rows": [], "row_count": 0, "error": str(e)}


def test_connection(source_config: dict) -> dict:
    result = {"ok": False, "tables": [], "active_table": None, "table_info": {}, "error": None}
    raw_paths = _as_list(source_config.get("raw_path"))

    if raw_paths and not source_config.get("sqlite_path"):
        # Fichier(s) pas encore converti(s) (ex: Excel) — on liste juste les feuilles
        # du premier fichier, pris comme reference pour tous les autres.
        reference = raw_paths[0]
        if not Path(reference).exists():
            result["error"] = f"Fichier introuvable : {reference}"
            return result
        try:
            sheets = _excel_sheets(reference)
        except Exception as e:
            result["error"] = str(e)
            return result
        if not sheets:
            result["error"] = "Aucune feuille trouvee dans ce fichier."
            return result
        active = source_config.get("active_table") or sheets[0]
        if active not in sheets:
            active = sheets[0]
        result.update({"ok": True, "tables": sheets, "active_table": active, "table_info": _excel_preview(reference, active)})
        return result

    try:
        db_path = source_config.get("sqlite_path", "")
        if not db_path or not Path(db_path).exists():
            result["error"] = f"Fichier introuvable : {db_path}"
            return result
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        tables = _sqlite_tables(conn)
        if not tables:
            result["error"] = "Aucune table trouvee dans cette base."
            conn.close()
            return result
        active = source_config.get("active_table") or tables[0]
        if active not in tables:
            active = tables[0]
        result.update({"ok": True, "tables": tables, "active_table": active, "table_info": _table_info(conn, active)})
        conn.close()
    except Exception as e:
        result["error"] = str(e)
    return result


def _save_upload(uploaded_file) -> str:
    """Sauvegarde un fichier uploade sur disque, retourne son chemin."""
    upload_dir = Path(settings.MEDIA_ROOT) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", uploaded_file.name)
    dest_path = str(upload_dir / f"{uuid.uuid4().hex}_{safe_name}")
    with open(dest_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)
    return dest_path


def _combined_label(names: list) -> str:
    if len(names) == 1:
        return names[0]
    return f"{names[0]} (+{len(names) - 1} autre{'s' if len(names) > 2 else ''})"


def prepare_from_upload(uploaded_files, source_type: str) -> dict:
    """Sauvegarde un ou plusieurs fichiers uploades et prepare la source de donnees.

    *uploaded_files* : un fichier unique, ou une liste (transactions du client
    eclatees en plusieurs CSV/Excel de meme structure).
    """
    result = {"ok": False, "source_config": {}, "error": None}
    files = _as_list(uploaded_files)
    is_multi = len(files) > 1

    # Le type declare vient de l'onglet clique cote client — pas fiable si le
    # JS de l'onglet n'a pas tourne. On se fie plutot a l'extension reelle.
    detected = {_detect_source_type(f.name) for f in files}
    detected.discard(None)
    if len(detected) > 1:
        result["error"] = "Les fichiers envoyes ne sont pas du meme type (melange CSV/Excel/SQLite)."
        return result
    if len(detected) == 1:
        source_type = detected.pop()

    if source_type == "sqlite" and is_multi:
        result["error"] = "Une seule base SQLite peut etre choisie a la fois."
        return result

    try:
        dest_paths = [_save_upload(f) for f in files]
        original_names = [f.name for f in files]
        label = _combined_label(original_names)

        if source_type == "sqlite":
            result.update({"ok": True, "source_config": {
                "type": "sqlite", "sqlite_path": dest_paths[0],
                "original_name": original_names[0], "active_table": None, "label": label,
            }})
        elif source_type == "csv":
            conv = csv_to_sqlite(dest_paths if is_multi else dest_paths[0])
            if conv["error"]:
                result["error"] = "Erreur CSV : " + conv["error"]
            else:
                result.update({"ok": True, "source_config": {
                    "type": "csv", "sqlite_path": conv["sqlite_path"],
                    "original_name": label, "active_table": conv["table_name"],
                    "label": label, "columns": conv["columns"], "row_count": conv["row_count"],
                }})
        elif source_type == "excel":
            # Pas de conversion ici : on attend le choix de la feuille (voir test_connection).
            result.update({"ok": True, "source_config": {
                "type": "excel", "sqlite_path": None,
                "raw_path": dest_paths if is_multi else dest_paths[0],
                "original_name": label, "active_table": None, "label": label,
            }})
        else:
            result["error"] = "Type inconnu."
    except Exception as e:
        result["error"] = str(e)
    return result


def prepare_from_path(file_path: str, source_type: str) -> dict:
    result = {"ok": False, "source_config": {}, "error": None}
    if not Path(file_path).exists():
        result["error"] = f"Fichier introuvable : {file_path}"
        return result
    name = Path(file_path).name
    if source_type == "sqlite":
        result.update({"ok": True, "source_config": {
            "type": "sqlite", "sqlite_path": file_path,
            "original_name": name, "active_table": None, "label": name,
        }})
    elif source_type == "csv":
        conv = csv_to_sqlite(file_path)
        if conv["error"]:
            result["error"] = "Erreur CSV : " + conv["error"]
        else:
            result.update({"ok": True, "source_config": {
                "type": "csv", "sqlite_path": conv["sqlite_path"],
                "original_name": name, "active_table": conv["table_name"], "label": name,
            }})
    elif source_type == "excel":
        result.update({"ok": True, "source_config": {
            "type": "excel", "sqlite_path": None, "raw_path": file_path,
            "original_name": name, "active_table": None, "label": name,
        }})
    else:
        result["error"] = "Type inconnu."
    return result


def get_internal_source() -> dict:
    return {
        "type": "internal",
        "sqlite_path": str(settings.SQLITE_DB_PATH),
        "original_name": "Base interne",
        "active_table": "analytics_transaction",
        "label": "Base interne - Transactions",
    }
