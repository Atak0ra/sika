"""Tests pour analytics/db_connector.py — support des sources externes."""
import json
import math
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from . import db_connector as dc


def _make_xlsx(path: str, sheets: dict) -> None:
    """Ecrit un .xlsx avec une feuille par entree de *sheets* {nom: DataFrame}."""
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)


def _make_csv(path: str, df: "pd.DataFrame") -> None:
    df.to_csv(path, index=False)


class ExcelToSqliteTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _xlsx_path(self, name="source.xlsx") -> str:
        return str(Path(self.tmp_dir.name) / name)

    def test_converts_chosen_sheet_into_sqlite_table(self):
        xlsx_path = self._xlsx_path()
        _make_xlsx(xlsx_path, {
            "Ventes": pd.DataFrame({"Pays": ["FR", "SN"], "Montant": [100, 200]}),
            "Autre":  pd.DataFrame({"x": [1]}),
        })

        result = dc.excel_to_sqlite(xlsx_path, "Ventes")

        self.assertIsNone(result["error"])
        self.assertEqual(result["row_count"], 2)
        self.assertIn("pays", result["columns"])
        self.assertIn("montant", result["columns"])

        conn = sqlite3.connect(result["sqlite_path"])
        rows = conn.execute(f'SELECT pays, montant FROM "{result["table_name"]}" ORDER BY pays').fetchall()
        conn.close()
        self.assertEqual(rows, [("FR", 100), ("SN", 200)])

    def test_missing_sheet_returns_error_not_exception(self):
        xlsx_path = self._xlsx_path()
        _make_xlsx(xlsx_path, {"Ventes": pd.DataFrame({"x": [1]})})

        result = dc.excel_to_sqlite(xlsx_path, "SheetQuiNexistePas")

        self.assertIsNotNone(result["error"])
        self.assertIsNone(result["sqlite_path"])


class ExcelSheetsTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_lists_sheet_names_in_order(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "multi.xlsx")
        _make_xlsx(xlsx_path, {
            "Janvier": pd.DataFrame({"x": [1]}),
            "Fevrier": pd.DataFrame({"x": [2]}),
        })

        self.assertEqual(dc._excel_sheets(xlsx_path), ["Janvier", "Fevrier"])


class ExcelPreviewNanTests(TestCase):
    """Une cellule vide dans les 3 premieres lignes ne doit pas casser le JSON envoye au navigateur."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_missing_value_becomes_none_not_nan(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "trous.xlsx")
        _make_xlsx(xlsx_path, {
            "Transactions": pd.DataFrame({"date": ["2024-01-01"], "montant": [float("nan")]}),
        })

        info = dc._excel_preview(xlsx_path, "Transactions")

        value = info["preview_rows"][0][1]
        self.assertIsNone(value)
        # doit rester serialisable en JSON strict (comme le fera le navigateur) :
        json.dumps(info, allow_nan=False)


class TestConnectionExcelTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_lists_sheets_as_tables_without_converting(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "raw.xlsx")
        _make_xlsx(xlsx_path, {
            "Janvier": pd.DataFrame({"Montant": [1, 2]}),
            "Fevrier": pd.DataFrame({"Montant": [3]}),
        })
        cfg = {"type": "excel", "raw_path": xlsx_path, "sqlite_path": None, "active_table": None}

        result = dc.test_connection(cfg)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["tables"], ["Janvier", "Fevrier"])
        self.assertEqual(result["active_table"], "Janvier")
        self.assertEqual(result["table_info"]["row_count"], 2)


class PrepareFromUploadExcelTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_saves_raw_file_without_converting(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "src.xlsx")
        _make_xlsx(xlsx_path, {"Ventes": pd.DataFrame({"x": [1]})})
        with open(xlsx_path, "rb") as f:
            uploaded = SimpleUploadedFile("etude.xlsx", f.read())

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            res = dc.prepare_from_upload(uploaded, "excel")

        self.assertTrue(res["ok"], res.get("error"))
        cfg = res["source_config"]
        self.assertEqual(cfg["type"], "excel")
        self.assertIsNone(cfg.get("sqlite_path"))
        self.assertIsNone(cfg.get("active_table"))
        self.assertTrue(Path(cfg["raw_path"]).exists())


class SourceConfirmExcelViewTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_converts_chosen_sheet_and_activates_source(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "src.xlsx")
        _make_xlsx(xlsx_path, {"Ventes": pd.DataFrame({"x": [1, 2, 3]})})
        cfg = {
            "type": "excel", "sqlite_path": None, "raw_path": xlsx_path,
            "original_name": "src.xlsx", "active_table": None, "label": "src.xlsx",
        }

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            resp = self.client.post(reverse("analytics:source_confirm"), {
                "source_config_json": json.dumps(cfg),
                "active_table": "Ventes",
            })

        self.assertRedirects(resp, reverse("analytics:index"))
        session_cfg = self.client.session["db_source"]
        self.assertIsNotNone(session_cfg["sqlite_path"])
        self.assertTrue(Path(session_cfg["sqlite_path"]).exists())

    def test_conversion_error_does_not_activate_source(self):
        cfg = {
            "type": "excel", "sqlite_path": None, "raw_path": "/no/such/file.xlsx",
            "original_name": "src.xlsx", "active_table": None, "label": "src.xlsx",
        }

        resp = self.client.post(reverse("analytics:source_confirm"), {
            "source_config_json": json.dumps(cfg),
            "active_table": "Ventes",
        })

        self.assertRedirects(resp, reverse("analytics:source_setup"))
        self.assertNotIn("db_source", self.client.session)


class MultiCsvConcatTests(TestCase):
    """Le client a ses transactions eclatees dans plusieurs CSV (meme structure)."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _csv_path(self, name: str) -> str:
        return str(Path(self.tmp_dir.name) / name)

    def test_concatenates_same_structure_csvs_into_one_table(self):
        jan = self._csv_path("janvier.csv")
        fev = self._csv_path("fevrier.csv")
        _make_csv(jan, pd.DataFrame({"pays": ["FR", "SN"], "montant": [100, 200]}))
        _make_csv(fev, pd.DataFrame({"pays": ["ML"], "montant": [300]}))

        result = dc.csv_to_sqlite([jan, fev])

        self.assertIsNone(result["error"])
        self.assertEqual(result["row_count"], 3)
        conn = sqlite3.connect(result["sqlite_path"])
        total = conn.execute(f'SELECT SUM(montant) FROM "{result["table_name"]}"').fetchone()[0]
        conn.close()
        self.assertEqual(total, 600)

    def test_mismatched_columns_returns_error_not_silent_merge(self):
        jan = self._csv_path("janvier.csv")
        fev = self._csv_path("fevrier.csv")
        _make_csv(jan, pd.DataFrame({"pays": ["FR"], "montant": [100]}))
        _make_csv(fev, pd.DataFrame({"pays": ["ML"], "devise": ["XOF"]}))  # colonnes differentes

        result = dc.csv_to_sqlite([jan, fev])

        self.assertIsNotNone(result["error"])
        self.assertIsNone(result["sqlite_path"])


class MultiExcelConcatTests(TestCase):
    """Le client a ses transactions eclatees dans plusieurs fichiers Excel (meme structure)."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _xlsx_path(self, name: str) -> str:
        return str(Path(self.tmp_dir.name) / name)

    def test_concatenates_same_sheet_across_files(self):
        jan = self._xlsx_path("janvier.xlsx")
        fev = self._xlsx_path("fevrier.xlsx")
        _make_xlsx(jan, {"Transactions": pd.DataFrame({"pays": ["FR"], "montant": [100]})})
        _make_xlsx(fev, {"Transactions": pd.DataFrame({"pays": ["SN"], "montant": [200]})})

        result = dc.excel_to_sqlite([jan, fev], "Transactions")

        self.assertIsNone(result["error"])
        self.assertEqual(result["row_count"], 2)

    def test_missing_sheet_in_one_file_returns_error(self):
        jan = self._xlsx_path("janvier.xlsx")
        fev = self._xlsx_path("fevrier.xlsx")
        _make_xlsx(jan, {"Transactions": pd.DataFrame({"pays": ["FR"], "montant": [100]})})
        _make_xlsx(fev, {"AutreNom": pd.DataFrame({"pays": ["SN"], "montant": [200]})})

        result = dc.excel_to_sqlite([jan, fev], "Transactions")

        self.assertIsNotNone(result["error"])
        self.assertIsNone(result["sqlite_path"])

    def test_mismatched_columns_returns_error(self):
        jan = self._xlsx_path("janvier.xlsx")
        fev = self._xlsx_path("fevrier.xlsx")
        _make_xlsx(jan, {"Transactions": pd.DataFrame({"pays": ["FR"], "montant": [100]})})
        _make_xlsx(fev, {"Transactions": pd.DataFrame({"pays": ["SN"], "devise": ["XOF"]})})

        result = dc.excel_to_sqlite([jan, fev], "Transactions")

        self.assertIsNotNone(result["error"])
        self.assertIsNone(result["sqlite_path"])


class PrepareFromUploadMultiFileTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def _uploaded_xlsx(self, name: str, df: "pd.DataFrame") -> SimpleUploadedFile:
        path = str(Path(self.tmp_dir.name) / name)
        _make_xlsx(path, {"Transactions": df})
        with open(path, "rb") as f:
            return SimpleUploadedFile(name, f.read())

    def test_stores_raw_path_as_list_for_multiple_excel_files(self):
        f1 = self._uploaded_xlsx("janvier.xlsx", pd.DataFrame({"x": [1]}))
        f2 = self._uploaded_xlsx("fevrier.xlsx", pd.DataFrame({"x": [2]}))

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            res = dc.prepare_from_upload([f1, f2], "excel")

        self.assertTrue(res["ok"], res.get("error"))
        cfg = res["source_config"]
        self.assertIsInstance(cfg["raw_path"], list)
        self.assertEqual(len(cfg["raw_path"]), 2)
        for p in cfg["raw_path"]:
            self.assertTrue(Path(p).exists())

    def test_single_file_still_stored_as_plain_string(self):
        f1 = self._uploaded_xlsx("etude.xlsx", pd.DataFrame({"x": [1]}))

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            res = dc.prepare_from_upload(f1, "excel")

        self.assertTrue(res["ok"], res.get("error"))
        self.assertIsInstance(res["source_config"]["raw_path"], str)


class TestConnectionMultiExcelTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_lists_sheets_from_first_file_as_reference(self):
        jan = str(Path(self.tmp_dir.name) / "janvier.xlsx")
        fev = str(Path(self.tmp_dir.name) / "fevrier.xlsx")
        _make_xlsx(jan, {"Transactions": pd.DataFrame({"montant": [1, 2]})})
        _make_xlsx(fev, {"Transactions": pd.DataFrame({"montant": [3]})})
        cfg = {"type": "excel", "raw_path": [jan, fev], "sqlite_path": None, "active_table": None}

        result = dc.test_connection(cfg)

        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["tables"], ["Transactions"])


class DetectSourceTypeTests(TestCase):
    """Le serveur doit deviner le vrai type depuis l'extension, pas se fier a l'onglet clique."""

    def test_detects_sqlite_csv_and_excel_extensions(self):
        self.assertEqual(dc._detect_source_type("base.db"), "sqlite")
        self.assertEqual(dc._detect_source_type("base.sqlite3"), "sqlite")
        self.assertEqual(dc._detect_source_type("export.csv"), "csv")
        self.assertEqual(dc._detect_source_type("classeur.xlsx"), "excel")
        self.assertEqual(dc._detect_source_type("vieux.xls"), "excel")

    def test_unknown_extension_returns_none(self):
        self.assertIsNone(dc._detect_source_type("notes.txt"))


class PrepareFromUploadIgnoresWrongTabTests(TestCase):
    """Meme si l'onglet SQLite est reste actif par erreur, un upload .xlsx doit marcher."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_xlsx_uploaded_under_sqlite_tab_is_still_processed_as_excel(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "etude.xlsx")
        _make_xlsx(xlsx_path, {"Transactions": pd.DataFrame({"x": [1]})})
        with open(xlsx_path, "rb") as f:
            uploaded = SimpleUploadedFile("etude.xlsx", f.read())

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            # source_type="sqlite" simule l'onglet reste bloque sur SQLite cote client
            res = dc.prepare_from_upload(uploaded, "sqlite")

        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(res["source_config"]["type"], "excel")

    def test_mixed_extensions_in_one_batch_returns_clear_error(self):
        xlsx_path = str(Path(self.tmp_dir.name) / "a.xlsx")
        csv_path = str(Path(self.tmp_dir.name) / "b.csv")
        _make_xlsx(xlsx_path, {"Transactions": pd.DataFrame({"x": [1]})})
        _make_csv(csv_path, pd.DataFrame({"x": [1]}))
        with open(xlsx_path, "rb") as f1, open(csv_path, "rb") as f2:
            files = [SimpleUploadedFile("a.xlsx", f1.read()), SimpleUploadedFile("b.csv", f2.read())]

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            res = dc.prepare_from_upload(files, "sqlite")

        self.assertFalse(res["ok"])
        self.assertIsNotNone(res["error"])


class SourceConfirmMultiExcelViewTests(TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)

    def test_converts_and_concatenates_all_files_on_confirm(self):
        jan = str(Path(self.tmp_dir.name) / "janvier.xlsx")
        fev = str(Path(self.tmp_dir.name) / "fevrier.xlsx")
        _make_xlsx(jan, {"Transactions": pd.DataFrame({"montant": [1, 2]})})
        _make_xlsx(fev, {"Transactions": pd.DataFrame({"montant": [3]})})
        cfg = {
            "type": "excel", "sqlite_path": None, "raw_path": [jan, fev],
            "original_name": "janvier.xlsx (+1 autre)", "active_table": None, "label": "janvier.xlsx (+1 autre)",
        }

        with override_settings(MEDIA_ROOT=self.tmp_dir.name):
            resp = self.client.post(reverse("analytics:source_confirm"), {
                "source_config_json": json.dumps(cfg),
                "active_table": "Transactions",
            })

        self.assertRedirects(resp, reverse("analytics:index"))
        session_cfg = self.client.session["db_source"]
        conn = sqlite3.connect(session_cfg["sqlite_path"])
        count = conn.execute(f'SELECT COUNT(*) FROM "{session_cfg["active_table"]}"').fetchone()[0]
        conn.close()
        self.assertEqual(count, 3)
