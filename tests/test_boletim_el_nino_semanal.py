from __future__ import annotations

import unittest
from datetime import date

import pandas as pd

from sisclima.engines.boletim_el_nino_semanal import build_boletim_semanal, semana_iso


class BoletimElNinoSemanalTests(unittest.TestCase):
    def test_semana_iso_rotulo(self) -> None:
        info = semana_iso(date(2026, 8, 18))
        self.assertEqual(info["semana"], 34)
        self.assertIn("SE 34/2026", info["rotulo"])

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
        self.assertIn("Cenário sazonal", md)
        self.assertIn("Amazônia Legal e Mato Grosso", md)
        self.assertIn("Situação atual", md)
        self.assertIn("Medidor de trajetória", md)
        self.assertIn("Impactos potenciais", md)
        self.assertEqual(bol["snapshot"]["n_laranja"], 1)
        self.assertTrue(str(bol["arquivo"]).endswith(".md"))
        self.assertIn("Encaminhamentos recomendados", md)
        self.assertIn("Conclusão e tendência", md)
        self.assertIn("Alertas meteorológicos e integração TITAN", md)
        self.assertIn("Estoques estratégicos SES", md)
        self.assertIn("Referências", md)

    def test_markdown_publico_omite_pauta_interna(self) -> None:
        resumo = pd.DataFrame(
            [
                {"municipio": "Cuiabá", "nivel": "laranja", "tmax": 38.2, "pm25_ugm3": 32.0, "indice_prioridade_global": 80},
            ]
        )
        md = build_boletim_semanal(resumo, hoje=date(2026, 8, 18), try_dw=False, publico=True)["markdown"]
        self.assertNotIn("Encaminhamentos recomendados", md)
        self.assertIn("Municípios prioritários para acompanhamento", md)

    def test_recorte_vazio_nao_mostra_zero_municipios(self) -> None:
        bol = build_boletim_semanal(pd.DataFrame(), hoje=date(2026, 8, 18), try_dw=False)
        md = bol["markdown"]
        self.assertIn("Dado indisponível nesta rodada", md)
        self.assertNotIn("Municípios no recorte: **0**", md)
        self.assertIsNone(bol["snapshot"]["n_municipios"])


if __name__ == "__main__":
    unittest.main()
