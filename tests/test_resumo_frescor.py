# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.resumo_frescor import refresh_resumo_multirisco


class ResumoFrescorTests(unittest.TestCase):
    def test_ordem_produz_irm_rit_compostos(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "municipio": "A",
                    "nivel": "verde",
                    "nivel_predicao_7d": "amarela",
                    "populacao": 80_000,
                    "cnes_estab_per_10k": 1.0,
                    "cnes_leitos_per_10k": 5.0,
                    "cnes_profissionais_qtd": 100,
                    "cnes_equipes_ab_qtd": 5,
                    "equipamentos_nebulizacao": 0,
                    "focos_queimadas_7d": 3,
                    "pm25_ugm3": None,
                }
            ]
        )
        out = refresh_resumo_multirisco(df, inject_ehf=False, merge_predicao=False, persist=False)
        self.assertEqual(out.loc[0, "nivel"], "verde")
        self.assertEqual(out.loc[0, "nivel_predicao_7d"], "amarela")
        self.assertIn("indice_resiliencia_municipal_0_100", out.columns)
        self.assertIn("rit_score_rede", out.columns)
        self.assertIn("gap_fumaca_nebulizacao", out.columns)
        self.assertTrue(pd.notna(out.loc[0, "rit_0_100"]))
        meta = out.attrs.get("multirisco_frescor") or {}
        self.assertIn("irm", meta.get("steps", []))
        self.assertIn("rit", meta.get("steps", []))
        self.assertIn("compostos", meta.get("steps", []))


if __name__ == "__main__":
    unittest.main()
