# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.ehf_geocalor import compute_ehf_geocalor, eventos_from_daily


def _serie(n: int = 200, base: float = 28.0, spike_start: int = 180, spike_days: int = 6, spike: float = 42.0):
    dates = pd.date_range("2023-01-01", periods=n, freq="D")
    rows = []
    for i, d in enumerate(dates):
        t = spike if spike_start <= i < spike_start + spike_days else base
        rows.append(
            {
                "cod_ibge": "5103403",
                "municipio": "Cuiabá",
                "data": d.strftime("%Y-%m-%d"),
                "tmax": t + 2,
                "tmin": t - 2,
                "tmedia": t,
                "fonte": "teste",
            }
        )
    return pd.DataFrame(rows)


class EhfGeocalorTests(unittest.TestCase):
    def test_evento_minimo_3_dias(self) -> None:
        df = _serie(spike_days=0, spike=28.0)
        daily = compute_ehf_geocalor(df)
        eventos = eventos_from_daily(daily)
        self.assertTrue(eventos.empty)

    def test_detecta_onda_6_dias(self) -> None:
        df = _serie(n=200, spike_start=180, spike_days=8, spike=45.0)
        daily = compute_ehf_geocalor(df)
        eventos = eventos_from_daily(daily)
        self.assertGreaterEqual(len(eventos), 1)
        self.assertGreaterEqual(int(eventos["duracao_dias"].max()), 3)
        self.assertEqual(eventos.iloc[0]["metodologia"], "GeoCalor_EHF_NairnFawcett_3d")
        hw = pd.to_numeric(daily["is_hw_day"], errors="coerce").fillna(0)
        self.assertGreaterEqual(int(hw.sum()), 3)

    def test_p95_local_por_municipio(self) -> None:
        a = _serie(n=200, base=20, spike_start=180, spike_days=8, spike=35)
        b = a.copy()
        b["cod_ibge"] = "5108402"
        b["municipio"] = "Várzea Grande"
        daily = compute_ehf_geocalor(pd.concat([a, b], ignore_index=True))
        self.assertEqual(daily["cod_ibge"].nunique(), 2)
        self.assertIn("ehf", daily.columns)
        self.assertIn("ehi_sig", daily.columns)


if __name__ == "__main__":
    unittest.main()
