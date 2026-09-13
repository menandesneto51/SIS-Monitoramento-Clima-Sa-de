# -*- coding: utf-8 -*-
"""Catálogo de exposições climáticas — Open-Meteo + Copernicus/CAMS + derivados ARARAS.

Usado por sazonalidade/lags e Odds Ratio ecológico. Só entra na análise o que
existir na série/resumo (não inventa coluna).
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

# Open-Meteo (forecast/archive) + biometeo derivado
CLIMA_OPENMETEO: tuple[str, ...] = (
    "tmax",
    "tmin",
    "umidade_media",
    "vento_max",
    "precipitacao_mm",
    "precipitacao_horas",
    "chuva_mm",
    "radiacao",
    "umidade_solo_0_1cm",
    "umidade_solo_1_3cm",
    "umidade_solo_3_9cm",
    "indice_saturacao_solo",
)

# Derivados do pipeline biometeo (não são da API bruta)
CLIMA_DERIVADOS: tuple[str, ...] = (
    "heat_index",
    "utci_proxy",
    "risco_cumulativo_3d",
    "risco_calor_diario",
    "amplitude_termica",
    "indice_tensao_climatica",
)

# Copernicus CAMS + IQA operacional
CLIMA_COPERNICUS: tuple[str, ...] = (
    "pm25_ugm3",
    "pm10_ugm3",
    "o3_ugm3",
    "no2_ugm3",
    "co_mgm3",
    "so2_ugm3",
    "iq_ar_score",
    "indice_qualidade_ar_operacional",
)

# Ordem canônica para agregação estadual / lags / OR
CLIMA_EXPOSICOES: tuple[str, ...] = tuple(
    dict.fromkeys(CLIMA_OPENMETEO + CLIMA_DERIVADOS + CLIMA_COPERNICUS)
)

CLIMA_ROTULOS: dict[str, str] = {
    "tmax": "Tmáx (°C)",
    "tmin": "Tmín (°C)",
    "umidade_media": "Umidade relativa (%)",
    "vento_max": "Vento máx.",
    "precipitacao_mm": "Precipitação (mm)",
    "precipitacao_horas": "Horas com chuva",
    "chuva_mm": "Chuva (mm)",
    "radiacao": "Radiação",
    "umidade_solo_0_1cm": "Umidade solo 0–1 cm",
    "umidade_solo_1_3cm": "Umidade solo 1–3 cm",
    "umidade_solo_3_9cm": "Umidade solo 3–9 cm",
    "indice_saturacao_solo": "Saturação do solo",
    "heat_index": "Índice de calor",
    "utci_proxy": "UTCI proxy",
    "risco_cumulativo_3d": "Risco cumulativo 3d",
    "risco_calor_diario": "Risco calor diário",
    "amplitude_termica": "Amplitude térmica",
    "indice_tensao_climatica": "Índice de tensão climática",
    "pm25_ugm3": "PM2,5",
    "pm10_ugm3": "PM10",
    "o3_ugm3": "Ozônio (O₃)",
    "no2_ugm3": "NO₂",
    "co_mgm3": "CO",
    "so2_ugm3": "SO₂",
    "iq_ar_score": "IQA (score 0–4)",
    "indice_qualidade_ar_operacional": "IQA operacional (%)",
}


def available_climate_cols(df: pd.DataFrame | None, cols: Iterable[str] | None = None) -> list[str]:
    """Colunas climáticas presentes e com pelo menos um valor numérico válido."""
    if df is None or df.empty:
        return []
    wanted = list(cols) if cols is not None else list(CLIMA_EXPOSICOES)
    out: list[str] = []
    for c in wanted:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().any():
            out.append(c)
    return out


def climate_coverage_report(
    met: pd.DataFrame | None,
    aq: pd.DataFrame | None = None,
) -> dict[str, object]:
    """Resumo de cobertura Open-Meteo / Copernicus para a UI."""
    frames = [f for f in (met, aq) if f is not None and not f.empty]
    if not frames:
        return {
            "openmeteo": [],
            "copernicus": [],
            "derivados": [],
            "todos": [],
            "faltando_catalogo": list(CLIMA_EXPOSICOES),
        }
    merged_cols: set[str] = set()
    for f in frames:
        merged_cols.update(available_climate_cols(f))
    # amplitude se tmax+tmin
    if "tmax" in merged_cols and "tmin" in merged_cols:
        merged_cols.add("amplitude_termica")
    om = [c for c in CLIMA_OPENMETEO if c in merged_cols]
    cp = [c for c in CLIMA_COPERNICUS if c in merged_cols]
    der = [c for c in CLIMA_DERIVADOS if c in merged_cols]
    todos = [c for c in CLIMA_EXPOSICOES if c in merged_cols]
    faltando = [c for c in CLIMA_EXPOSICOES if c not in merged_cols]
    return {
        "openmeteo": om,
        "copernicus": cp,
        "derivados": der,
        "todos": todos,
        "faltando_catalogo": faltando,
        "n_disponiveis": len(todos),
        "n_catalogo": len(CLIMA_EXPOSICOES),
    }


def ensure_amplitude_termica(df: pd.DataFrame) -> pd.DataFrame:
    """Cria amplitude_termica = tmax − tmin quando possível."""
    if df is None or df.empty:
        return df
    out = df
    if "amplitude_termica" not in out.columns and "tmax" in out.columns and "tmin" in out.columns:
        out = out.copy()
        out["amplitude_termica"] = pd.to_numeric(out["tmax"], errors="coerce") - pd.to_numeric(
            out["tmin"], errors="coerce"
        )
    return out
