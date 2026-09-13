# -*- coding: utf-8 -*-
"""Testes cobertura climática na sazonalidade/OR."""
from __future__ import annotations

import pandas as pd

from sisclima.engines.clima_exposicoes import (
    CLIMA_COPERNICUS,
    CLIMA_OPENMETEO,
    climate_coverage_report,
    ensure_amplitude_termica,
)
from sisclima.engines.odds_ratio import DEFAULT_EXPOSURES, compute_climate_health_ors
from sisclima.engines.seasonality import compute_seasonality_outputs


def test_catalog_covers_openmeteo_and_copernicus():
    assert "tmax" in CLIMA_OPENMETEO
    assert "umidade_media" in CLIMA_OPENMETEO
    assert "precipitacao_mm" in CLIMA_OPENMETEO
    assert "pm25_ugm3" in CLIMA_COPERNICUS
    assert "iq_ar_score" in CLIMA_COPERNICUS
    assert "pm10_ugm3" in CLIMA_COPERNICUS


def test_seasonality_merges_aq_and_uses_full_climate():
    n = 45
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    met = pd.DataFrame(
        {
            "data": dates,
            "tmax": [32 + (i % 5) for i in range(n)],
            "tmin": [20 + (i % 3) for i in range(n)],
            "umidade_media": [40 + (i % 20) for i in range(n)],
            "precipitacao_mm": [i % 7 for i in range(n)],
            "vento_max": [5 + (i % 4) for i in range(n)],
            "utci_proxy": [30 + (i % 4) for i in range(n)],
            "risco_cumulativo_3d": [i % 6 for i in range(n)],
        }
    )
    aq = pd.DataFrame(
        {
            "data": dates,
            "pm25_ugm3": [15 + (i % 10) for i in range(n)],
            "pm10_ugm3": [25 + (i % 12) for i in range(n)],
            "o3_ugm3": [40 + (i % 8) for i in range(n)],
            "iq_ar_score": [i % 4 for i in range(n)],
        }
    )
    sivep = pd.DataFrame({"data": dates, "casos_srag": [i % 5 for i in range(n)]})
    empty = pd.DataFrame()
    out = compute_seasonality_outputs(met, sivep, empty, empty, empty, qualidade_ar=aq)
    lags = out["clima_desfecho_lags_v1"]
    cob = out["sazonalidade_clima_cobertura_v1"]
    assert not lags.empty
    expos = set(lags["exposicao"].unique())
    for c in ("tmax", "tmin", "umidade_media", "precipitacao_mm", "pm25_ugm3", "pm10_ugm3", "iq_ar_score"):
        assert c in expos, f"faltou exposição {c}"
    assert "amplitude_termica" in expos or "amplitude_termica" in set(cob["variavel"])
    assert not cob.empty
    assert "iq_ar_score" in set(cob["variavel"])


def test_or_default_exposures_include_catalog():
    assert "umidade_media" in DEFAULT_EXPOSURES
    assert "pm10_ugm3" in DEFAULT_EXPOSURES
    assert "iq_ar_score" in DEFAULT_EXPOSURES
    assert "precipitacao_mm" in DEFAULT_EXPOSURES
    resumo = pd.DataFrame(
        {
            "cod_ibge": list(range(1, 31)),
            "tmax": [30 + i % 5 for i in range(30)],
            "umidade_media": [35 + i % 10 for i in range(30)],
            "pm25_ugm3": [10 + i % 8 for i in range(30)],
            "iq_ar_score": [i % 4 for i in range(30)],
            "precipitacao_mm": [i % 6 for i in range(30)],
            "casos_srag": [i % 4 for i in range(30)],
        }
    )
    resumo = ensure_amplitude_termica(resumo)
    odds = compute_climate_health_ors(resumo)
    assert not odds.empty
    expos = set(odds["exposicao"].unique())
    assert "umidade_media" in expos
    assert "pm25_ugm3" in expos
    assert "iq_ar_score" in expos


def test_climate_coverage_report():
    met = pd.DataFrame({"tmax": [1.0], "umidade_media": [50.0], "precipitacao_mm": [2.0]})
    aq = pd.DataFrame({"pm25_ugm3": [12.0], "iq_ar_score": [2]})
    rep = climate_coverage_report(met, aq)
    assert "tmax" in rep["openmeteo"]
    assert "pm25_ugm3" in rep["copernicus"]
    assert rep["n_disponiveis"] >= 4
