# -*- coding: utf-8 -*-
"""Smoke tests KPIs Prioridade 1."""
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.kpis_p1_sala import (
    compute_fumaca_kpi,
    compute_heat_days_ytd,
    compute_spi_proxy,
    enrich_exposicao_fumaca,
    resumo_kpis_p1_boletim,
)


class TestKpisP1Sala(unittest.TestCase):
    def test_enrich_fumaca_score(self):
        df = pd.DataFrame(
            {
                "cod_ibge": ["5103403", "5107925"],
                "pm25_ugm3": [50.0, 5.0],
                "focos_queimadas_7d": [10, 0],
                "equipamentos_nebulizacao": [0, 2],
            }
        )
        out = enrich_exposicao_fumaca(df)
        self.assertIn("exposicao_fumaca_0_100", out.columns)
        self.assertGreater(float(out.loc[0, "exposicao_fumaca_0_100"]), float(out.loc[1, "exposicao_fumaca_0_100"]))

    def test_spi_and_heat_run(self):
        spi = compute_spi_proxy(dias=30)
        heat = compute_heat_days_ytd()
        # Pode ser ok=False se DB de teste vazio; não deve lançar
        self.assertIn("ok", spi)
        self.assertIn("ok", heat)
        self.assertIn("kpi", spi)
        self.assertIn("kpi", heat)

    def test_resumo_markdown(self):
        pack = resumo_kpis_p1_boletim(pd.DataFrame({"cod_ibge": ["5103403"], "pm25_ugm3": [30.0]}))
        self.assertIn("markdown", pack)
        self.assertTrue(isinstance(pack["markdown"], str))


if __name__ == "__main__":
    unittest.main()
