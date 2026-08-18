# -*- coding: utf-8 -*-
"""
Índice de prioridade global (0–100).

Soma ponderada de camadas já normalizadas — não soma KPIs brutos.
Pilares ausentes são omitidos e os pesos renormalizados (completude_meta_pct).
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.config import SETTINGS

DEFAULT_WEIGHTS = {
    "vigilancia": 0.30,
    "pressao": 0.25,
    "adaptacao": 0.20,
    "fragilidade": 0.15,  # 100 − resiliência
    "alerta": 0.10,
}

FAIXAS_DEFAULT = {
    "baixa_max": 30,
    "moderada_max": 60,
    "alta_max": 80,
}

PRIORIDADE_COLS = [
    "indice_prioridade_global",
    "faixa_prioridade_global",
    "completude_prioridade_pct",
    "pilares_prioridade",
    "tendencia_prioridade_7d",
    "orientacao_prioridade",
]


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _cfg() -> dict[str, Any]:
    painel = (SETTINGS.get("indicadores_painel") or {}) if isinstance(SETTINGS, dict) else {}
    meta = dict(painel.get("meta_global") or {})
    pesos = dict(DEFAULT_WEIGHTS)
    pesos.update(meta.get("pesos") or {})
    # Overrides opcionais via env
    for key, env_key in (
        ("vigilancia", "META_W_VIGILANCIA"),
        ("pressao", "META_W_PRESSAO"),
        ("adaptacao", "META_W_ADAPTACAO"),
        ("fragilidade", "META_W_FRAGILIDADE"),
        ("alerta", "META_W_ALERTA"),
    ):
        raw = os.getenv(env_key)
        if raw:
            try:
                pesos[key] = float(raw)
            except ValueError:
                pass
    faixas = dict(FAIXAS_DEFAULT)
    faixas.update(meta.get("faixas") or painel.get("faixas") or {})
    return {"pesos": pesos, "faixas": faixas, "notas": meta.get("notas") or ""}


def _faixa(v: float, faixas: dict[str, Any]) -> str:
    if pd.isna(v):
        return "—"
    if v <= float(faixas.get("baixa_max", 30)):
        return "baixa"
    if v <= float(faixas.get("moderada_max", 60)):
        return "moderada"
    if v <= float(faixas.get("alta_max", 80)):
        return "alta"
    return "muito alta"


def _pillar_series(df: pd.DataFrame, name: str) -> pd.Series:
    """Extrai pilar 0–100 (NaN se indisponível)."""
    n = len(df)
    idx = df.index
    if name == "vigilancia":
        if "indice_vigilancia_integrada" not in df.columns:
            return pd.Series(np.nan, index=idx)
        return _num(df["indice_vigilancia_integrada"])
    if name == "pressao":
        if "indice_pressao_saude" not in df.columns:
            return pd.Series(np.nan, index=idx)
        return _num(df["indice_pressao_saude"])
    if name == "adaptacao":
        # No ARARAS, índice adaptação deriva dos riscos AdaptaSUS (maior = mais pressão).
        if "indice_adaptacao_climatica" not in df.columns:
            return pd.Series(np.nan, index=idx)
        return _num(df["indice_adaptacao_climatica"])
    if name == "fragilidade":
        if "indice_resiliencia" not in df.columns:
            return pd.Series(np.nan, index=idx)
        return (100.0 - _num(df["indice_resiliencia"])).clip(0, 100)
    if name == "alerta":
        if "score_alerta_integrado" in df.columns:
            return (_num(df["score_alerta_integrado"]).clip(0, 4) / 4.0 * 100.0)
        if "nivel_alerta_integrado" in df.columns:
            rank = {"cinza": 0, "verde": 0, "amarela": 1, "laranja": 2, "vermelha": 3, "roxa": 4}
            return df["nivel_alerta_integrado"].astype(str).str.lower().map(rank).fillna(0) / 4.0 * 100.0
        if "score" in df.columns:
            return (_num(df["score"]).clip(0, 4) / 4.0 * 100.0)
        return pd.Series(np.nan, index=idx)
    return pd.Series(np.nan, index=idx)


def _tendencia_row(row: pd.Series) -> str:
    votes = []
    for col in ("tendencia_7d", "tendencia_pressao_7d"):
        v = str(row.get(col, "")).lower().strip()
        if v in {"subindo", "aumento"}:
            votes.append("aumento")
        elif v in {"descendo", "queda"}:
            votes.append("queda")
        elif v in {"estável", "estavel", "manutenção", "manutencao"}:
            votes.append("manutenção")
    # Predição de pressão vs atual
    try:
        atual = float(row.get("indice_pressao_saude"))
        pred = float(row.get("pred_indice_pressao_7d"))
        if not np.isnan(atual) and not np.isnan(pred):
            if pred > atual + 3:
                votes.append("aumento")
            elif pred < atual - 3:
                votes.append("queda")
            else:
                votes.append("manutenção")
    except Exception:
        pass
    if not votes:
        return "—"
    # maioria
    from collections import Counter

    return Counter(votes).most_common(1)[0][0]


def _orientacao(row: pd.Series) -> str:
    faixa = str(row.get("faixa_prioridade_global", "—"))
    score = row.get("indice_prioridade_global")
    tend = str(row.get("tendencia_prioridade_7d", "—"))
    bits = [f"Prioridade global {faixa}"]
    try:
        if pd.notna(score):
            bits[0] += f" ({float(score):.0f}/100)"
    except Exception:
        pass
    if tend in {"aumento", "subindo"}:
        bits.append("tendência de piora em ~7 dias")
    elif tend in {"queda", "descendo"}:
        bits.append("tendência de alívio em ~7 dias")
    elif tend == "manutenção":
        bits.append("manutenção prevista em ~7 dias")
    # Destaca pilar mais alto disponível
    vals = []
    for label, col in (
        ("vigilância", "indice_vigilancia_integrada"),
        ("pressão saúde", "indice_pressao_saude"),
        ("AdaptaSUS", "indice_adaptacao_climatica"),
    ):
        try:
            v = float(row.get(col))
            if not np.isnan(v):
                vals.append((v, label))
        except Exception:
            pass
    if vals:
        vals.sort(reverse=True)
        bits.append(f"pilar em destaque: {vals[0][1]}")
    return ". ".join(bits) + "."


def enrich_prioridade_global(resumo: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta indice_prioridade_global e metadados ao resumo municipal."""
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()

    cfg = _cfg()
    pesos = cfg["pesos"]
    faixas = cfg["faixas"]
    df = resumo.copy()

    pillars = {name: _pillar_series(df, name) for name in pesos}
    score = pd.Series(0.0, index=df.index)
    weight_sum = pd.Series(0.0, index=df.index)
    n_ok = pd.Series(0, index=df.index, dtype=int)
    names_ok = pd.Series([""] * len(df), index=df.index, dtype=object)

    for name, w in pesos.items():
        s = pillars[name]
        ok = s.notna()
        score = score + s.fillna(0) * float(w) * ok.astype(float)
        weight_sum = weight_sum + float(w) * ok.astype(float)
        n_ok = n_ok + ok.astype(int)
        # nomes dos pilares presentes
        add = np.where(ok, name + ";", "")
        names_ok = names_ok + pd.Series(add, index=df.index)

    with np.errstate(invalid="ignore", divide="ignore"):
        prioridade = np.where(weight_sum > 0, score / weight_sum, np.nan)
    df["indice_prioridade_global"] = pd.Series(prioridade, index=df.index).clip(0, 100).round(1)
    df["completude_prioridade_pct"] = (n_ok / max(len(pesos), 1) * 100.0).round(1)
    df["pilares_prioridade"] = names_ok.str.rstrip(";")
    df["faixa_prioridade_global"] = [
        _faixa(v, faixas) for v in df["indice_prioridade_global"]
    ]
    df["tendencia_prioridade_7d"] = [_tendencia_row(r) for _, r in df.iterrows()]
    df["orientacao_prioridade"] = [_orientacao(r) for _, r in df.iterrows()]
    return df


def state_prioridade_summary(resumo: pd.DataFrame) -> dict[str, Any]:
    if resumo is None or resumo.empty or "indice_prioridade_global" not in resumo.columns:
        return {}
    s = _num(resumo["indice_prioridade_global"])
    out: dict[str, Any] = {
        "media": float(s.mean()) if s.notna().any() else None,
        "max": float(s.max()) if s.notna().any() else None,
        "municipios": int(resumo["cod_ibge"].nunique()) if "cod_ibge" in resumo.columns else len(resumo),
    }
    if "faixa_prioridade_global" in resumo.columns:
        vc = resumo["faixa_prioridade_global"].astype(str).value_counts().to_dict()
        out["n_alta_ou_mais"] = int(vc.get("alta", 0) + vc.get("muito alta", 0))
        out["n_muito_alta"] = int(vc.get("muito alta", 0))
        out["distribuicao_faixa"] = vc
    if "tendencia_prioridade_7d" in resumo.columns:
        tc = resumo["tendencia_prioridade_7d"].astype(str).value_counts().to_dict()
        out["tendencia_aumento"] = int(tc.get("aumento", 0))
        out["tendencia_queda"] = int(tc.get("queda", 0))
        out["tendencia_manutencao"] = int(tc.get("manutenção", 0))
    if "completude_prioridade_pct" in resumo.columns:
        c = _num(resumo["completude_prioridade_pct"])
        out["completude_media"] = float(c.mean()) if c.notna().any() else None
    return out
