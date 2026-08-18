from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from sisclima.ingestion.openmeteo import _as_locations, _daily_from_payload


class OpenMeteoParseTests(unittest.TestCase):
    def test_as_locations_aceita_objeto_ou_lista(self) -> None:
        self.assertEqual(len(_as_locations({"daily": {}})), 1)
        self.assertEqual(len(_as_locations([{"daily": {}}, {"daily": {}}])), 2)
        self.assertEqual(_as_locations(None), [])

    def test_daily_from_payload(self) -> None:
        js = {
            "daily": {
                "time": ["2026-08-18"],
                "temperature_2m_max": [38.1],
                "temperature_2m_min": [24.0],
                "relative_humidity_2m_mean": [40],
                "wind_speed_10m_max": [12],
                "precipitation_sum": [0],
                "precipitation_hours": [0],
            }
        }
        df = _daily_from_payload(js, "Cuiabá", "5103403", -15.6, -56.1)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["municipio"], "Cuiabá")
        self.assertAlmostEqual(float(df.iloc[0]["tmax"]), 38.1)


class HttpRetryTests(unittest.TestCase):
    def test_repete_503_e_devolve_200(self) -> None:
        from sisclima.core import http_client as hc

        bad = Mock()
        bad.status_code = 503
        bad.headers = {}
        good = Mock()
        good.status_code = 200
        good.headers = {}
        with patch.object(hc.requests, "get", side_effect=[bad, good]) as get:
            with patch.object(hc.time, "sleep"):
                out = hc.http_get("https://example.test", retries=2)
        self.assertEqual(out.status_code, 200)
        self.assertEqual(get.call_count, 2)


class SivepKeepTests(unittest.TestCase):
    def test_pasta_vazia_nao_apaga_banco(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        drop = root / "drop"
        drop.mkdir()
        db = root / "sivep.db"
        with sqlite3.connect(db) as conn:
            pd.DataFrame([{"cod_ibge": "5103403", "casos_srag": 3}]).to_sql(
                "sivep_srag", conn, index=False
            )
        os.environ["SIVEP_UPDATE_FOLDER"] = str(drop)
        os.environ["SIVEP_LOCAL_DB_PATH"] = str(db)
        os.environ["SIVEP_USE_UNIFIED_DB"] = "false"
        os.environ["SIVEP_LOCAL_TABLE"] = "sivep_srag"
        from sisclima.ingestion import sivep_local as sl

        with patch.object(sl, "_use_unified_db", return_value=False):
            info = sl.rebuild_sivep_local_db()
        self.assertEqual(info.get("status"), "kept")
        self.assertEqual(info.get("rows"), 1)
        with sqlite3.connect(db) as conn:
            n = int(pd.read_sql("SELECT COUNT(*) AS n FROM sivep_srag", conn)["n"].iloc[0])
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
