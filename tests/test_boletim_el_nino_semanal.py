from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from sisclima.engines.boletim_el_nino.snapshot import snapshot_operacional
from sisclima.engines.boletim_el_nino_semanal import build_boletim_semanal, semana_iso


class BoletimElNinoSemanalTests(unittest.TestCase):
    def test_semana_sinan_calendario_oficial_2026(self) -> None:
        """Calendário SINAN 2026: SE 34 = 23–29/08; SE 35 = 30/08–05/09."""
        se33 = semana_iso(date(2026, 8, 18))
        self.assertEqual(se33["semana"], 33)
        self.assertEqual(se33["inicio"], "2026-08-16")
        self.assertEqual(se33["fim"], "2026-08-22")

        se34 = semana_iso(date(2026, 8, 24))
        self.assertEqual(se34["semana"], 34)
        self.assertEqual(se34["rotulo"], "SE 34/2026")
        self.assertEqual(se34["inicio"], "2026-08-23")
        self.assertEqual(se34["fim"], "2026-08-29")

        se35 = semana_iso(date(2026, 8, 30))
        self.assertEqual(se35["semana"], 35)
        self.assertEqual(se35["inicio"], "2026-08-30")
        self.assertEqual(se35["fim"], "2026-09-05")

        se1 = semana_iso(date(2026, 1, 4))
        self.assertEqual(se1["semana"], 1)
        self.assertEqual(se1["inicio"], "2026-01-04")

    def test_markdown_inclui_cenario_e_nowcast(self) -> None:
        resumo = pd.DataFrame(
            [
                {
                    "municipio": "Cuiabá",
                    "nivel": "laranja",
                    "nivel_predicao_7d": "vermelha",
                    "tmax": 38.2,
                    "pm25_ugm3": 32.0,
                    "indice_prioridade_global": 80,
                },
                {
                    "municipio": "Várzea Grande",
                    "nivel": "amarela",
                    "nivel_predicao_7d": "amarela",
                    "tmax": 36.0,
                    "pm25_ugm3": 18.0,
                    "indice_prioridade_global": 40,
                },
            ]
        )
        bol = build_boletim_semanal(resumo, hoje=date(2026, 8, 18), try_dw=False)
        md = bol["markdown"]
        self.assertIn("Sala de Situação", md)
        self.assertIn("Cuiabá", md)
        self.assertIn("Municípios no extremo de atenção", md)
        self.assertIn("mínimo", md)
        self.assertIn("máximo", md)
        self.assertIn("Cenário sazonal", md)
        self.assertIn("Amazônia Legal e Mato Grosso", md)
        self.assertIn("Situação atual", md)
        self.assertIn("Notas metodológicas", md)
        self.assertIn("Impactos potenciais", md)
        self.assertEqual(bol["snapshot"]["n_laranja"], 1)
        self.assertTrue(str(bol["arquivo"]).endswith(".md"))
        self.assertIn("15. Encaminhamentos", md)
        self.assertIn("Conclusão e tendência", md)
        self.assertIn("Alertas meteorológicos e ambientais", md)
        self.assertIn("13. Preparação assistencial e farmacêutica — estoques estratégicos", md)
        self.assertNotIn("### 13.1 Estoques", md)
        self.assertIn("11. Priorização territorial", md)
        self.assertIn("### 11.4", md)
        self.assertIn("### 11.5", md)
        self.assertIn("verde 0", md.lower())
        self.assertIn("P90 APS (km)", md)
        self.assertIn("Não há municípios com melhora projetada nesta rodada.", md)
        self.assertNotIn("UTCI) proxy", md)
        self.assertNotIn("ROUTE_", md)
        self.assertNotIn("Mato Grosso do Sul (MS)", md)
        self.assertNotIn("notas técnicas MS/SES", md)
        self.assertNotIn("limite institucional", md)
        self.assertNotIn("estabilidade (sem previsão", md)
        self.assertNotIn("RISCO_TÉRMICO_PROJETADO", md)
        self.assertIn("**Tabela 1 –", md)
        self.assertIn("Fonte:", md)
        self.assertIn("µg/m³", md)
        self.assertIn("Verde —", md)

    def test_markdown_publico_omite_pauta_interna(self) -> None:
        resumo = pd.DataFrame(
            [
                {"municipio": "Cuiabá", "nivel": "laranja", "tmax": 38.2, "pm25_ugm3": 32.0, "indice_prioridade_global": 80},
            ]
        )
        md = build_boletim_semanal(resumo, hoje=date(2026, 8, 18), try_dw=False, publico=True)["markdown"]
        self.assertNotIn("Evidência transversal desta rodada", md)
        self.assertIn("Municípios prioritários para acompanhamento", md)

    def test_recorte_vazio_nao_mostra_zero_municipios(self) -> None:
        bol = build_boletim_semanal(pd.DataFrame(), hoje=date(2026, 8, 18), try_dw=False)
        md = bol["markdown"]
        self.assertIn("Dado indisponível nesta rodada", md)
        self.assertNotIn("Municípios no recorte: **0**", md)
        self.assertIsNone(bol["snapshot"]["n_municipios"])

    def test_snapshot_reporta_min_max_e_cauda(self) -> None:
        resumo = pd.DataFrame(
            {
                "municipio": ["A", "B", "C"],
                "nivel": ["verde", "laranja", "vermelha"],
                "tmax": [30.0, 32.0, 38.5],
                "umidade_media": [60.0, 50.0, 25.0],
                "pm25_ugm3": [8.0, 12.0, 40.0],
                "utci_proxy": [28.0, 31.0, 34.0],
            }
        )
        snap = snapshot_operacional(resumo)
        self.assertEqual(snap["tmax_min"], 30.0)
        self.assertEqual(snap["tmax_max"], 38.5)
        self.assertEqual(snap["n_tmax_37"], 1)
        self.assertEqual(snap["n_umidade_30"], 1)
        self.assertEqual(snap["n_pm25_25"], 1)
        self.assertEqual(snap["n_utci_32"], 1)
        self.assertEqual(snap["pm25_max"], 40.0)

    def test_hydro_facts_separa_seca_e_inundacao(self) -> None:
        resumo = pd.DataFrame(
            {
                "municipio": ["A", "B", "C", "D"],
                "nivel": ["amarela"] * 4,
                "situacao_hidro": ["seca_baixa"] * 2 + ["inundacao_alta", "normal"],
            }
        )
        snap = snapshot_operacional(resumo)
        hf = snap["hydro_facts"]
        self.assertEqual(hf["low_availability"], 2)
        self.assertEqual(hf["flood_risk_high"], 1)
        self.assertEqual(hf["habitual"], 1)
        self.assertEqual(hf["coverage"], 4)
        self.assertEqual(hf["low_availability"] + hf["flood_risk_high"] + hf["habitual"], hf["coverage"])
        agr = snap.get("agravos_monitorados") or snap.get("agravos_monitorados") or {}
        self.assertEqual((agr.get("hidrorelacionados") or {}).get("municipios_hidro_alerta"), 2)

    def test_hydro_facts_8_1_1(self) -> None:
        resumo = pd.DataFrame(
            {
                "municipio": [f"M{i}" for i in range(10)],
                "nivel": ["amarela"] * 10,
                "situacao_hidro": ["seca_baixa"] * 8 + ["inundacao_alta", "normal"],
            }
        )
        hf = snapshot_operacional(resumo)["hydro_facts"]
        self.assertEqual(hf["low_availability"], 8)
        self.assertEqual(hf["flood_risk_high"], 1)
        self.assertEqual(hf["habitual"], 1)
        self.assertEqual(hf["coverage"], 10)
        self.assertEqual(hf["low_availability"] + hf["flood_risk_high"] + hf["habitual"], hf["coverage"])

    def test_focos_nao_confunde_cobertura_com_deteccao(self) -> None:
        resumo = pd.DataFrame(
            {
                "municipio": ["A", "B", "C", "D", "E"],
                "nivel": ["amarela"] * 5,
                "focos_queimadas_7d": [10, 3, 5, None, None],
            }
        )
        snap = snapshot_operacional(resumo)
        ff = snap["fire_facts"]
        self.assertTrue(ff["coverage_is_detection"])
        self.assertEqual(ff["coverage"], 3)
        self.assertEqual(ff["detected"], 3)
        from sisclima.engines.boletim_el_nino.interpretacao import interpretar_fogo

        txt = interpretar_fogo(snap)
        self.assertIn("Foram detectados", txt)
        self.assertIn("focos de calor em", txt)
        self.assertIn("municípios", txt)
        self.assertNotIn("Cobertura da fonte:", txt)
        self.assertNotIn("Municípios com registro na base integrada", txt)
        self.assertNotIn("totalizando", txt)

    def test_conclusao_sem_melhora_e_saturacao(self) -> None:
        from sisclima.engines.boletim_el_nino.governanca import conclusao_tendencia

        snap = {
            "disponivel": True,
            "n_municipios": 10,
            "n_vermelha_roxa": 10,
            "delta_projecao": {"melhora": 0, "estabilidade": 2, "aumento_1": 5, "aumento_2plus": 3},
            "delta_n_comparavel": 10,
            "niveis_projecao_7d": {"vermelha": 2, "roxa": 8},
            "model_qa": {"MODEL_SATURATION_WARNING": True},
            "regionais": [{"regional": "Cuiabá"}],
        }
        txt = conclusao_tendencia(snap, {}, {"n_inmet_vigentes": 1})
        self.assertIn("Não há municípios com melhora projetada nesta rodada.", txt)
        self.assertNotIn("0 municípios apresentam melhora", txt)
        self.assertIn("persistência térmica e onda de calor", txt)

    def test_pareamento_e_hidro_redacao(self) -> None:
        from sisclima.engines.boletim_el_nino.formatters import fmt_pareamento
        from sisclima.engines.boletim_el_nino.interpretacao import interpretar_hidrologia
        from sisclima.engines.boletim_el_nino.governanca import conclusao_tendencia

        self.assertEqual(fmt_pareamento(1, 142), "1 de 142 municípios (0,7%).")
        snap = {
            "n_municipios": 142,
            "cobertura_hidro": 10,
            "hydro_facts": {"low_availability": 8, "flood_risk_high": 1, "habitual": 1, "coverage": 10},
            "solo_mediana": 14,
        }
        hidro = interpretar_hidrologia(snap)
        self.assertNotIn("ver tabela abaixo", hidro)
        self.assertIn("situação hidrológica habitual", hidro)
        self.assertIn("8 municípios apresentam sinal de baixa disponibilidade hídrica", hidro)
        conc = conclusao_tendencia(
            {
                "disponivel": True,
                "n_municipios": 142,
                "n_vermelha_roxa": 84,
                "delta_projecao": {"melhora": 0, "estabilidade": 37, "aumento_1": 50, "aumento_2plus": 54},
                "delta_n_comparavel": 141,
                "delta_sem_pareamento": 1,
                "niveis_projecao_7d": {"vermelha": 6, "roxa": 136},
                "regionais": [{"regional": "Sinop"}],
            },
            {},
            {},
        )
        self.assertIn("1 de 142 municípios (0,7%).", conc)
        self.assertNotIn("1 município (1 de 142", conc)


if __name__ == "__main__":
    unittest.main()
