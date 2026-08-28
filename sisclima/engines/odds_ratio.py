# -*- coding: utf-8 -*-
"""Odds Ratio ecológico clima-saúde (municipal)."""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

try:
    from scipy import stats
except Exception:  # pragma: no cover
    stats = None


DEFAULT_EXPOSURES = [
    "tmax",
    "utci_proxy",
    "risco_cumulativo_3d",
    "pm25_ugm3",
    "precipitacao_mm",
    "indice_tensao_climatica",
]

DEFAULT_OUTCOMES = [
    "casos_srag",
    "casos_arbovirus_7d",
    "ocupacao_leitos_pct",
    "pressao_calor_pct",
    "obitos_calor_suspeitos",
    "indice_carga_saude",
]


def _fisher_p(a: int, b: int, c: int, d: int) -> float:
    if stats is None:
        return float("nan")
    try:
        _, p = stats.fisher_exact([[a, b], [c, d]])
        return float(p)
    except Exception:
        return float("nan")


def _interpret_or(orv: float, p: float) -> str:
    if pd.isna(orv):
        return "indeterminado"
    sig = (not pd.isna(p)) and p < 0.05
    if orv >= 2:
        return "associação positiva forte" + (" (significativa)" if sig else "")
    if orv > 1:
        return "associação positiva" + (" (significativa)" if sig else "")
    if orv <= 0.5:
        return "associação negativa forte" + (" (significativa)" if sig else "")
    if orv < 1:
        return "associação negativa" + (" (significativa)" if sig else "")
    return "sem associação aparente"


def _binarize(s: pd.Series, mode: str = "q75") -> tuple[pd.Series, float]:
    x = pd.to_numeric(s, errors="coerce")
    if x.notna().sum() < 8:
        return pd.Series(np.nan, index=s.index), float("nan")
    if mode == "q75":
        thr = float(x.quantile(0.75))
    else:
        thr = float(x.median())
    return (x >= thr).astype(float), thr


def or_binary(
    df: pd.DataFrame,
    exposure_col: str,
    outcome_col: str,
    exposure_thr_mode: str = "q75",
    outcome_thr_mode: str = "q75",
) -> dict | None:
    if exposure_col not in df.columns or outcome_col not in df.columns:
        return None
    work = df[[exposure_col, outcome_col]].copy()
    exp_bin, exp_thr = _binarize(work[exposure_col], exposure_thr_mode)
    out_bin, out_thr = _binarize(work[outcome_col], outcome_thr_mode)
    work["_exp"] = exp_bin
    work["_out"] = out_bin
    work = work.dropna(subset=["_exp", "_out"])
    if len(work) < 12 or work["_exp"].nunique() < 2 or work["_out"].nunique() < 2:
        return None

    tab = pd.crosstab(work["_exp"], work["_out"])
    a = int(tab.loc[1.0, 1.0]) if 1.0 in tab.index and 1.0 in tab.columns else 0
    b = int(tab.loc[1.0, 0.0]) if 1.0 in tab.index and 0.0 in tab.columns else 0
    c = int(tab.loc[0.0, 1.0]) if 0.0 in tab.index and 1.0 in tab.columns else 0
    d = int(tab.loc[0.0, 0.0]) if 0.0 in tab.index and 0.0 in tab.columns else 0

    aa, bb, cc, dd = map(float, [a, b, c, d])
    if min(aa, bb, cc, dd) == 0:
        aa += 0.5
        bb += 0.5
        cc += 0.5
        dd += 0.5

    orv = (aa * dd) / (bb * cc)
    se = math.sqrt(1.0 / aa + 1.0 / bb + 1.0 / cc + 1.0 / dd)
    lcl = math.exp(math.log(orv) - 1.96 * se)
    ucl = math.exp(math.log(orv) + 1.96 * se)
    p = _fisher_p(a, b, c, d)

    return {
        "exposicao": exposure_col,
        "desfecho": outcome_col,
        "n_analisado": int(len(work)),
        "limiar_exposicao": exp_thr,
        "limiar_desfecho": out_thr,
        "eventos_expostos": a,
        "nao_eventos_expostos": b,
        "eventos_nao_expostos": c,
        "nao_eventos_nao_expostos": d,
        "or": float(orv),
        "ic95_inferior": float(lcl),
        "ic95_superior": float(ucl),
        "p_value": p,
        "significativo_005": bool((not pd.isna(p)) and p < 0.05),
        "interpretacao": _interpret_or(orv, p),
        "nota_tecnica": "OR ecológico municipal (não causal individual).",
    }


def compute_climate_health_ors(
    resumo: pd.DataFrame,
    exposures: Iterable[str] | None = None,
    outcomes: Iterable[str] | None = None,
) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    work = resumo.copy()
    if "cod_ibge" in work.columns:
        work = work.drop_duplicates("cod_ibge", keep="first")
    exps = [c for c in (exposures or DEFAULT_EXPOSURES) if c in work.columns]
    outs = [c for c in (outcomes or DEFAULT_OUTCOMES) if c in work.columns]
    rows: list[dict] = []
    for exp in exps:
        for out in outs:
            if exp == out:
                continue
            item = or_binary(work, exp, out)
            if item:
                rows.append(item)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["significativo_005", "or"], ascending=[False, False])
    df["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    return df


def compute_or_timeline(
    daily: pd.DataFrame,
    exposure_col: str,
    outcome_col: str,
    *,
    window_days: int = 28,
    step_days: int = 7,
) -> pd.DataFrame:
    """OR ecológico em janelas móveis (dias de alta exposição × desfecho alto)."""
    if daily is None or daily.empty or "data" not in daily.columns:
        return pd.DataFrame()
    if exposure_col not in daily.columns or outcome_col not in daily.columns:
        return pd.DataFrame()
    work = daily.copy()
    work["data"] = pd.to_datetime(work["data"], errors="coerce")
    work = work.dropna(subset=["data"]).sort_values("data")
    if len(work) < 14:
        return pd.DataFrame()
    dates = work["data"].dt.normalize().drop_duplicates().sort_values()
    rows: list[dict] = []
    start = dates.min()
    end = dates.max()
    cursor = start + pd.Timedelta(days=window_days)
    while cursor <= end:
        win = work[(work["data"] > cursor - pd.Timedelta(days=window_days)) & (work["data"] <= cursor)]
        item = or_binary(win, exposure_col, outcome_col)
        if item:
            item["data"] = cursor.strftime("%Y-%m-%d")
            item["janela_dias"] = window_days
            rows.append(item)
        cursor += pd.Timedelta(days=step_days)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def compute_or_by_group(
    resumo: pd.DataFrame,
    group_col: str,
    exposure_col: str,
    outcome_col: str,
    *,
    min_n: int = 12,
) -> pd.DataFrame:
    """OR por grupo territorial (regional, etc.) — grupos com mais chance de desfecho na alta exposição."""
    if resumo is None or resumo.empty or group_col not in resumo.columns:
        return pd.DataFrame()
    if exposure_col not in resumo.columns or outcome_col not in resumo.columns:
        return pd.DataFrame()
    rows: list[dict] = []
    for grupo, sub in resumo.groupby(group_col, dropna=True):
        if len(sub) < min_n:
            continue
        item = or_binary(sub, exposure_col, outcome_col)
        if not item:
            continue
        item["grupo"] = str(grupo)
        item["n_municipios"] = int(len(sub))
        rows.append(item)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["significativo_005", "or"], ascending=[False, False])

