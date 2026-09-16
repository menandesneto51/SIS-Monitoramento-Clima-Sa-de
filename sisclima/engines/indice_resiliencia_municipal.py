# -*- coding: utf-8 -*-
"""Índice de Resiliência Municipal (IRM) — capacidade CNES 0–100.

Alta IRM = melhor capacidade assistencial (produto Sala/boletim).
No RIT entra o inverso como domínio ``rede`` (fragilidade), ver rit_multirisco.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

IRM_COLS = [
    "indice_resiliencia_municipal_0_100",
    "irm_faixa",
    "irm_completude_pct",
    "irm_comp_estab",
    "irm_comp_leitos",
    "irm_comp_profissionais",
    "irm_comp_eab",
    "irm_comp_nebulizacao",
]

# Pesos v1 (soma = 1)
_PESOS = {
    "estab": 0.25,
    "leitos": 0.25,
    "profissionais": 0.20,
    "eab": 0.15,
    "nebulizacao": 0.15,
}

_MIN_COMPLETUDE = 40.0  # abaixo disso IRM = nulo


def _num(s: Any) -> pd.Series:
    if isinstance(s, pd.Series):
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(pd.Series(s), errors="coerce")


def _faixa_capacidade(score: float | None) -> str:
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "—"
    x = float(score)
    if x < 25:
        return "baixa"
    if x < 50:
        return "moderada"
    if x < 70:
        return "adequada"
    if x < 85:
        return "alta"
    return "muito_alta"


def _densidade_10k(qtd: pd.Series, pop: pd.Series) -> pd.Series:
    q = _num(qtd)
    p = _num(pop)
    out = pd.Series(np.nan, index=q.index, dtype="float64")
    ok = p.notna() & (p > 0) & q.notna()
    out.loc[ok] = q.loc[ok] / p.loc[ok] * 10_000.0
    return out


def _score_clip(dens: pd.Series, teto: float) -> pd.Series:
    """Mapeia densidade → 0–100 com teto operacional."""
    d = _num(dens)
    if teto <= 0:
        return pd.Series(np.nan, index=d.index)
    return (d.clip(lower=0, upper=teto) / float(teto) * 100.0).where(d.notna())


def _score_nebul(neb: pd.Series, pop: pd.Series) -> pd.Series:
    """Presença + densidade leve de nebulizadores."""
    n = _num(neb)
    dens = _densidade_10k(n.fillna(0), pop)
    # presença conta 60; densidade até ~2/10k completa 40
    base = pd.Series(np.nan, index=n.index, dtype="float64")
    known = n.notna()
    base.loc[known] = np.where(n.loc[known] > 0, 60.0, 0.0)
    dens_sc = dens.clip(0, 2.0) / 2.0 * 40.0
    out = base.copy()
    out.loc[known] = (base.loc[known].fillna(0) + dens_sc.loc[known].fillna(0)).clip(0, 100)
    return out


def enrich_indice_resiliencia(resumo: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta IRM e componentes no resumo municipal."""
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()
    out = resumo.copy()
    n = len(out)

    # População: coluna principal; se vazia, completa pelo catálogo IBGE MT (142).
    if "populacao" not in out.columns:
        out["populacao"] = np.nan
    pop = _num(out["populacao"])
    if pop.isna().any() and "cod_ibge" in out.columns:
        try:
            from sisclima.ingestion.ibge_municipios import catalogo_municipios_mt

            cat = catalogo_municipios_mt()
            if cat is not None and not cat.empty and "populacao" in cat.columns:
                cat = cat.copy()
                cat["cod_ibge"] = (
                    cat["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.extract(r"(\d+)", expand=False).str.zfill(7)
                )
                pop_map = (
                    cat.dropna(subset=["cod_ibge"])
                    .drop_duplicates("cod_ibge")
                    .set_index("cod_ibge")["populacao"]
                )
                keys = (
                    out["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.extract(r"(\d+)", expand=False).str.zfill(7)
                )
                filled = keys.map(pop_map)
                miss = pop.isna() & filled.notna()
                out.loc[miss, "populacao"] = pd.to_numeric(filled.loc[miss], errors="coerce")
                pop = _num(out["populacao"])
        except Exception:
            pass

    # Estabelecimentos /10k — se per_10k nulo, recalcula a partir de totais CNES
    dens_e = _num(out["cnes_estab_per_10k"]) if "cnes_estab_per_10k" in out.columns else pd.Series(np.nan, index=out.index)
    if dens_e.isna().any():
        estab = out.get("cnes_estabelecimentos_total")
        if estab is None or _num(estab).isna().all():
            estab = out.get("cnes_estabelecimentos_com_profissional")
        dens_fb = _densidade_10k(estab if estab is not None else pd.Series(np.nan, index=out.index), pop)
        dens_e = dens_e.fillna(dens_fb)
    comp_e = _score_clip(dens_e, teto=8.0)

    # Leitos /10k — fallback CNES → IndicaSUS (leitos_total / leitos_sus)
    dens_l = _num(out["cnes_leitos_per_10k"]) if "cnes_leitos_per_10k" in out.columns else pd.Series(np.nan, index=out.index)
    if dens_l.isna().any():
        leitos = out.get("cnes_leitos_total")
        if leitos is None or _num(leitos).isna().all():
            leitos = out.get("leitos_total")
        if leitos is None or _num(leitos).isna().all():
            leitos = out.get("leitos_sus")
        dens_fb = _densidade_10k(leitos if leitos is not None else pd.Series(np.nan, index=out.index), pop)
        dens_l = dens_l.fillna(dens_fb)
    comp_l = _score_clip(dens_l, teto=25.0)

    # Profissionais /10k
    prof_col = "cnes_profissionais_qtd" if "cnes_profissionais_qtd" in out.columns else "cnes_profissionais_total"
    dens_p = _densidade_10k(out.get(prof_col, pd.Series(np.nan, index=out.index)), pop)
    comp_p = _score_clip(dens_p, teto=80.0)

    # Equipes eAB /10k
    dens_a = _densidade_10k(out.get("cnes_equipes_ab_qtd", pd.Series(np.nan, index=out.index)), pop)
    comp_a = _score_clip(dens_a, teto=4.0)

    # Nebulização
    comp_n = _score_nebul(out.get("equipamentos_nebulizacao", pd.Series(np.nan, index=out.index)), pop)

    comps = {
        "estab": comp_e,
        "leitos": comp_l,
        "profissionais": comp_p,
        "eab": comp_a,
        "nebulizacao": comp_n,
    }

    irm = []
    faixa = []
    completude = []
    for i in range(n):
        vals: list[tuple[str, float]] = []
        for key, series in comps.items():
            v = series.iloc[i] if i < len(series) else np.nan
            if pd.notna(v):
                vals.append((key, float(v)))
        pct = 100.0 * len(vals) / float(len(_PESOS)) if _PESOS else 0.0
        completude.append(round(pct, 1))
        if pct < _MIN_COMPLETUDE or not vals:
            # Fallback legado: índice de resiliência operacional já calculado
            legacy = np.nan
            if "indice_resiliencia" in out.columns:
                legacy = pd.to_numeric(out["indice_resiliencia"].iloc[i], errors="coerce")
            if pd.notna(legacy):
                score = float(legacy)
                irm.append(round(score, 1))
                faixa.append(_faixa_capacidade(score))
            else:
                irm.append(np.nan)
                faixa.append("—")
            continue
        # Renormaliza pesos só sobre componentes válidos
        w_sum = sum(_PESOS[k] for k, _ in vals)
        score = sum(_PESOS[k] * v for k, v in vals) / w_sum if w_sum > 0 else np.nan
        irm.append(round(float(score), 1) if pd.notna(score) else np.nan)
        faixa.append(_faixa_capacidade(score))

    out["irm_comp_estab"] = comp_e.round(1)
    out["irm_comp_leitos"] = comp_l.round(1)
    out["irm_comp_profissionais"] = comp_p.round(1)
    out["irm_comp_eab"] = comp_a.round(1)
    out["irm_comp_nebulizacao"] = comp_n.round(1)
    out["irm_completude_pct"] = completude
    out["indice_resiliencia_municipal_0_100"] = irm
    out["irm_faixa"] = faixa
    return out


def fragilidade_rede_from_irm(irm: float | None) -> float | None:
    """Converte capacidade IRM → escore de fragilidade 0–100 para o RIT."""
    if irm is None or (isinstance(irm, float) and np.isnan(irm)):
        return None
    return float(np.clip(100.0 - float(irm), 0.0, 100.0))
