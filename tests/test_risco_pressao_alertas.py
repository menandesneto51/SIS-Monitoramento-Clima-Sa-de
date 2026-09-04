# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import pandas as pd


class QuadroRiscoPressaoTests(unittest.TestCase):
    def test_quadro_lista_risco_e_pressao(self) -> None:
        from sisclima.reporting.quadro_risco_pressao import quadro_risco_pressao

        df = pd.DataFrame(
            [
                {
                    "cod_ibge": "5107925",
                    "municipio": "Sorriso",
                    "regional_saude": "Sinop",
                    "nivel": "laranja",
                    "indice_pressao_saude": 72.4,
                    "semaforo_pressao": "vermelha",
                    "ocupacao_leitos_pct": 81.0,
                    "pressao_calor_pct": 6.2,
                },
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "regional_saude": "Cuiabá",
                    "nivel": "amarela",
                    "indice_pressao_saude": 41.0,
                    "semaforo_pressao": "amarela",
                    "ocupacao_leitos_pct": 70.0,
                    "pressao_calor_pct": 3.1,
                },
            ]
        )
        with patch(
            "sisclima.reporting.quadro_risco_pressao._leitos_por_ibge",
            return_value={},
        ):
            quadro = quadro_risco_pressao(df)
        self.assertTrue(quadro["disponivel"])
        self.assertEqual(quadro["dist_nivel"]["laranja"], 1)
        self.assertEqual(quadro["registros"][0]["municipio"], "Sorriso")
        self.assertEqual(quadro["pressao_max"], 72.4)
        self.assertEqual(quadro["calor_max"], 6.2)
        regs = {r["regional"]: r for r in quadro.get("ocupacao_por_regional") or []}
        self.assertIn("Sinop", regs)
        self.assertEqual(regs["Sinop"]["n_municipios"], 1)
        self.assertAlmostEqual(regs["Sinop"]["ocupacao_ponderada"], 81.0, places=1)

    def test_ocupacao_por_regional_sem_leitos_nao_inventa_pct(self) -> None:
        from sisclima.reporting.quadro_risco_pressao import agregar_ocupacao_por_regional

        df = pd.DataFrame(
            [
                {
                    "cod_ibge": "5100102",
                    "municipio": "Acorizal",
                    "regional_saude": "Baixada Cuiabana",
                    "ocupacao_leitos_pct": pd.NA,
                    "fonte_ocupacao": "SEM_LEITOS_INDICASUS",
                },
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "regional_saude": "Baixada Cuiabana",
                    "ocupacao_leitos_pct": 60.0,
                    "fonte_ocupacao": "INDICASUS_TEMPO_REAL",
                },
            ]
        )
        with patch(
            "sisclima.reporting.quadro_risco_pressao._leitos_por_ibge",
            return_value={},
        ):
            rows = agregar_ocupacao_por_regional(df)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["n_sem_leitos"], 1)
        self.assertEqual(rows[0]["n_com_taxa"], 1)
        self.assertAlmostEqual(rows[0]["ocupacao_ponderada"], 60.0, places=1)

    def test_quadro_vazio_nao_inventa_zero(self) -> None:
        from sisclima.reporting.quadro_risco_pressao import quadro_risco_pressao

        quadro = quadro_risco_pressao(pd.DataFrame())
        self.assertFalse(quadro["disponivel"])
        self.assertIn("ausente", str(quadro.get("motivo") or "").lower())


class ForceMunicipioAlertTests(unittest.TestCase):
    def test_force_inclui_sorriso_abaixo_do_minimo(self) -> None:
        from sisclima.alerts.digest import _select_payloads

        payloads = [
            {"escopo": "estadual", "alvo_id": "MT", "nivel": "laranja"},
            {"escopo": "municipal", "alvo_id": "5103403", "nivel": "vermelha", "score": 3},
            {"escopo": "municipal", "alvo_id": "5107925", "nivel": "verde", "score": 0},
        ]
        with patch.dict(
            os.environ,
            {
                "ALERT_LAYERS": "ses,municipais",
                "ALERT_MAX_MUNICIPIOS": "1",
                "ALERT_MIN_LEVEL_MUNICIPAL": "laranja",
                "ALERT_FORCE_MUNICIPIOS": "5107925",
                "ALERT_SEND_ALL_MUNICIPIOS": "false",
            },
            clear=False,
        ):
            selected = _select_payloads(payloads)
        ids = {str(p.get("alvo_id")) for p in selected if p.get("escopo") == "municipal"}
        self.assertIn("5107925", ids)
        self.assertIn("5103403", ids)

    def test_build_municipal_inclui_force_cinza(self) -> None:
        from sisclima.engines.alertas_multinivel import build_alertas_multinivel

        df = pd.DataFrame(
            [
                {
                    "cod_ibge": "5103403",
                    "municipio": "Cuiabá",
                    "regional_saude": "Cuiabá",
                    "nivel": "laranja",
                    "score": 2,
                    "motivo": "calor",
                },
                {
                    "cod_ibge": "5107925",
                    "municipio": "Sorriso",
                    "regional_saude": "Sinop",
                    "nivel": "cinza",
                    "score": 0,
                    "motivo": "teste",
                },
            ]
        )
        with patch.dict(os.environ, {"ALERT_FORCE_MUNICIPIOS": "5107925"}, clear=False):
            payloads = build_alertas_multinivel(df, min_level="amarela")
        mun = [p for p in payloads if p.get("escopo") == "municipal"]
        ids = {str(p.get("alvo_id")) for p in mun}
        self.assertIn("5107925", ids)


    def test_ocupacao_sozinha_gera_indice_0_100(self) -> None:
        from sisclima.engines.indice_pressao_saude import build_indice_pressao_municipal

        df = pd.DataFrame(
            [
                {"cod_ibge": "5107925", "municipio": "Sorriso", "ocupacao_leitos_pct": 92.0},
                {"cod_ibge": "5103403", "municipio": "Cuiabá", "ocupacao_leitos_pct": 60.0},
            ]
        )
        out = build_indice_pressao_municipal(df)
        self.assertTrue(out["indice_pressao_saude"].notna().all())
        self.assertGreater(float(out.loc[out["cod_ibge"] == "5107925", "indice_pressao_saude"].iloc[0]), 69)


if __name__ == "__main__":
    unittest.main()
