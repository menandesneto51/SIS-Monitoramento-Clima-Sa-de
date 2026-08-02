# -*- coding: utf-8 -*-
"""Motor de inteligência alinhado ao AdaptaSUS / Guia MS.

Calcula scores 0–100 por risco prioritário a partir do resumo municipal,
orientações SOP e índice de adaptação climática.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from sisclima.core.config import ROOT

RISK_IDS = [
    "temperatura_extrema",
    "poluicao_ar",
    "vetoriais_zoonoses",
    "precipitacao_extrema",
    "wash",
    "san",
]

_CFG_CACHE: dict[str, Any] | None = None


def load_adaptasus_config() -> dict[str, Any]:
    global _CFG_CACHE
    if _CFG_CACHE is not None:
        return _CFG_CACHE
    path = ROOT / "config" / "adaptasus_riscos.yaml"
    if not path.exists():
        path = Path("config/adaptasus_riscos.yaml")
    with open(path, encoding="utf-8") as f:
        _CFG_CACHE = yaml.safe_load(f) or {}
    return _CFG_CACHE


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _clip01(s: pd.Series) -> pd.Series:
    return _num(s).clip(lower=0, upper=1).fillna(0)


def _score_temperatura(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Retorna (score 0-100, cobertura 0-1)."""
    parts = []
    if "utci_proxy" in df.columns:
        parts.append(_clip01((_num(df["utci_proxy"]) - 26.0) / 16.0))
    if "risco_cumulativo_3d" in df.columns:
        parts.append(_clip01(_num(df["risco_cumulativo_3d"]) / 15.0))
    if "tmax" in df.columns:
        parts.append(_clip01((_num(df["tmax"]) - 30.0) / 12.0))
    if "onda_calor_p95_2d" in df.columns:
        parts.append(_clip01(_num(df["onda_calor_p95_2d"])))
    # Frio (quando tmin disponível)
    frio = pd.Series(0.0, index=df.index)
    if "tmin" in df.columns:
        frio = _clip01((12.0 - _num(df["tmin"])) / 12.0)
        parts.append(frio * 0.35)
    if not parts:
        return pd.Series(np.nan, index=df.index), pd.Series(0.0, index=df.index)
    score = sum(p for p in parts) / len(parts) * 100.0
    cov = pd.Series(1.0 if len(parts) >= 2 else 0.5, index=df.index)
    return score.clip(0, 100), cov


def _score_poluicao(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    has_pm = "pm25_ugm3" in df.columns or "iq_ar_score" in df.columns
    has_focos = "focos_queimadas_7d" in df.columns
    if not has_pm and not has_focos:
        return pd.Series(np.nan, index=df.index), pd.Series(0.0, index=df.index)
    pm = _clip01(_num(df["pm25_ugm3"]) / 75.0) if "pm25_ugm3" in df.columns else pd.Series(0.0, index=df.index)
    iq = _clip01(_num(df["iq_ar_score"]) / 100.0) if "iq_ar_score" in df.columns else pd.Series(0.0, index=df.index)
    focos = (
        _clip01(_num(df["focos_queimadas_7d"]) / 80.0)
        if has_focos
        else pd.Series(0.0, index=df.index)
    )
    # Seca amplifica queimadas
    seca = pd.Series(0.0, index=df.index)
    if "precipitacao_mm" in df.columns:
        seca = _clip01((5.0 - _num(df["precipitacao_mm"])) / 5.0)
    if "dias_sem_chuva_max" in df.columns:
        seca = np.maximum(seca, _clip01(_num(df["dias_sem_chuva_max"]) / 30.0))
    score = (pm * 0.40 + iq * 0.15 + focos * 0.30 + seca * 0.15) * 100.0
    has = (
        (_num(df["pm25_ugm3"]).notna() if "pm25_ugm3" in df.columns else pd.Series(False, index=df.index))
        | (_num(df["focos_queimadas_7d"]).fillna(0) > 0 if has_focos else pd.Series(False, index=df.index))
    )
    cov = has.astype(float)
    score = score.where(has, np.nan)
    return score.clip(0, 100), cov


def _score_vetorial(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if "casos_arbovirus_7d" not in df.columns and "zscore_arbovirus" not in df.columns:
        return pd.Series(np.nan, index=df.index), pd.Series(0.0, index=df.index)
    casos = _clip01(_num(df["casos_arbovirus_7d"]) / 30.0) if "casos_arbovirus_7d" in df.columns else pd.Series(0.0, index=df.index)
    z = _clip01(_num(df["zscore_arbovirus"]) / 4.0) if "zscore_arbovirus" in df.columns else pd.Series(0.0, index=df.index)
    clima = pd.Series(0.0, index=df.index)
    if "tmax" in df.columns:
        clima = clima + _clip01((_num(df["tmax"]) - 28.0) / 10.0) * 0.5
    if "precipitacao_mm" in df.columns:
        # chuva moderada favorece vetor (pico ~10–40 mm)
        precip = _num(df["precipitacao_mm"])
        clima = clima + _clip01(1.0 - (precip - 25.0).abs() / 40.0) * 0.5
    score = (casos * 0.45 + z * 0.30 + clima * 0.25) * 100.0
    has = (
        _num(df["casos_arbovirus_7d"]).notna()
        if "casos_arbovirus_7d" in df.columns
        else pd.Series(False, index=df.index)
    )
    cov = has.astype(float).where(has, 0.3)
    return score.clip(0, 100), cov.clip(0, 1)


def _score_precipitacao(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    if "precipitacao_mm" not in df.columns and "nivel_chuva" not in df.columns:
        return pd.Series(np.nan, index=df.index), pd.Series(0.0, index=df.index)
    precip = _num(df["precipitacao_mm"]) if "precipitacao_mm" in df.columns else pd.Series(np.nan, index=df.index)
    inund = _clip01(precip / 80.0)
    # Seca: só eleva quando há sinal climático de estiagem (baixa umidade / alta tmax),
    # evitando 100% só porque o dia teve 0 mm de chuva.
    seca = _clip01((1.0 - precip.clip(lower=0) / 5.0))
    if "umidade_media" in df.columns:
        seca = seca * _clip01((50.0 - _num(df["umidade_media"])) / 35.0)
    else:
        seca = seca * 0.35
    if "tmax" in df.columns:
        seca = seca * (0.5 + 0.5 * _clip01((_num(df["tmax"]) - 32.0) / 8.0))
    score = np.maximum(inund.to_numpy(dtype=float), seca.to_numpy(dtype=float)) * 100.0
    score = pd.Series(score, index=df.index)
    if "nivel_chuva" in df.columns:
        nivel = df["nivel_chuva"].astype(str).str.lower()
        boost = nivel.isin(["alto", "muito alto", "alerta", "vermelho", "laranja"]).astype(float) * 15.0
        score = (score + boost).clip(0, 100)
    cov = precip.notna().astype(float) if "precipitacao_mm" in df.columns else pd.Series(0.4, index=df.index)
    return score, cov


def _score_ausente(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    return pd.Series(np.nan, index=df.index), pd.Series(0.0, index=df.index)


def _score_wash(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Risco WASH 0–100 a partir do déficit domiciliar IBGE (+ amplificação por estiagem)."""
    base = None
    if "indice_deficit_wash" in df.columns:
        base = _num(df["indice_deficit_wash"])
    else:
        parts = []
        if "deficit_rede_agua_pct" in df.columns:
            parts.append(_num(df["deficit_rede_agua_pct"]))
        if "deficit_esgoto_inadequado_pct" in df.columns:
            parts.append(_num(df["deficit_esgoto_inadequado_pct"]))
        if "deficit_agua_canalizada_pct" in df.columns:
            parts.append(_num(df["deficit_agua_canalizada_pct"]))
        if parts:
            mat = np.column_stack([p.fillna(np.nan).to_numpy(dtype=float) for p in parts])
            base = pd.Series(np.nanmean(mat, axis=1), index=df.index)
    if base is None:
        return pd.Series(np.nan, index=df.index), pd.Series(0.0, index=df.index)

    score = base.clip(0, 100)
    # Estiagem / baixa umidade amplifica déficit de água (não inventa risco sem dado WASH)
    amp = pd.Series(0.0, index=df.index)
    if "precipitacao_mm" in df.columns:
        amp = np.maximum(amp, _clip01((3.0 - _num(df["precipitacao_mm"])) / 3.0) * 0.15)
    if "umidade_media" in df.columns:
        amp = np.maximum(amp, _clip01((40.0 - _num(df["umidade_media"])) / 30.0) * 0.12)
    if "dias_sem_chuva_max" in df.columns:
        amp = np.maximum(amp, _clip01(_num(df["dias_sem_chuva_max"]) / 35.0) * 0.15)
    score = (score * (1.0 + amp)).clip(0, 100)
    cov = base.notna().astype(float)
    score = score.where(base.notna(), np.nan)
    return score, cov


_SCORE_FN = {
    "temperatura_extrema": _score_temperatura,
    "poluicao_ar": _score_poluicao,
    "vetoriais_zoonoses": _score_vetorial,
    "precipitacao_extrema": _score_precipitacao,
    "wash": _score_wash,
    "san": _score_ausente,
}


def _acoes_for_risk(cfg: dict[str, Any], risk_id: str) -> list[str]:
    for r in cfg.get("riscos") or []:
        if r.get("id") == risk_id:
            return list(r.get("acoes_guia") or [])
    return []


def _nome_risco(cfg: dict[str, Any], risk_id: str) -> str:
    for r in cfg.get("riscos") or []:
        if r.get("id") == risk_id:
            return str(r.get("nome") or risk_id)
    return risk_id


def derive_smart_risk_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Derivados inteligentes (sem novas fontes externas)."""
    out = df.copy()
    # calor × proxy demográfico (log população como vulnerabilidade relativa)
    tensao = _num(out["indice_tensao_climatica"]) if "indice_tensao_climatica" in out.columns else _num(out.get("risco_cumulativo_3d", pd.Series(dtype=float))) * 6.0
    if "populacao" in out.columns:
        pop = _num(out["populacao"]).fillna(0)
        vuln = _clip01(np.log1p(pop) / np.log1p(pop.max() if pop.max() > 0 else 1))
    else:
        vuln = pd.Series(0.5, index=out.index)
    out["risco_calor_vulneravel"] = (tensao.fillna(0) * (0.55 + 0.45 * vuln)).clip(0, 100).round(1)

    pm = _clip01(_num(out["pm25_ugm3"]) / 75.0) if "pm25_ugm3" in out.columns else pd.Series(0.0, index=out.index)
    seca = _clip01((5.0 - _num(out["precipitacao_mm"])) / 5.0) if "precipitacao_mm" in out.columns else pd.Series(0.0, index=out.index)
    focos = (
        _clip01(_num(out["focos_queimadas_7d"]) / 80.0)
        if "focos_queimadas_7d" in out.columns
        else pd.Series(0.0, index=out.index)
    )
    has_ar = (
        (_num(out["pm25_ugm3"]).notna() if "pm25_ugm3" in out.columns else pd.Series(False, index=out.index))
        | (_num(out["focos_queimadas_7d"]).fillna(0) > 0 if "focos_queimadas_7d" in out.columns else pd.Series(False, index=out.index))
    )
    out["risco_ar_queimadas"] = ((pm * 0.45 + focos * 0.40 + seca * 0.15) * 100.0).where(
        has_ar,
        np.nan,
    ).clip(0, 100).round(1)

    arbo = _clip01(_num(out["casos_arbovirus_7d"]) / 30.0) if "casos_arbovirus_7d" in out.columns else pd.Series(0.0, index=out.index)
    tmax = _clip01((_num(out["tmax"]) - 28.0) / 10.0) if "tmax" in out.columns else pd.Series(0.0, index=out.index)
    precip = _num(out["precipitacao_mm"]) if "precipitacao_mm" in out.columns else pd.Series(np.nan, index=out.index)
    clima_vet = tmax * 0.5 + _clip01(1.0 - (precip - 25.0).abs() / 40.0).fillna(0) * 0.5
    out["risco_vetorial_climatico"] = ((arbo * 0.6 + clima_vet * 0.4) * 100.0).clip(0, 100).round(1)

    press = _clip01(_num(out["pressao_calor_pct"]) / 12.0) if "pressao_calor_pct" in out.columns else pd.Series(0.0, index=out.index)
    ocup = _clip01(_num(out["ocupacao_leitos_pct"]) / 100.0) if "ocupacao_leitos_pct" in out.columns else pd.Series(0.0, index=out.index)
    tens = _clip01(tensao / 100.0)
    out["pressao_rede_climatica"] = ((press * 0.4 + ocup * 0.35 + tens * 0.25) * 100.0).clip(0, 100).round(1)

    if "precipitacao_mm" in out.columns:
        inund = _clip01(_num(out["precipitacao_mm"]) / 80.0)
        seca2 = _clip01((2.0 - _num(out["precipitacao_mm"])) / 2.0)
        out["risco_precipitacao"] = (np.maximum(inund, seca2) * 100.0).clip(0, 100).round(1)
    return out


def enrich_adaptasus_intelligence(resumo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Retorna:
      - resumo enriquecido (índices + derivados)
      - adaptasus_risco_municipal
      - adaptasus_risco_estado
    """
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    cfg = load_adaptasus_config()
    pesos = cfg.get("pesos_indice_adaptacao") or {}
    df = derive_smart_risk_indicators(resumo)

    scores: dict[str, pd.Series] = {}
    covs: dict[str, pd.Series] = {}
    for rid in RISK_IDS:
        fn = _SCORE_FN[rid]
        sc, cv = fn(df)
        col = f"risco_{rid}"
        df[col] = sc.round(1)
        df[f"cobertura_{rid}"] = cv.round(2)
        scores[rid] = sc
        covs[rid] = cv

    # Índice de adaptação: média ponderada dos riscos *com cobertura*, penalidade por incompletos
    w = np.array([float(pesos.get(rid, 1.0 / len(RISK_IDS))) for rid in RISK_IDS], dtype=float)
    penal = float(pesos.get("penalidade_completude", 0.25))
    mat = np.column_stack([scores[rid].fillna(0).to_numpy(dtype=float) for rid in RISK_IDS])
    cov_mat = np.column_stack([covs[rid].fillna(0).to_numpy(dtype=float) for rid in RISK_IDS])
    # zera peso onde cobertura ~0
    w_eff = w * (cov_mat > 0.05)
    w_sum = w_eff.sum(axis=1)
    w_sum = np.where(w_sum <= 0, 1.0, w_sum)
    indice = (mat * w_eff).sum(axis=1) / w_sum
    completude_riscos = (cov_mat > 0.05).mean(axis=1) * 100.0
    indice = indice * (1.0 - penal * (1.0 - completude_riscos / 100.0))
    df["indice_adaptacao_climatica"] = pd.Series(indice, index=df.index).clip(0, 100).round(1)
    df["completude_riscos_adaptasus_pct"] = pd.Series(completude_riscos, index=df.index).round(1)

    # Risco dominante entre os cobertos
    score_frame = pd.DataFrame({rid: scores[rid] for rid in RISK_IDS})
    for rid in RISK_IDS:
        score_frame.loc[covs[rid] <= 0.05, rid] = np.nan
    dominante = score_frame.idxmax(axis=1, skipna=True)
    df["risco_adaptasus_dominante"] = dominante.fillna("temperatura_extrema")
    df["risco_adaptasus_dominante_nome"] = df["risco_adaptasus_dominante"].map(
        lambda x: _nome_risco(cfg, str(x))
    )
    df["score_risco_dominante"] = [
        float(score_frame.loc[i, d]) if pd.notna(d) and d in score_frame.columns and pd.notna(score_frame.loc[i, d]) else np.nan
        for i, d in zip(df.index, df["risco_adaptasus_dominante"])
    ]

    orientacoes = []
    checklists = []
    for _, row in df.iterrows():
        rid = str(row.get("risco_adaptasus_dominante") or "temperatura_extrema")
        acoes = _acoes_for_risk(cfg, rid)
        nome = _nome_risco(cfg, rid)
        score_d = row.get("score_risco_dominante")
        if pd.isna(score_d):
            orientacoes.append("Dados insuficientes para priorizar risco AdaptaSUS nesta rodada.")
            checklists.append("Verificar completude das fontes clima/saúde.")
        else:
            nivel = "alta" if float(score_d) >= 60 else ("moderada" if float(score_d) >= 35 else "baixa")
            orientacoes.append(
                f"Risco dominante: {nome} (score {float(score_d):.0f} — pressão {nivel}). "
                f"Índice adaptação: {row.get('indice_adaptacao_climatica', '—')}."
            )
            checklists.append(" | ".join(acoes[:3]) if acoes else "Seguir SOP CIEVS e Guia MS.")
    df["orientacao_adaptasus"] = orientacoes
    df["checklist_adaptasus"] = checklists

    # Snapshot municipal
    keep = [
        c for c in [
            "cod_ibge", "municipio", "regional_saude", "nivel", "score",
            "indice_adaptacao_climatica", "completude_riscos_adaptasus_pct",
            "risco_adaptasus_dominante", "risco_adaptasus_dominante_nome", "score_risco_dominante",
            "orientacao_adaptasus", "checklist_adaptasus",
            "risco_calor_vulneravel", "risco_ar_queimadas", "risco_vetorial_climatico",
            "pressao_rede_climatica", "risco_precipitacao",
            "indice_deficit_wash", "cobertura_rede_agua_pct", "deficit_rede_agua_pct",
            "cobertura_esgoto_rede_pct", "deficit_esgoto_inadequado_pct",
        ] + [f"risco_{r}" for r in RISK_IDS] + [f"cobertura_{r}" for r in RISK_IDS]
        if c in df.columns
    ]
    mun = df[keep].copy()
    mun["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    # Estado
    estado_rows = []
    for rid in RISK_IDS:
        col = f"risco_{rid}"
        cov = f"cobertura_{rid}"
        serie = _num(df[col]) if col in df.columns else pd.Series(dtype=float)
        cobertura = float((_num(df[cov]) > 0.05).mean() * 100) if cov in df.columns else 0.0
        estado_rows.append(
            {
                "risco_id": rid,
                "risco_nome": _nome_risco(cfg, rid),
                "municipios_com_dado": int(serie.notna().sum()),
                "cobertura_pct": round(cobertura, 1),
                "score_medio": round(float(serie.mean()), 1) if serie.notna().any() else None,
                "score_max": round(float(serie.max()), 1) if serie.notna().any() else None,
                "status_cobertura": next(
                    (r.get("status_cobertura") for r in (cfg.get("riscos") or []) if r.get("id") == rid),
                    "—",
                ),
            }
        )
    estado = pd.DataFrame(estado_rows)
    estado["indice_adaptacao_media"] = float(_num(df["indice_adaptacao_climatica"]).mean()) if "indice_adaptacao_climatica" in df.columns else None
    estado["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    return df, mun, estado
