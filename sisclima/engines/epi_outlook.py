# -*- coding: utf-8 -*-
"""Perspectiva operacional de pressão em saúde (14d) — NÃO é nowcast epidemiológico.

Combina persistência do índice de pressão com overlay climático 14d
(`predicao_calor_14d_*`). Sem série SIVEP longa / correção de atraso, não
afirma incidência futura.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]
STAGE = {n: i for i, n in enumerate(LEVEL_ORDER)}


def build_perspectiva_pressao_14d(
    resumo: pd.DataFrame,
    pred14: pd.DataFrame | None = None,
    pressao: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return pd.DataFrame()

    base = resumo.copy()
    base["cod_ibge"] = base["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    base = base.dropna(subset=["cod_ibge"])

    if pressao is not None and not pressao.empty and "cod_ibge" in pressao.columns:
        p = pressao.copy()
        p["cod_ibge"] = p["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        keep = [c for c in ("cod_ibge", "indice_pressao_saude", "semaforo_pressao", "pred_indice_pressao_7d", "tendencia_pressao_7d") if c in p.columns]
        if len(keep) > 1:
            for c in keep:
                if c != "cod_ibge" and c in base.columns:
                    base = base.drop(columns=[c])
            base = base.merge(p[keep].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")

    pred_score = pd.Series(0.0, index=base.index)
    fonte_clima = "sem_predicao_14d"
    if pred14 is not None and not pred14.empty and "cod_ibge" in pred14.columns:
        pr = pred14.copy()
        pr["cod_ibge"] = pr["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        nivel_col = "nivel_predicao_14d" if "nivel_predicao_14d" in pr.columns else None
        score_col = "risco_preditivo_score" if "risco_preditivo_score" in pr.columns else None
        cols = ["cod_ibge"] + ([nivel_col] if nivel_col else []) + ([score_col] if score_col else [])
        pr = pr[cols].drop_duplicates("cod_ibge")
        base = base.merge(pr, on="cod_ibge", how="left", suffixes=("", "_p14"))
        if score_col and score_col in base.columns:
            pred_score = pd.to_numeric(base[score_col], errors="coerce").fillna(0.0)
            # score 0–4 → 0–100
            pred_score = (pred_score / 4.0) * 100.0
        elif nivel_col and nivel_col in base.columns:
            pred_score = base[nivel_col].astype(str).str.lower().map(STAGE).fillna(0) / 5.0 * 100.0
        fonte_clima = "predicao_calor_14d"

    press_atual = pd.to_numeric(base.get("indice_pressao_saude"), errors="coerce")
    if press_atual.isna().all() and "indice_vigilancia_integrada" in base.columns:
        press_atual = pd.to_numeric(base["indice_vigilancia_integrada"], errors="coerce")

    # Persistência 55% + overlay climático 45% (mesmo espírito do pred_indice_pressao_7d)
    outlook = 0.55 * press_atual.fillna(0) + 0.45 * pred_score.fillna(0)
    # Sem pressão nem clima → nulo
    mask_empty = press_atual.isna() & (pred_score.fillna(0) == 0)
    outlook = outlook.where(~mask_empty, np.nan)

    def _semaforo(v: float) -> str:
        if pd.isna(v):
            return "cinza"
        if v < 40:
            return "verde"
        if v < 70:
            return "amarela"
        return "vermelha"

    out = pd.DataFrame(
        {
            "cod_ibge": base["cod_ibge"],
            "municipio": base["municipio"] if "municipio" in base.columns else "",
            "regional_saude": base["regional_saude"] if "regional_saude" in base.columns else "",
            "indice_pressao_atual": press_atual,
            "overlay_clima_14d": pred_score,
            "perspectiva_pressao_14d": outlook.round(1),
            "semaforo_perspectiva_14d": outlook.map(_semaforo),
            "tendencia_pressao_7d": base["tendencia_pressao_7d"] if "tendencia_pressao_7d" in base.columns else "",
            "nivel_predicao_14d": base["nivel_predicao_14d"] if "nivel_predicao_14d" in base.columns else "",
            "fonte_outlook": fonte_clima,
            "disclaimer": "Perspectiva operacional (persistência + clima 14d). Não é nowcast epidemiológico 14–28d.",
            "atualizado_em": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    return out.sort_values("perspectiva_pressao_14d", ascending=False).reset_index(drop=True)


def summarize_outlook(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {"n": 0, "vermelha": 0, "amarela": 0, "verde": 0}
    s = df["semaforo_perspectiva_14d"].astype(str).str.lower()
    return {
        "n": int(len(df)),
        "vermelha": int(s.eq("vermelha").sum()),
        "amarela": int(s.eq("amarela").sum()),
        "verde": int(s.eq("verde").sum()),
        "media": float(pd.to_numeric(df["perspectiva_pressao_14d"], errors="coerce").mean() or 0),
    }
