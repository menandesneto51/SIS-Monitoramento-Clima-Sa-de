# -*- coding: utf-8 -*-
"""Cobertura EHF GeoCalor → resumo / RIT / alertas."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from sisclima.engines.ehf_geocalor import geocalor_linhas_alerta, inject_ehf_geocalor
from sisclima.engines.rit_multirisco import enrich_rit_multirisco, score_dominio_ehf


def _fake_star_daily() -> pd.DataFrame:
    rows = []
    for i, (cod, ehf, hw) in enumerate(
        [
            ("5103403", 2.5, 1),
            ("5107602", 0.8, 1),
            ("5107925", -1.0, 0),
            ("5100250", 0.0, 0),
            ("5106224", 3.2, 1),
        ]
    ):
        rows.append(
            {
                "cod_ibge": cod,
                "data": "2026-09-12",
                "ehf": ehf,
                "is_hw_day": hw,
                "intensidade": "severa" if ehf > 2 else ("baixa" if ehf > 0 else None),
                "municipio": f"Mun{i}",
            }
        )
    return pd.DataFrame(rows)


def _rt(name: str):
    if name == "star_clima_geocalor_diario":
        return _fake_star_daily()
    if name == "star_ondas_calor_evento":
        return pd.DataFrame()
    return pd.DataFrame()


class InjectEhfGeocalorTests(unittest.TestCase):
    def test_inject_covers_all_municipios_from_star(self) -> None:
        resumo = pd.DataFrame(
            {
                "cod_ibge": ["5103403", "5107602", "5107925", "5100250", "5106224"],
                "municipio": ["A", "B", "C", "D", "E"],
                "nivel": ["laranja", "amarela", "verde", "verde", "vermelha"],
            }
        )
        with patch("sisclima.core.db.read_table", side_effect=_rt):
            out = inject_ehf_geocalor(resumo.copy(), prefer_geocalor=True)

        self.assertEqual(int(out["ehf_geocalor"].notna().sum()), 5)
        self.assertEqual(int((pd.to_numeric(out["ehf_geocalor"], errors="coerce").fillna(0) > 0).sum()), 3)
        self.assertTrue((out["data_ehf_geocalor"].astype(str) == "2026-09-12").all())
        self.assertAlmostEqual(float(out.loc[out["cod_ibge"] == "5103403", "ehf_adaptado"].iloc[0]), 2.5)

    def test_score_dominio_prefer_ehf_geocalor(self) -> None:
        sc = score_dominio_ehf({"ehf_geocalor": 2.5, "ehf_adaptado": 0.1})
        self.assertGreaterEqual(sc, 85.0)

    def test_geocalor_linhas_alerta_quando_ehf_positivo(self) -> None:
        lines = geocalor_linhas_alerta(
            {
                "ehf_geocalor": 1.2,
                "intensidade_ehf": "baixa",
                "data_ehf_geocalor": "2026-09-12",
                "ehf_geocalor_idade_dias": 0,
                "is_hw_day": 1,
                "duracao_onda_ehf_dias": 4,
            }
        )
        self.assertTrue(any("GeoCalor / EHF" in x for x in lines))
        self.assertTrue(any("EHF 1.20" in x for x in lines))
        self.assertTrue(any("onda" in x.lower() for x in lines))

    def test_alerta_municipal_contem_bloco_geocalor(self) -> None:
        from sisclima.engines.alertas_multinivel import build_alertas_multinivel

        resumo = pd.DataFrame(
            {
                "cod_ibge": ["5103403", "5107602"],
                "municipio": ["Cuiabá", "Rondonópolis"],
                "regional_saude": ["Baixada Cuiabana", "Sul"],
                "nivel": ["laranja", "amarela"],
                "score": [2, 1],
                "tmax": [38.0, 36.0],
                "utci_proxy": [36.0, 34.0],
                "risco_cumulativo_3d": [2.0, 1.0],
                "ehf_geocalor": [2.5, 0.5],
                "ehf": [2.5, 0.5],
                "ehf_adaptado": [2.5, 0.5],
                "intensidade_ehf": ["severa", "baixa"],
                "is_hw_day": [1, 1],
                "data_ehf_geocalor": ["2026-09-12", "2026-09-12"],
                "ehf_geocalor_idade_dias": [0, 0],
                "duracao_onda_ehf_dias": [5, 3],
            }
        )
        with patch("sisclima.core.db.read_table", side_effect=_rt):
            resumo = enrich_rit_multirisco(resumo)
            payloads = build_alertas_multinivel(resumo, min_level="amarela")
        mun = [p for p in payloads if p.get("escopo") in {"municipal", "cuiaba"}]
        self.assertTrue(mun)
        with_geo = [p for p in mun if p.get("geocalor_linhas")]
        self.assertGreaterEqual(len(with_geo), 1)
        blob = "\n".join(with_geo[0]["geocalor_linhas"])
        self.assertIn("GeoCalor / EHF", blob)

    def test_onda_geocalor_ativa_no_inject(self) -> None:
        resumo = pd.DataFrame(
            {
                "cod_ibge": ["5103403", "5107925", "5100250"],
                "municipio": ["A", "B", "C"],
            }
        )
        with patch("sisclima.core.db.read_table", side_effect=_rt):
            out = inject_ehf_geocalor(resumo.copy(), prefer_geocalor=True)
        self.assertIn("onda_geocalor_ativa", out.columns)
        # 5103403: ehf 2.5 hw 1 → ativa; 5107925: ehf -1 hw 0 → 0; 5100250: 0/0 → 0
        a = out.set_index("cod_ibge")
        self.assertEqual(int(a.loc["5103403", "onda_geocalor_ativa"]), 1)
        self.assertEqual(str(a.loc["5103403", "onda_geocalor_severidade"]), "severa")
        self.assertEqual(int(a.loc["5107925", "onda_geocalor_ativa"]), 0)
        self.assertTrue(pd.isna(a.loc["5107925", "onda_geocalor_severidade"]) or a.loc["5107925", "onda_geocalor_severidade"] in (None, ""))


class StagesEhfFlagTests(unittest.TestCase):
    def _base_latest(self) -> dict:
        return {
            "utci_proxy": 28.0,  # verde/amarela baixa
            "tmax": 34.0,
            "ehf_geocalor": 2.5,
            "ehf_adaptado": 2.5,
            "is_hw_day": 1,
            "intensidade_ehf": "extrema",
            "duracao_onda_calor_dias": 2,  # abaixo do limiar de persistência
        }

    def test_usar_no_nivel_false_nao_eleva_por_intensidade(self) -> None:
        from sisclima.engines.stages import classify_stage

        settings = {
            "limiares_calor": {
                "utci": {"verde_max": 26, "amarela_max": 32, "laranja_max": 38, "vermelha_max": 46},
                "ehf": {"positivo": 0, "persistencia_dias_emergencia": 5, "usar_no_nivel": False},
            },
            "limiares_assistenciais": {},
            "limiares_operacionais": {},
            "qualidade_ar": {},
        }
        r = classify_stage(self._base_latest(), settings)
        self.assertEqual(int(r.indicadores.get("flag_candidato_ehf_dia") or 0), 0)
        # UTCI 28 → amarela (1); sem candidato EHF
        self.assertLessEqual(r.score, 1)

    def test_usar_no_nivel_true_extrema_eleva(self) -> None:
        from sisclima.engines.stages import classify_stage

        settings = {
            "limiares_calor": {
                "utci": {"verde_max": 26, "amarela_max": 32, "laranja_max": 38, "vermelha_max": 46},
                "ehf": {
                    "positivo": 0,
                    "persistencia_dias_emergencia": 5,
                    "usar_no_nivel": True,
                    "candidato_por_intensidade": {"baixa": 2, "severa": 3, "extrema": 4},
                },
            },
            "limiares_assistenciais": {},
            "limiares_operacionais": {},
            "qualidade_ar": {},
        }
        r = classify_stage(self._base_latest(), settings)
        self.assertEqual(int(r.indicadores.get("flag_candidato_ehf_dia") or 0), 1)
        self.assertGreaterEqual(r.score, 4)


if __name__ == "__main__":
    unittest.main()
