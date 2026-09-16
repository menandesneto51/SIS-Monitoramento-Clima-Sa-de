# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

import pandas as pd

from sisclima.engines.rit_multirisco import (
    enrich_rit_multirisco,
    rit_municipal,
    score_dominio_ar,
    score_dominio_pressao,
)


class RitMultiriscoTests(unittest.TestCase):
    def test_so_termico(self) -> None:
        out = rit_municipal({"nivel": "laranja", "pm25_ugm3": None})
        self.assertEqual(out["rit_0_100"], 50.0)
        self.assertEqual(out["rit_dominio_dominante"], "termico")
        self.assertEqual(out["rit_faixa"], "laranja")
        self.assertIsNone(out["rit_score_ar"])

    def test_termico_mais_pm_usa_max(self) -> None:
        out = rit_municipal({"nivel": "amarela", "pm25_ugm3": 80.0})
        self.assertEqual(out["rit_score_termico"], 25.0)
        self.assertEqual(out["rit_score_ar"], 100.0)
        self.assertEqual(out["rit_0_100"], 100.0)
        self.assertEqual(out["rit_dominio_dominante"], "ar")
        self.assertEqual(out["rit_faixa"], "roxa")

    def test_pm25_limiares(self) -> None:
        self.assertEqual(score_dominio_ar({"pm25_ugm3": 24.9}), 0.0)
        self.assertEqual(score_dominio_ar({"pm25_ugm3": 25.0}), 50.0)
        self.assertEqual(score_dominio_ar({"pm25_ugm3": 50.0}), 75.0)
        self.assertEqual(score_dominio_ar({"pm25_ugm3": 75.0}), 100.0)

    def test_aps_defasada_nao_eleva(self) -> None:
        row = {
            "nivel": "verde",
            "indice_pressao_saude": 95.0,
            "esus_idade_dias": 35,
        }
        out = rit_municipal(row, ref_hoje=pd.Timestamp("2026-09-11"))
        self.assertTrue(out["rit_pressao_omitida_defasagem"])
        self.assertIsNone(out["rit_score_pressao"])
        self.assertEqual(out["rit_0_100"], 0.0)
        self.assertEqual(out["rit_dominio_dominante"], "termico")

    def test_pressao_fresca_pode_dominar(self) -> None:
        row = {
            "nivel": "amarela",
            "indice_pressao_saude": 90.0,
            "esus_idade_dias": 3,
        }
        out = rit_municipal(row)
        self.assertFalse(out["rit_pressao_omitida_defasagem"])
        self.assertEqual(out["rit_0_100"], 90.0)
        self.assertEqual(out["rit_dominio_dominante"], "pressao")

    def test_ehf_e_hidro(self) -> None:
        out = rit_municipal(
            {
                "nivel": "amarela",
                "ehf_adaptado": 2.5,
                "nivel_alerta_hidro": "laranja",
            }
        )
        self.assertEqual(out["rit_score_ehf"], 85.0)
        self.assertEqual(out["rit_score_hidro"], 50.0)
        self.assertEqual(out["rit_0_100"], 85.0)
        self.assertEqual(out["rit_dominio_dominante"], "ehf")

    def test_enrich_colunas(self) -> None:
        df = pd.DataFrame(
            [
                {"municipio": "A", "nivel": "roxa", "pm25_ugm3": 10.0},
                {"municipio": "B", "nivel": "verde", "pm25_ugm3": 60.0},
            ]
        )
        out = enrich_rit_multirisco(df)
        self.assertIn("rit_0_100", out.columns)
        self.assertEqual(float(out.loc[0, "rit_0_100"]), 100.0)
        self.assertEqual(float(out.loc[1, "rit_0_100"]), 75.0)
        self.assertEqual(out.loc[1, "rit_dominio_dominante"], "ar")

    def test_score_pressao_tuple(self) -> None:
        s, omit = score_dominio_pressao(
            {"indice_pressao_saude": 40.0, "esus_idade_dias": 20},
            max_idade_dias=14,
        )
        self.assertIsNone(s)
        self.assertTrue(omit)

    def test_scorecard_ehf_roxo_ar_verde(self) -> None:
        from sisclima.engines.rit_multirisco import scorecard_rit

        sc = scorecard_rit(
            {
                "nivel": "amarela",
                "pm25_ugm3": 10.0,
                "ehf_adaptado": 3.0,
            }
        )
        self.assertTrue(sc["disponivel"])
        self.assertEqual(sc["dominio_dominante"], "ehf")
        self.assertEqual(sc["rit_faixa"], "roxa")
        by_id = {d["id"]: d for d in sc["dominios"]}
        self.assertEqual(by_id["ehf"]["faixa"], "roxa")
        self.assertEqual(by_id["ar"]["faixa"], "verde")
        self.assertIn("EHF", sc["explicacao_dominante"])
        self.assertNotIn("demais", sc["explicacao_dominante"])
        self.assertIn("Ar/PM2,5", sc["radar_compacto"])

    def test_scorecard_pressao_omitida(self) -> None:
        from sisclima.engines.rit_multirisco import scorecard_rit

        sc = scorecard_rit(
            {
                "nivel": "verde",
                "indice_pressao_saude": 99.0,
                "esus_idade_dias": 40,
            }
        )
        by_id = {d["id"]: d for d in sc["dominios"]}
        self.assertEqual(by_id["pressao"]["status"], "omitido_defasagem")
        self.assertNotEqual(sc["dominio_dominante"], "pressao")
        self.assertIn("rede", by_id)
        self.assertEqual(by_id["rede"]["status"], "indisponivel")

    def test_rede_omitida_sem_irm(self) -> None:
        out = rit_municipal({"nivel": "verde"})
        self.assertIsNone(out["rit_score_rede"])
        self.assertEqual(out["rit_dominio_dominante"], "termico")


if __name__ == "__main__":
    unittest.main()
