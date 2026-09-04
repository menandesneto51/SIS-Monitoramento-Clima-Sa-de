# -*- coding: utf-8 -*-
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class RodadaSemanalTests(unittest.TestCase):
    def test_build_rodada_exporta_classe_atual_e_projetada(self) -> None:
        from sisclima.reporting.rodada_semanal import build_rodada_semanal

        df = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "regional_saude": "Baixada Cuiabana",
                    "nivel": "roxa",
                    "pred_nivel_clima_7d": "roxa",
                    "tmax": 41.5,
                    "umidade_media": 11.0,
                    "pm25_ugm3": 88.4,
                    "utci_proxy": 43.2,
                    "focos_queimadas_7d": 142,
                    "indice_prioridade_global": 92.0,
                    "faixa_prioridade_global": "critica",
                    "risco_predominante": "Onda de calor",
                },
                {
                    "cod_ibge": "5107925",
                    "municipio": "Sorriso",
                    "regional_saude": "Sinop",
                    "nivel": "vermelha",
                    "pred_nivel_clima_7d": "roxa",
                    "tmax": 38.0,
                    "umidade_media": 18.0,
                    "pm25_ugm3": 40.0,
                    "utci_proxy": 39.0,
                    "focos_queimadas_7d": 20,
                    "indice_prioridade_global": 70.0,
                    "faixa_prioridade_global": "alta",
                    "risco_predominante": "Fumaça",
                },
            ]
        )
        out = build_rodada_semanal(df, ref=date(2026, 8, 23))
        self.assertEqual(len(out), 2)
        self.assertEqual(out.loc[out["cod_ibge"] == "5103403", "classe_atual"].iloc[0], "roxa")
        self.assertEqual(out.loc[out["cod_ibge"] == "5107925", "classe_projetada_7d"].iloc[0], "roxa")
        self.assertIn("SE ", out["semana_epidemiologica"].iloc[0])

    def test_validacao_projecao_x_observado(self) -> None:
        from sisclima.reporting.rodada_semanal import build_validacao_modelo

        proj = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "regional_saude": "Baixada Cuiabana",
                    "semana_epidemiologica": "SE 34/2026",
                    "classe_projetada_7d": "roxa",
                },
                {
                    "cod_ibge": "5107925",
                    "municipio": "Sorriso",
                    "regional_saude": "Sinop",
                    "semana_epidemiologica": "SE 34/2026",
                    "classe_projetada_7d": "vermelha",
                },
            ]
        )
        obs = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "semana_epidemiologica": "SE 35/2026",
                    "classe_atual": "roxa",
                },
                {
                    "cod_ibge": "5107925",
                    "semana_epidemiologica": "SE 35/2026",
                    "classe_atual": "roxa",
                },
            ]
        )
        v = build_validacao_modelo(proj, obs)
        self.assertEqual(len(v), 2)
        cuiaba = v.loc[v["cod_ibge"] == "5103403"].iloc[0]
        sorriso = v.loc[v["cod_ibge"] == "5107925"].iloc[0]
        self.assertTrue(bool(cuiaba["acertou"]))
        self.assertFalse(bool(sorriso["acertou"]))
        self.assertEqual(int(sorriso["diferenca_niveis"]), 1)

    def test_export_escreve_csv(self) -> None:
        from sisclima.reporting.rodada_semanal import export_rodada_semanal

        df = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "regional_saude": "Baixada Cuiabana",
                    "nivel": "laranja",
                    "pred_nivel_clima_7d": "vermelha",
                    "tmax": 37.0,
                    "umidade_media": 20.0,
                    "pm25_ugm3": 30.0,
                    "utci_proxy": 35.0,
                    "focos_queimadas_7d": 1,
                    "indice_prioridade_global": 50.0,
                    "faixa_prioridade_global": "moderada",
                }
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "sisclima.reporting.rodada_semanal.persist_rodada_hist",
                return_value=0,
            ):
                meta = export_rodada_semanal(
                    resumo=df,
                    ref=date(2026, 8, 23),
                    out_dir=Path(tmp),
                    persist_hist=True,
                )
            self.assertEqual(meta["n_municipios"], 1)
            path = Path(meta["path_municipal"])
            self.assertTrue(path.exists())
            loaded = pd.read_csv(path)
            self.assertEqual(loaded.iloc[0]["classe_atual"], "laranja")


if __name__ == "__main__":
    unittest.main()
