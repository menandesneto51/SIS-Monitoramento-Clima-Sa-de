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
                {"municipio": "Cuiabá", "nivel": "laranja", "tmax": 38.2, "pm25_ugm3": 32.0, "indice_prioridade_global": 80},
                {"municipio": "Várzea Grande", "nivel": "amarela", "tmax": 36.0, "pm25_ugm3": 18.0, "indice_prioridade_global": 40},
            ]
        )
        bol = build_boletim_semanal(resumo, hoje=date(2026, 8, 18))
        md = bol["markdown"]
        self.assertIn("sala de situação", md.lower())
        self.assertIn("Cuiabá", md)
        self.assertIn("Previsão climática sazonal", md)
        self.assertIn("Amazônia Legal e Mato Grosso", md)
        self.assertIn("dados reais", md.lower())
        self.assertEqual(bol["snapshot"]["n_laranja"], 1)
        self.assertTrue(str(bol["arquivo"]).endswith(".md"))
        self.assertIn("Pauta sugerida da sala", md)

    def test_markdown_publico_omite_pauta_interna(self) -> None:
        resumo = pd.DataFrame(
            [
                {"municipio": "Cuiabá", "nivel": "laranja", "tmax": 38.2, "pm25_ugm3": 32.0, "indice_prioridade_global": 80},
            ]
        )
        md = build_boletim_semanal(resumo, hoje=date(2026, 8, 18), publico=True)["markdown"]
        self.assertNotIn("Pauta sugerida da sala", md)
        self.assertIn("Municípios em destaque", md)


if __name__ == "__main__":
    unittest.main()
