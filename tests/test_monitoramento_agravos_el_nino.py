from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from sisclima.engines.boletim_el_nino_semanal import build_boletim_semanal
from sisclima.engines.monitoramento_agravos_el_nino import (
    aggregate_agravos_el_nino,
    load_catalog,
    merge_agravos_monitorados,
)


class MonitoramentoAgravosElNinoTests(unittest.TestCase):
    def test_catalogo_carrega_blocos(self) -> None:
        cat = load_catalog()
        self.assertIn("blocos", cat)
        self.assertIn("intoxicacao_fumaca", cat["blocos"])
        self.assertIn("arboviroses", cat["blocos"])

    def test_merge_agravos_enriquece_arboviroses(self) -> None:
        base = {"arboviroses_contexto_estiagem": {"casos_arbovirus_7d_soma": 10}}
        dw = {
            "arboviroses_dw": {"dengue_7d": 5, "chikungunya_7d": 2, "fonte": "epi_sinan_agravos"},
            "janela_dias": 7,
        }
        out = merge_agravos_monitorados(base, dw)
        arbo = out["arboviroses_contexto_estiagem"]
        self.assertEqual(arbo["dengue_7d_dw"], 5)
        self.assertEqual(arbo["chikungunya_7d_dw"], 2)

    def test_aggregate_vazio_nao_quebra(self) -> None:
        agg = aggregate_agravos_el_nino(ref=date(2026, 8, 18), try_dw=False)
        self.assertEqual(agg["janela_dias"], 7)
        self.assertIn("intoxicacao_fumaca", agg)
        self.assertIn("fontes_pendentes", agg)
        self.assertGreaterEqual(len(agg["fontes_pendentes"]), 1)

    def test_internacao_conta_por_mes_quando_data_ausente(self) -> None:
        from sisclima.engines.monitoramento_agravos_el_nino import _count_internacao_hospitalar

        intern = pd.DataFrame(
            [
                {
                    "data": pd.NaT,
                    "ano_internacao": "2026",
                    "mes_internacao": "8",
                    "numero_internacoes": 2,
                    "grupo_internacao_clima": "cardiovascular",
                },
                {
                    "data": pd.NaT,
                    "ano_internacao": "2026",
                    "mes_internacao": "7",
                    "numero_internacoes": 5,
                    "grupo_internacao_clima": "resp_infeccioso",
                },
            ]
        )
        out = _count_internacao_hospitalar(intern, date(2026, 8, 18), 7)
        self.assertEqual(out["internacoes_total_7d"], 2)
        self.assertEqual(out["grupos_7d"]["cardiovascular"], 2)

    def test_internacao_defasada_usa_mes_competencia_nao_zero(self) -> None:
        from sisclima.engines.monitoramento_agravos_el_nino import _count_internacao_hospitalar

        intern = pd.DataFrame(
            [
                {
                    "data": pd.Timestamp("2026-06-15"),
                    "numero_internacoes": 100,
                    "grupo_internacao_clima": "cardiovascular",
                },
                {
                    "data": pd.Timestamp("2026-06-20"),
                    "numero_internacoes": 50,
                    "grupo_internacao_clima": "resp_infeccioso",
                },
            ]
        )
        out = _count_internacao_hospitalar(intern, date(2026, 8, 19), 7)
        self.assertIsNone(out["internacoes_total_7d"])
        self.assertEqual(out["status"], "mes_competencia")
        self.assertEqual(out["internacoes_ultimo_mes_dw"], 150)

    def test_boletim_inclui_secao_dw_quando_ha_dados(self) -> None:
        resumo = pd.DataFrame(
            [{"municipio": "Cuiabá", "nivel": "laranja", "tmax": 38.0, "pm25_ugm3": 30.0}]
        )
        dw = {
            "janela_dias": 7,
            "intoxicacao_fumaca": {
                "notificacoes_intox_total_7d": 3,
                "notificacoes_fumaca_7d": 1,
                "fonte": "epi_sinan_agravos",
                "view_dw": "VW_SINAN_INTOXICACAOEXOGENA",
            },
            "sivep_alergico_dda": {"casos_srag_7d": 12, "casos_alergico_dda_7d": None, "cid_disponivel": False},
            "arboviroses_dw": {"dengue_7d": 40, "chikungunya_7d": 5, "fonte": "epi_arboviroses_municipal"},
            "onda_calor_desidratacao": {
                "notificacoes_desidratacao_7d": 2,
                "atendimentos_calor_7d": 8,
                "obitos_desidratacao_calor_7d": 0,
            },
            "mortalidade_cardiovascular": {
                "obitos_cardiovascular_7d": 4,
                "obitos_total_sim_7d": 10,
                "fonte": "epi_sim_obitos_calor",
            },
            "fontes_pendentes": [{"titulo": "e-SUS nebulização", "status": "pendente_sql_dw", "view_dw_sugerida": "VW_ESUS"}],
        }

        bol = build_boletim_semanal(resumo, hoje=date(2026, 8, 18), try_dw=False)
        snap = bol["snapshot"]
        snap["agravos_monitorados"] = merge_agravos_monitorados(snap["agravos_monitorados"], dw)
        from sisclima.engines.boletim_el_nino_semanal import format_markdown, load_cenario_oficial, semana_iso

        md = format_markdown(load_cenario_oficial(), semana_iso(date(2026, 8, 18)), snap)
        self.assertIn("Epidemiologia DW", md)
        self.assertIn("intoxicação exógena", md.lower())
        self.assertIn("Integrações pendentes", md)


if __name__ == "__main__":
    unittest.main()
