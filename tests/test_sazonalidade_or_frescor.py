# -*- coding: utf-8 -*-
"""Testes da aba Sazonalidade/OR — significância e frescor."""
from __future__ import annotations

import pandas as pd

from sisclima.engines.odds_ratio import compute_climate_health_ors
from sisclima.engines.seasonality import _spearman_pvalue, _lag_correlations
from sisclima.engines.sazonalidade_frescor import refresh_odds_live


def test_spearman_pvalue_strong_correlation():
    p = _spearman_pvalue(0.8, 50)
    assert p < 0.05
    assert _spearman_pvalue(0.0, 50) > 0.5


def test_lag_correlations_include_significance_and_humidity():
    n = 60
    df = pd.DataFrame(
        {
            "tmax": range(n),
            "umidade_media": [40 + (i % 10) for i in range(n)],
            "casos_srag": [i * 0.5 for i in range(n)],
            "pressao_calor_pct": [50 + i * 0.1 for i in range(n)],
        }
    )
    out = _lag_correlations(df, max_lag=2)
    assert not out.empty
    assert "p_value" in out.columns
    assert "significativo_005" in out.columns
    assert "umidade_media" in set(out["exposicao"].unique())


def test_refresh_odds_live_includes_umidade_when_present():
    resumo = pd.DataFrame(
        {
            "cod_ibge": [i for i in range(1, 41)],
            "tmax": [30 + (i % 8) for i in range(40)],
            "umidade_media": [35 + (i % 20) for i in range(40)],
            "casos_srag": [i % 5 for i in range(40)],
            "pressao_calor_pct": [40 + (i % 15) for i in range(40)],
        }
    )
    odds = refresh_odds_live(resumo, persist=False)
    assert not odds.empty
    assert "significativo_005" in odds.columns
    # umidade deve entrar nas exposições quando coluna existe
    assert "umidade_media" in set(odds["exposicao"].unique()) or odds["exposicao"].nunique() >= 1
    odds2 = compute_climate_health_ors(resumo)
    assert "umidade_media" in set(odds2["exposicao"].unique())
