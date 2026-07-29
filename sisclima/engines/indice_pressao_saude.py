# -*- coding: utf-8 -*-
"""
Índice de pressão em saúde (semáforo verde / amarela / vermelha).

Pilares: IndicaSUS · SISREG · SINAN · SIM — agravos com correlação climática
documentada. Cada KPI traz cenário atual, predição ~7d e tendência (alta/queda).

Distinto do nível operacional de 5 cores (verde→roxa): este módulo resume a
pressão assistencial-epidemiológica para leitura rápida do gestor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "indice_pressao_semaforo.yaml"

SEMAFORO_COLOR = {
    "verde": "#16803c",
    "amarela": "#c49200",
    "vermelha": "#dc2626",
}

SEMAFORO_EMOJI = {
    "verde": "🟢",
    "amarela": "🟡",
    "vermelha": "🔴",
}

TENDENCIA_EMOJI = {
    "subindo": "↑",
    "estavel": "→",
    "descendo": "↓",
    "—": "—",
}

# Mapa nível preditivo (5 cores) → pressão esperada 0–100
_PRED_NIVEL_TO_SCORE = {
    "cinza": np.nan,
    "verde": 18.0,
    "amarela": 42.0,
    "laranja": 62.0,
    "vermelha": 82.0,
    "roxa": 95.0,
}


def _load_cfg() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _num(s: Any) -> pd.Series:
    if isinstance(s, pd.Series):
        return pd.to_numeric(s, errors="coerce")
    try:
        return pd.to_numeric(pd.Series(s), errors="coerce")
    except Exception:
        return pd.Series(dtype=float)


def _ibge(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d{7})", expand=False)


def semaforo_from_score(score: float | None, verde_max: float = 39, amarela_max: float = 69) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "—"
    try:
        v = float(score)
    except (TypeError, ValueError):
        return "—"
    if v <= verde_max:
        return "verde"
    if v <= amarela_max:
        return "amarela"
    return "vermelha"


def _semaforo_limiar(valor: float | None, verde_max: float, amarela_max: float) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "—"
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return "—"
    if v <= verde_max:
        return "verde"
    if v <= amarela_max:
        return "amarela"
    return "vermelha"


def _score_from_semaforo(sem: str) -> float:
    return {"verde": 20.0, "amarela": 55.0, "vermelha": 88.0}.get(str(sem).lower(), np.nan)


def _tendencia(atual: float | None, pred: float | None, delta_min: float = 5.0) -> str:
    if atual is None or pred is None:
        return "—"
    try:
        a, p = float(atual), float(pred)
    except (TypeError, ValueError):
        return "—"
    if np.isnan(a) or np.isnan(p):
        return "—"
    d = p - a
    if d >= delta_min:
        return "subindo"
    if d <= -delta_min:
        return "descendo"
    return "estavel"


def catalogo_agravos(cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or _load_cfg()
    rows = cfg.get("agravos_clima") or []
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    if "indicadores" in out.columns:
        out["indicadores"] = out["indicadores"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else str(x)
        )
    return out


def _agg_sim_municipal(sim_mun: pd.DataFrame) -> pd.DataFrame:
    if sim_mun is None or sim_mun.empty or "cod_ibge" not in sim_mun.columns:
        return pd.DataFrame(columns=["cod_ibge", "obitos_sim_calor", "grupos_sim"])
    s = sim_mun.copy()
    s["cod_ibge"] = _ibge(s["cod_ibge"])
    obito_col = "obitos" if "obitos" in s.columns else None
    if obito_col is None:
        for c in ("obitos_total", "eventos", "n_obitos"):
            if c in s.columns:
                obito_col = c
                break
    if obito_col is None:
        return pd.DataFrame(columns=["cod_ibge", "obitos_sim_calor", "grupos_sim"])
    s[obito_col] = pd.to_numeric(s[obito_col], errors="coerce").fillna(0)
    g = s.groupby("cod_ibge", as_index=False).agg(
        obitos_sim_calor=(obito_col, "sum"),
        grupos_sim=("grupo_obito_calor", "nunique")
        if "grupo_obito_calor" in s.columns
        else (obito_col, "count"),
    )
    return g


def _agg_saude_calor(saude_calor: pd.DataFrame) -> pd.DataFrame:
    if saude_calor is None or saude_calor.empty or "cod_ibge" not in saude_calor.columns:
        return pd.DataFrame(columns=["cod_ibge", "eventos_sinan_calor"])
    s = saude_calor.copy()
    s["cod_ibge"] = _ibge(s["cod_ibge"])
    # Preferir eventos SINAN quando a coluna fonte existir
    if "fonte" in s.columns:
        mask = s["fonte"].astype(str).str.upper().str.contains("SINAN", na=False)
        if mask.any():
            s = s.loc[mask]
    ev = "eventos" if "eventos" in s.columns else None
    if ev is None:
        return pd.DataFrame(columns=["cod_ibge", "eventos_sinan_calor"])
    s[ev] = pd.to_numeric(s[ev], errors="coerce").fillna(0)
    return s.groupby("cod_ibge", as_index=False).agg(eventos_sinan_calor=(ev, "sum"))


def _prep_sisreg(sisreg: pd.DataFrame | None) -> pd.DataFrame:
    if sisreg is None or sisreg.empty or "cod_ibge" not in sisreg.columns:
        return pd.DataFrame()
    s = sisreg.copy()
    s["cod_ibge"] = _ibge(s["cod_ibge"])
    return s


def build_indice_pressao_municipal(
    resumo: pd.DataFrame,
    *,
    sim_mun: pd.DataFrame | None = None,
    saude_calor_mun: pd.DataFrame | None = None,
    pred_7d: pd.DataFrame | None = None,
    sisreg: pd.DataFrame | None = None,
    cfg: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Monta KPIs por município + índice composto + semáforo 3 cores + pred/tendência."""
    cfg = cfg or _load_cfg()
    if resumo is None or resumo.empty:
        return pd.DataFrame()

    sem_cfg = cfg.get("semaforo") or {}
    verde_max = float(sem_cfg.get("verde_max", 39))
    amarela_max = float(sem_cfg.get("amarela_max", 69))
    delta_min = float((cfg.get("tendencia") or {}).get("delta_min", 5))
    pilares = cfg.get("pilares") or {}

    lim_ocup = (pilares.get("indicasus") or {}).get("limiares_ocupacao_pct") or {}
    lim_fila = (pilares.get("sisreg") or {}).get("limiares_fila_horas") or {}
    lim_sol = (pilares.get("sisreg") or {}).get("limiares_solicitacoes_abertas") or {}
    lim_z = (pilares.get("sinan") or {}).get("limiares_zscore") or {}
    lim_c7 = (pilares.get("sinan") or {}).get("limiares_casos_7d") or {}
    lim_ob = (pilares.get("sim") or {}).get("limiares_obitos_janela") or {}

    w_ind = float((pilares.get("indicasus") or {}).get("peso", 0.30))
    w_sis = float((pilares.get("sisreg") or {}).get("peso", 0.20))
    w_sin = float((pilares.get("sinan") or {}).get("peso", 0.30))
    w_sim = float((pilares.get("sim") or {}).get("peso", 0.20))

    df = resumo.copy()
    if "cod_ibge" not in df.columns:
        return pd.DataFrame()
    df["cod_ibge"] = _ibge(df["cod_ibge"])

    # --- IndicaSUS ---
    ocup = _num(df["ocupacao_leitos_pct"]) if "ocupacao_leitos_pct" in df.columns else pd.Series(np.nan, index=df.index)
    df["kpi_indicasus_valor"] = ocup.round(1)
    df["kpi_indicasus_semaforo"] = [
        _semaforo_limiar(
            v,
            float(lim_ocup.get("verde_max", 79)),
            float(lim_ocup.get("amarela_max", 89)),
        )
        for v in ocup
    ]
    df["kpi_indicasus_score"] = df["kpi_indicasus_semaforo"].map(_score_from_semaforo)

    # --- SISREG ---
    sis = _prep_sisreg(sisreg)
    fila = pd.Series(np.nan, index=df.index)
    sols = pd.Series(np.nan, index=df.index)
    df["kpi_sisreg_disponivel"] = False
    if not sis.empty:
        keep = ["cod_ibge"]
        for c in ("fila_media_h", "tempo_espera_h", "solicitacoes_abertas", "taxa_regulacao_pct"):
            if c in sis.columns:
                keep.append(c)
        m = sis[keep].drop_duplicates("cod_ibge")
        merged = df[["cod_ibge"]].merge(m, on="cod_ibge", how="left")
        if "fila_media_h" in merged.columns:
            fila = _num(merged["fila_media_h"])
        elif "tempo_espera_h" in merged.columns:
            fila = _num(merged["tempo_espera_h"])
        if "solicitacoes_abertas" in merged.columns:
            sols = _num(merged["solicitacoes_abertas"])
        df["kpi_sisreg_disponivel"] = fila.notna() | sols.notna()

    df["kpi_sisreg_fila_h"] = fila.round(1)
    df["kpi_sisreg_solicitacoes"] = sols.round(0)
    sem_fila = [
        _semaforo_limiar(v, float(lim_fila.get("verde_max", 24)), float(lim_fila.get("amarela_max", 72)))
        for v in fila
    ]
    sem_sol = [
        _semaforo_limiar(v, float(lim_sol.get("verde_max", 10)), float(lim_sol.get("amarela_max", 40)))
        for v in sols
    ]
    # Pior dos dois quando ambos existem
    rank = {"—": -1, "verde": 0, "amarela": 1, "vermelha": 2}

    def _max_sem(a: str, b: str) -> str:
        if a == "—" and b == "—":
            return "—"
        if a == "—":
            return b
        if b == "—":
            return a
        return a if rank.get(a, -1) >= rank.get(b, -1) else b

    df["kpi_sisreg_semaforo"] = [_max_sem(a, b) for a, b in zip(sem_fila, sem_sol)]
    df["kpi_sisreg_score"] = df["kpi_sisreg_semaforo"].map(_score_from_semaforo)

    # --- SINAN ---
    casos7 = (
        _num(df["casos_arbovirus_7d"])
        if "casos_arbovirus_7d" in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    zarb = (
        _num(df["zscore_arbovirus"])
        if "zscore_arbovirus" in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    srag = _num(df["casos_srag"]) if "casos_srag" in df.columns else pd.Series(np.nan, index=df.index)
    calor_ev = _agg_saude_calor(saude_calor_mun)
    eventos_sinan = pd.Series(np.nan, index=df.index)
    if not calor_ev.empty:
        m = df[["cod_ibge"]].merge(calor_ev, on="cod_ibge", how="left")
        eventos_sinan = _num(m["eventos_sinan_calor"])

    df["kpi_sinan_casos_7d"] = casos7.round(0)
    df["kpi_sinan_zscore"] = zarb.round(2)
    df["kpi_sinan_srag"] = srag.round(0)
    df["kpi_sinan_eventos_calor"] = eventos_sinan.round(0)

    sem_z = [
        _semaforo_limiar(v, float(lim_z.get("verde_max", 0.99)), float(lim_z.get("amarela_max", 1.99)))
        for v in zarb
    ]
    sem_c = [
        _semaforo_limiar(v, float(lim_c7.get("verde_max", 4)), float(lim_c7.get("amarela_max", 14)))
        for v in casos7
    ]
    # SRAG: usa mesmos limiares de casos_7d como aproximação operacional
    sem_s = [
        _semaforo_limiar(v, float(lim_c7.get("verde_max", 4)), float(lim_c7.get("amarela_max", 14)))
        for v in srag
    ]
    sinan_sem = [_max_sem(_max_sem(a, b), c) for a, b, c in zip(sem_z, sem_c, sem_s)]
    # Se tudo vazio mas há eventos calor, classifica por eventos
    for i, ev in enumerate(eventos_sinan):
        if sinan_sem[i] == "—" and pd.notna(ev):
            sinan_sem[i] = _semaforo_limiar(
                float(ev),
                float(lim_c7.get("verde_max", 4)),
                float(lim_c7.get("amarela_max", 14)),
            )
    df["kpi_sinan_semaforo"] = sinan_sem
    df["kpi_sinan_score"] = df["kpi_sinan_semaforo"].map(_score_from_semaforo)

    # --- SIM ---
    sim_agg = _agg_sim_municipal(sim_mun)
    obitos = pd.Series(np.nan, index=df.index)
    if not sim_agg.empty:
        m = df[["cod_ibge"]].merge(sim_agg, on="cod_ibge", how="left")
        obitos = _num(m["obitos_sim_calor"])
    # Fallback: coluna já no resumo
    if obitos.isna().all() and "obitos_calor_suspeitos" in df.columns:
        obitos = _num(df["obitos_calor_suspeitos"])
    df["kpi_sim_obitos"] = obitos.round(0)
    df["kpi_sim_semaforo"] = [
        _semaforo_limiar(v, float(lim_ob.get("verde_max", 0)), float(lim_ob.get("amarela_max", 2)))
        for v in obitos
    ]
    df["kpi_sim_score"] = df["kpi_sim_semaforo"].map(_score_from_semaforo)

    # --- Índice composto (renormaliza pesos pelos pilares disponíveis) ---
    scores = []
    weights = []
    for col, w in (
        ("kpi_indicasus_score", w_ind),
        ("kpi_sisreg_score", w_sis),
        ("kpi_sinan_score", w_sin),
        ("kpi_sim_score", w_sim),
    ):
        scores.append(_num(df[col]))
        weights.append(w)

    arr = np.column_stack([s.to_numpy(dtype=float) for s in scores])
    w = np.array(weights, dtype=float)
    mask = ~np.isnan(arr)
    w_eff = mask * w
    w_sum = w_eff.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        comp = np.where(w_sum > 0, np.nansum(arr * w, axis=1) / w_sum, np.nan)
    df["indice_pressao_saude"] = pd.Series(comp, index=df.index).clip(0, 100).round(1)
    df["semaforo_pressao"] = [
        semaforo_from_score(v, verde_max, amarela_max) for v in df["indice_pressao_saude"]
    ]
    df["pilares_disponiveis"] = mask.sum(axis=1).astype(int)

    # --- Predição ~7d (ancorada no clima preditivo + tendência dos pilares) ---
    pred_score = pd.Series(np.nan, index=df.index)
    pred_nivel = pd.Series([None] * len(df), index=df.index, dtype=object)
    if pred_7d is not None and not pred_7d.empty and "cod_ibge" in pred_7d.columns:
        p = pred_7d.copy()
        p["cod_ibge"] = _ibge(p["cod_ibge"])
        col_nivel = "nivel_predicao_7d" if "nivel_predicao_7d" in p.columns else None
        col_risco = "risco_preditivo_score" if "risco_preditivo_score" in p.columns else None
        keep = ["cod_ibge"] + [c for c in (col_nivel, col_risco) if c]
        m = df[["cod_ibge"]].merge(p[keep].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        if col_nivel:
            pred_nivel = m[col_nivel].astype(str).str.lower()
            pred_score = pred_nivel.map(_PRED_NIVEL_TO_SCORE)
        if col_risco and pred_score.isna().all():
            # risco tipicamente 0–1 ou 0–100
            r = _num(m[col_risco])
            pred_score = np.where(r <= 1.5, r * 100.0, r)
            pred_score = pd.Series(pred_score, index=df.index).clip(0, 100)

    # Combina: 55% índice atual + 45% pressão esperada pelo clima preditivo
    # (quando pred falta, mantém atual = estável)
    atual = _num(df["indice_pressao_saude"])
    blend = pd.Series(
        np.where(
            pred_score.notna() & atual.notna(),
            0.55 * atual + 0.45 * pred_score,
            np.where(atual.notna(), atual, pred_score),
        ),
        index=df.index,
    ).clip(0, 100).round(1)

    df["pred_indice_pressao_7d"] = blend
    df["pred_nivel_clima_7d"] = pred_nivel
    df["semaforo_pressao_pred_7d"] = [
        semaforo_from_score(v, verde_max, amarela_max) for v in blend
    ]
    df["tendencia_pressao_7d"] = [
        _tendencia(a, p, delta_min) for a, p in zip(atual, blend)
    ]

    # Tendências por pilar (proxy: se pred clima sobe, pilares de demanda sobem)
    bump = pd.Series(
        np.where(pred_score.notna() & atual.notna(), pred_score - atual, 0.0),
        index=df.index,
    )

    def _pillar_pred(score_col: str) -> pd.Series:
        base = _num(df[score_col])
        return (base + bump.clip(lower=0) * 0.5 - (-bump.clip(upper=0)) * 0.5).clip(0, 100)

    for pillar, score_col in (
        ("indicasus", "kpi_indicasus_score"),
        ("sisreg", "kpi_sisreg_score"),
        ("sinan", "kpi_sinan_score"),
        ("sim", "kpi_sim_score"),
    ):
        pred_p = _pillar_pred(score_col)
        df[f"kpi_{pillar}_pred_7d"] = pred_p.round(1)
        df[f"kpi_{pillar}_tendencia"] = [
            _tendencia(a, p, delta_min) for a, p in zip(_num(df[score_col]), pred_p)
        ]
        df[f"kpi_{pillar}_semaforo_pred"] = [
            semaforo_from_score(v, verde_max, amarela_max) for v in pred_p
        ]

    df["indice_pressao_gerado_em"] = pd.Timestamp.now().isoformat(timespec="seconds")
    df["indice_pressao_versao"] = str(cfg.get("versao") or "1.0")
    return df


def state_pressao_summary(pressao: pd.DataFrame) -> dict[str, Any]:
    """KPIs estaduais do índice de pressão."""
    if pressao is None or pressao.empty:
        return {}
    out: dict[str, Any] = {
        "municipios": int(pressao["cod_ibge"].nunique()) if "cod_ibge" in pressao.columns else len(pressao),
    }
    if "indice_pressao_saude" in pressao.columns:
        s = _num(pressao["indice_pressao_saude"])
        out["indice_media"] = float(s.mean()) if s.notna().any() else None
        out["indice_max"] = float(s.max()) if s.notna().any() else None
    if "semaforo_pressao" in pressao.columns:
        vc = pressao["semaforo_pressao"].astype(str).str.lower().value_counts().to_dict()
        out["n_verde"] = int(vc.get("verde", 0))
        out["n_amarela"] = int(vc.get("amarela", 0))
        out["n_vermelha"] = int(vc.get("vermelha", 0))
    if "tendencia_pressao_7d" in pressao.columns:
        tc = pressao["tendencia_pressao_7d"].astype(str).str.lower().value_counts().to_dict()
        out["n_subindo"] = int(tc.get("subindo", 0))
        out["n_estavel"] = int(tc.get("estavel", 0))
        out["n_descendo"] = int(tc.get("descendo", 0))
    if "kpi_sisreg_disponivel" in pressao.columns:
        out["sisreg_cobertura"] = int(pressao["kpi_sisreg_disponivel"].fillna(False).astype(bool).sum())
    return out


def format_kpi_label(semaforo: str, tendencia: str) -> str:
    e = SEMAFORO_EMOJI.get(str(semaforo).lower(), "⚪")
    t = TENDENCIA_EMOJI.get(str(tendencia).lower(), "—")
    return f"{e} {str(semaforo).capitalize()} {t}"
