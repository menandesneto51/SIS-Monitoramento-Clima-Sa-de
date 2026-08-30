# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.core.db import init_db, read_table, table_count
from sisclima.ingestion.historico_incremental import (
    TABLE_CLIMA,
    upsert_clima_diario,
)


class HistoricoIncrementalTests(unittest.TestCase):
    def test_upsert_clima_updates_same_key(self) -> None:
        init_db()
        base = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "data": "2026-08-01",
                    "tmax": 35.0,
                    "tmin": 22.0,
                    "utci_proxy": 36.0,
                    "umidade_media": 40.0,
                    "precipitacao_mm": 0.0,
                    "risco_cumulativo_3d": 5.0,
                    "pm25_ugm3": 10.0,
                    "fonte": "teste",
                    "atualizado_em": "2026-08-01T10:00:00",
                }
            ]
        )
        n1 = upsert_clima_diario(base)
        self.assertEqual(n1, 1)
        before = table_count(TABLE_CLIMA)

        upd = base.copy()
        upd["tmax"] = 38.5
        upd["atualizado_em"] = "2026-08-01T18:00:00"
        n2 = upsert_clima_diario(upd)
        self.assertEqual(n2, 1)
        after = table_count(TABLE_CLIMA)
        self.assertEqual(after, before)

        df = read_table(TABLE_CLIMA)
        hit = df[(df["cod_ibge"].astype(str) == "5103403") & (df["data"].astype(str).str.startswith("2026-08-01"))]
        self.assertFalse(hit.empty)
        self.assertAlmostEqual(float(hit.iloc[0]["tmax"]), 38.5, places=1)


if __name__ == "__main__":
    unittest.main()
