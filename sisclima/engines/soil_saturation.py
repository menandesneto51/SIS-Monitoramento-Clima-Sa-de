# -*- coding: utf-8 -*-
"""Índice de saturação do solo a partir de umidade volumétrica (Open-Meteo)."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Referências físicas operacionais (m³/m³) para solos tropicais tipicos — não calibrado por pedologia municipal.
SOIL_WILT = 0.05
SOIL_SAT_REF = 0.42

SOIL_MOISTURE_COLS = [
    "umidade_solo_0_1cm",
    "umidade_solo_1_3cm",
    "umidade_solo_3_9cm",
]


def _class_saturacao(idx: float) -> str:
    if pd.isna(idx):
        return "indisponivel"
    if idx >= 85:
        return "critica"
    if idx >= 70:
        return "alta"
    if idx >= 40:
        return "moderada"
    return "baixa"


def volumetric_to_saturation_index(sm: pd.Series, wilt: float = SOIL_WILT, sat: float = SOIL_SAT_REF) -> pd.Series:
    x = pd.to_numeric(sm, errors="coerce")
    span = max(sat - wilt, 1e-6)
    return ((x - wilt) / span * 100.0).clip(0, 100)


def enrich_soil_saturation(met: pd.DataFrame) -> pd.DataFrame:
    """Adiciona umidade média superficial e indice_saturacao_solo ao frame met."""
    if met is None or met.empty:
        return met if met is not None else pd.DataFrame()
    out = met.copy()
    present = [c for c in SOIL_MOISTURE_COLS if c in out.columns]
    if not present:
        # Aceita nomes brutos Open-Meteo se ainda não renomeados
        rename = {
            "soil_moisture_0_to_1cm": "umidade_solo_0_1cm",
            "soil_moisture_1_to_3cm": "umidade_solo_1_3cm",
            "soil_moisture_3_to_9cm": "umidade_solo_3_9cm",
        }
        out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
        present = [c for c in SOIL_MOISTURE_COLS if c in out.columns]
    if not present:
        return out

    for c in present:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    # Média ponderada superficial (mais peso nas camadas mais rasas)
    weights = {"umidade_solo_0_1cm": 0.5, "umidade_solo_1_3cm": 0.3, "umidade_solo_3_9cm": 0.2}
    wsum = np.zeros(len(out), dtype=float)
    vsum = np.zeros(len(out), dtype=float)
    for c in present:
        w = weights.get(c, 1.0 / len(present))
        vals = out[c].to_numpy(dtype=float)
        mask = ~np.isnan(vals)
        wsum[mask] += w
        vsum[mask] += vals[mask] * w
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(wsum > 0, vsum / wsum, np.nan)
    out["umidade_solo_media"] = media
    out["indice_saturacao_solo"] = volumetric_to_saturation_index(out["umidade_solo_media"]).round(1)
    out["classe_saturacao_solo"] = out["indice_saturacao_solo"].map(_class_saturacao)
    out["fonte_solo"] = out.get("fonte_solo", pd.Series("openmeteo", index=out.index))
    return out


def municipal_soil_snapshot(met: pd.DataFrame, resumo: pd.DataFrame | None = None) -> pd.DataFrame:
    """Último dia por município com saturação do solo."""
    if met is None or met.empty:
        return pd.DataFrame()
    df = enrich_soil_saturation(met)
    if "indice_saturacao_solo" not in df.columns:
        return pd.DataFrame()
    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce")
        df = df.sort_values("data").groupby("cod_ibge", as_index=False).tail(1) if "cod_ibge" in df.columns else df.tail(1)
    keep = [
        c
        for c in [
            "cod_ibge",
            "municipio",
            "data",
            "umidade_solo_0_1cm",
            "umidade_solo_1_3cm",
            "umidade_solo_3_9cm",
            "umidade_solo_media",
            "indice_saturacao_solo",
            "classe_saturacao_solo",
            "precipitacao_mm",
            "fonte_solo",
        ]
        if c in df.columns
    ]
    out = df[keep].copy()
    if resumo is not None and not resumo.empty and "cod_ibge" in resumo.columns and "cod_ibge" in out.columns:
        extras = [c for c in ["regional_saude", "nivel", "score"] if c in resumo.columns]
        if extras:
            m = resumo[["cod_ibge"] + extras].drop_duplicates("cod_ibge")
            m["cod_ibge"] = m["cod_ibge"].astype(str)
            out["cod_ibge"] = out["cod_ibge"].astype(str)
            out = out.merge(m, on="cod_ibge", how="left")
    out["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    return out
