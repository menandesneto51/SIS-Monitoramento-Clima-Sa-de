# -*- coding: utf-8 -*-
"""Risco hidrológico municipal a partir de séries ANA (padrão claro hidro_risco_v14)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _nivel_alerta(score: float) -> str:
    if score >= 5:
        return "vermelha"
    if score >= 3:
        return "laranja"
    if score >= 1:
        return "amarela"
    return "verde"


def _tendencia(delta: float, limiar: float) -> str:
    if pd.isna(delta):
        return "indisponivel"
    if delta >= limiar:
        return "subindo"
    if delta <= -limiar:
        return "caindo"
    return "estavel"


def _score_series(valores: pd.Series, valor_ult: float, delta_7d: float, limiar_delta: float) -> tuple[int, int, list[str], str]:
    p10 = float(valores.quantile(0.10))
    p25 = float(valores.quantile(0.25))
    p75 = float(valores.quantile(0.75))
    p90 = float(valores.quantile(0.90))
    tend = _tendencia(delta_7d, limiar_delta)
    score_estiagem = 0
    score_cheia = 0
    motivo: list[str] = []
    if valor_ult <= p10:
        score_estiagem += 3
        motivo.append("valor <= P10")
    elif valor_ult <= p25:
        score_estiagem += 1
        motivo.append("valor <= P25")
    if valor_ult >= p90:
        score_cheia += 3
        motivo.append("valor >= P90")
    elif valor_ult >= p75:
        score_cheia += 1
        motivo.append("valor >= P75")
    if tend == "caindo":
        score_estiagem += 1
        motivo.append("tendencia queda 7d")
    if tend == "subindo":
        score_cheia += 1
        motivo.append("tendencia subida 7d")
    return score_estiagem, score_cheia, motivo, tend


def compute_hidro_risco_from_ana(telemetria: pd.DataFrame) -> pd.DataFrame:
    """Calcula risco hidro municipal a partir de ana_telemetria (cota/vazao/chuva)."""
    if telemetria is None or telemetria.empty:
        return pd.DataFrame()
    df = telemetria.copy()
    if "data" not in df.columns and "data_hora" in df.columns:
        df["data"] = pd.to_datetime(df["data_hora"], errors="coerce").dt.normalize()
    else:
        df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
    df = df.dropna(subset=["data"])
    if df.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    # Séries por município e variável
    for var, label in [("cota_cm", "cota"), ("vazao_m3s", "vazao"), ("chuva_mm", "chuva")]:
        if var not in df.columns:
            continue
        work = df.copy()
        work[var] = pd.to_numeric(work[var], errors="coerce")
        work = work.dropna(subset=[var])
        keys = [c for c in ["cod_ibge", "municipio"] if c in work.columns]
        if not keys:
            continue
        for key_vals, g in work.groupby(keys, dropna=False):
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            meta = dict(zip(keys, key_vals))
            g = g.sort_values("data")
            daily = g.groupby("data", as_index=False)[var].median()
            if len(daily) < 7:
                continue
            valores = daily[var].dropna()
            if len(valores) < 7:
                continue
            valor_ult = float(valores.iloc[-1])
            ult7 = float(daily.tail(7)[var].mean()) if len(daily) >= 7 else np.nan
            ant7 = float(daily.iloc[-14:-7][var].mean()) if len(daily) >= 14 else np.nan
            delta_7d = float(ult7 - ant7) if not pd.isna(ult7) and not pd.isna(ant7) else np.nan
            iqr = float(valores.quantile(0.75) - valores.quantile(0.25))
            limiar = max(abs(iqr) * 0.10, 1.0)
            se, sc, motivo, tend = _score_series(valores, valor_ult, delta_7d, limiar)
            # Chuva alta reforça cheia; chuva baixa não marca estiagem de rio
            if label == "chuva":
                se = 0
                if valor_ult >= float(valores.quantile(0.90)):
                    sc = max(sc, 2)
                    motivo = [m for m in motivo if "P10" not in m and "P25" not in m] or ["chuva alta (P90)"]
            score = max(se, sc)
            rows.append(
                {
                    **meta,
                    "variavel": label,
                    "n_dias": int(len(daily)),
                    "data_ultima": daily["data"].max().strftime("%Y-%m-%d"),
                    "valor_ultimo": round(valor_ult, 3),
                    "delta_7d": round(delta_7d, 3) if not pd.isna(delta_7d) else np.nan,
                    "tendencia_7d": tend,
                    "score_estiagem": se,
                    "score_cheia": sc,
                    "score_hidro": score,
                    "nivel_alerta_hidro": _nivel_alerta(score),
                    "motivo_tecnico": "; ".join(motivo) if motivo else "sem gatilho",
                }
            )

    if not rows:
        return pd.DataFrame()
    est = pd.DataFrame(rows)
    group_keys = [c for c in ["cod_ibge", "municipio"] if c in est.columns]
    mun = (
        est.groupby(group_keys, as_index=False)
        .agg(
            n_series=("variavel", "nunique"),
            score_hidro_max=("score_hidro", "max"),
            score_estiagem_max=("score_estiagem", "max"),
            score_cheia_max=("score_cheia", "max"),
            data_mais_recente=("data_ultima", "max"),
            motivo_resumo=("motivo_tecnico", lambda s: " | ".join(list(s)[:3])[:800]),
        )
    )
    mun["nivel_alerta_hidro"] = mun["score_hidro_max"].map(_nivel_alerta)
    mun["risco_predominante"] = np.where(
        mun["score_estiagem_max"] > mun["score_cheia_max"],
        "estiagem_rio_baixo",
        np.where(mun["score_cheia_max"] > mun["score_estiagem_max"], "cheia_subida_rio", "misto_ou_neutro"),
    )
    mun["fonte"] = "ANA_telemetria_percentis"
    mun["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    mun["nota_tecnica"] = "Risco hidrológico ecológico por percentis/tendência 7d (padrão hidro_risco_v14, Python claro)."
    return mun
