# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.indice_resiliencia_municipal import (
    enrich_indice_resiliencia,
    fragilidade_rede_from_irm,
)
from sisclima.engines.indicadores_compostos import enrich_indicadores_compostos
from sisclima.engines.rit_multirisco import enrich_rit_multirisco, rit_municipal


class IndiceResilienciaMunicipalTests(unittest.TestCase):
    def test_fragilidade_inverso(self) -> None:
        self.assertEqual(fragilidade_rede_from_irm(80.0), 20.0)
        self.assertEqual(fragilidade_rede_from_irm(0.0), 100.0)
        self.assertIsNone(fragilidade_rede_from_irm(None))

    def test_completude_baixa_nula_irm(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "municipio": "A",
                    "populacao": 100_000,
                    "cnes_estab_per_10k": 2.0,  # só 1/5 componentes
                }
            ]
        )
        out = enrich_indice_resiliencia(df)
        self.assertTrue(pd.isna(out.loc[0, "indice_resiliencia_municipal_0_100"]))
        self.assertLess(float(out.loc[0, "irm_completude_pct"]), 40.0)

    def test_irm_alto_com_componentes(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "municipio": "Rico",
                    "populacao": 100_000,
                    "cnes_estab_per_10k": 8.0,
                    "cnes_leitos_per_10k": 25.0,
                    "cnes_profissionais_qtd": 800,
                    "cnes_equipes_ab_qtd": 40,
                    "equipamentos_nebulizacao": 20,
                }
            ]
        )
        out = enrich_indice_resiliencia(df)
        irm = float(out.loc[0, "indice_resiliencia_municipal_0_100"])
        self.assertGreaterEqual(irm, 85.0)
        self.assertEqual(out.loc[0, "irm_faixa"], "muito_alta")

    def test_rede_domina_quando_irm_baixo(self) -> None:
        row = {
            "nivel": "verde",
            "indice_resiliencia_municipal_0_100": 10.0,
            "pm25_ugm3": None,
        }
        out = rit_municipal(row)
        self.assertEqual(out["rit_score_rede"], 90.0)
        self.assertEqual(out["rit_0_100"], 90.0)
        self.assertEqual(out["rit_dominio_dominante"], "rede")

    def test_irm_alto_nao_eleva_rit(self) -> None:
        row = {
            "nivel": "amarela",
            "indice_resiliencia_municipal_0_100": 95.0,
            "pm25_ugm3": 10.0,
        }
        out = rit_municipal(row)
        self.assertEqual(out["rit_score_rede"], 5.0)
        self.assertEqual(out["rit_0_100"], 25.0)  # térmico amarela
        self.assertEqual(out["rit_dominio_dominante"], "termico")
        self.assertNotEqual(out["rit_dominio_dominante"], "rede")

    def test_nivel_pred_inalterados_no_enrich(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "municipio": "X",
                    "nivel": "laranja",
                    "nivel_predicao_7d": "vermelha",
                    "populacao": 50_000,
                    "cnes_estab_per_10k": 4.0,
                    "cnes_leitos_per_10k": 12.0,
                    "cnes_profissionais_qtd": 200,
                    "cnes_equipes_ab_qtd": 10,
                    "equipamentos_nebulizacao": 0,
                    "focos_queimadas_7d": 5,
                    "pm25_ugm3": None,
                    "indice_pressao_saude": 80.0,
                    "esus_idade_dias": 2,
                }
            ]
        )
        out = enrich_indice_resiliencia(df)
        out = enrich_rit_multirisco(out)
        out = enrich_indicadores_compostos(out)
        self.assertEqual(out.loc[0, "nivel"], "laranja")
        self.assertEqual(out.loc[0, "nivel_predicao_7d"], "vermelha")
        self.assertIn("rit_score_rede", out.columns)
        self.assertEqual(int(out.loc[0, "gap_fumaca_nebulizacao"]), 1)
        self.assertTrue(pd.notna(out.loc[0, "indice_resiliencia_municipal_0_100"]))


if __name__ == "__main__":
    unittest.main()
