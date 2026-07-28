# -*- coding: utf-8 -*-
"""Capacidade operacional CNES via DW (SQL claro) + merge no resumo."""
from __future__ import annotations

import numpy as np
import pandas as pd

from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.dw_sources import load_dw_cnes_estabelecimentos, load_dw_cnes_leitos

log = get_logger(__name__)


def _norm_ibge(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{6,7})", expand=False)


def _agg_leitos(leitos: pd.DataFrame) -> pd.DataFrame:
    l = leitos.copy()
    l["cod_ibge"] = _norm_ibge(l["cod_ibge"]) if "cod_ibge" in l.columns else pd.NA
    for c in ["leitos_existentes", "leitos_sus"]:
        if c in l.columns:
            l[c] = pd.to_numeric(l[c], errors="coerce")
    if "especialidade" in l.columns:
        esp = l["especialidade"].astype(str).str.lower()
        l["flag_uti"] = esp.str.contains("uti|intensiva|uci", regex=True, na=False).astype(int)
    else:
        l["flag_uti"] = 0
    return l.groupby("cod_ibge", as_index=False).agg(
        municipio=("municipio", "first") if "municipio" in l.columns else ("cod_ibge", "first"),
        cnes_leitos_total=("leitos_existentes", "sum") if "leitos_existentes" in l.columns else ("cod_ibge", "size"),
        cnes_leitos_sus=("leitos_sus", "sum") if "leitos_sus" in l.columns else ("cod_ibge", "size"),
        cnes_unidades_leito=("cnes", "nunique") if "cnes" in l.columns else ("cod_ibge", "size"),
        flag_uti=("flag_uti", "max"),
    )


def _agg_estab(estab: pd.DataFrame) -> pd.DataFrame:
    e = estab.copy()
    e["cod_ibge"] = _norm_ibge(e["cod_ibge"]) if "cod_ibge" in e.columns else pd.NA
    if "qtd_estabelecimento" in e.columns:
        e["qtd_estabelecimento"] = pd.to_numeric(e["qtd_estabelecimento"], errors="coerce").fillna(1)
    else:
        e["qtd_estabelecimento"] = 1
    tipo = e["tipo_unidade"].astype(str).str.lower() if "tipo_unidade" in e.columns else pd.Series("", index=e.index)
    e["flag_hospital"] = tipo.str.contains("hospital", na=False).astype(int)
    e["flag_ups"] = tipo.str.contains("ubs|posto|centro de saude|estratégia", regex=True, na=False).astype(int)
    return e.groupby("cod_ibge", as_index=False).agg(
        municipio_estab=("municipio", "first") if "municipio" in e.columns else ("cod_ibge", "first"),
        regional_saude=("regional_saude", "first") if "regional_saude" in e.columns else ("cod_ibge", "first"),
        cnes_estabelecimentos_total=("qtd_estabelecimento", "sum"),
        cnes_cnes_unicos=("cnes", "nunique") if "cnes" in e.columns else ("cod_ibge", "size"),
        flag_hospital=("flag_hospital", "max"),
        flag_ups=("flag_ups", "max"),
    )


def _fallback_local(resumo: pd.DataFrame | None) -> pd.DataFrame:
    """Capacidade a partir de hospital_ocupacao / resumo quando DW CNES falha."""
    log.warning("DW CNES vazio — usando fallback de ocupação/capacidade instalada local")
    base = resumo.copy() if resumo is not None and not resumo.empty else pd.DataFrame()
    try:
        from sisclima.core.db import read_table

        occ = read_table("hospital_ocupacao_municipio")
    except Exception:
        occ = pd.DataFrame()
    if not occ.empty and "cod_ibge" in occ.columns:
        o = occ.copy()
        o["cod_ibge"] = _norm_ibge(o["cod_ibge"])
        rename = {
            "ocupacao_pct": "ocupacao_leitos_pct",
            "leitos_existentes": "cnes_leitos_total",
            "municipio_base": "municipio",
        }
        o = o.rename(columns={k: v for k, v in rename.items() if k in o.columns})
        keep = [c for c in ["cod_ibge", "municipio", "cnes_leitos_total", "ocupacao_leitos_pct", "leitos_ocupados"] if c in o.columns]
        o = o[keep].drop_duplicates("cod_ibge")
        if base.empty:
            base = o
        else:
            base["cod_ibge"] = _norm_ibge(base["cod_ibge"])
            for col in keep:
                if col == "cod_ibge":
                    continue
                if col not in base.columns:
                    base = base.merge(o[["cod_ibge", col]], on="cod_ibge", how="left")
                else:
                    m = base[["cod_ibge"]].merge(o[["cod_ibge", col]], on="cod_ibge", how="left")
                    if col == "municipio":
                        base[col] = base[col].fillna(m[col])
                    else:
                        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(pd.to_numeric(m[col], errors="coerce"))
    if base.empty:
        return pd.DataFrame()
    mun = base.copy()
    mun["cod_ibge"] = _norm_ibge(mun["cod_ibge"])
    if "cnes_estabelecimentos_total" not in mun.columns:
        mun["cnes_estabelecimentos_total"] = np.nan
    if "flag_uti" not in mun.columns:
        mun["flag_uti"] = 0
    mun["fonte"] = "FALLBACK_OCUPACAO_LOCAL"
    return mun


def build_ops_cnes_municipio(resumo: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Agrega CNES leitos + estabelecimentos por município.
    Retorna (ops_cnes_municipio, ops_resumo_operacional_cnes).
    """
    try:
        leitos = load_dw_cnes_leitos()
    except Exception as exc:
        log.warning("DW CNES leitos indisponível: %s", exc)
        leitos = pd.DataFrame()
    try:
        estab = load_dw_cnes_estabelecimentos()
    except Exception as exc:
        log.warning("DW CNES estabelecimentos indisponível: %s", exc)
        estab = pd.DataFrame()

    fonte = "DW_CNES"
    if leitos.empty and estab.empty:
        mun = _fallback_local(resumo)
        if mun.empty:
            return pd.DataFrame(), pd.DataFrame()
        fonte = str(mun.get("fonte", pd.Series(["FALLBACK_OCUPACAO_LOCAL"])).iloc[0])
    else:
        mun = pd.DataFrame()
        if not leitos.empty:
            mun = _agg_leitos(leitos)
        if not estab.empty:
            e0 = _agg_estab(estab)
            mun = mun.merge(e0, on="cod_ibge", how="outer") if not mun.empty else e0
        if mun.empty:
            return pd.DataFrame(), pd.DataFrame()
        if "municipio" not in mun.columns and "municipio_estab" in mun.columns:
            mun["municipio"] = mun["municipio_estab"]
        elif "municipio" in mun.columns and "municipio_estab" in mun.columns:
            mun["municipio"] = mun["municipio"].fillna(mun["municipio_estab"])
        if resumo is not None and not resumo.empty and "cod_ibge" in resumo.columns:
            r = resumo.copy()
            r["cod_ibge"] = _norm_ibge(r["cod_ibge"])
            keep = [
                c
                for c in [
                    "cod_ibge", "populacao", "ocupacao_leitos_pct", "pressao_calor_pct",
                    "nivel", "score", "indice_vulnerabilidade_calor", "regional_saude",
                ]
                if c in r.columns
            ]
            r = r[keep].drop_duplicates("cod_ibge")
            if "regional_saude" in mun.columns and "regional_saude" in r.columns:
                r = r.drop(columns=["regional_saude"])
            mun = mun.merge(r, on="cod_ibge", how="left")

    # População residual (fallback path)
    if resumo is not None and not resumo.empty and "cod_ibge" in resumo.columns and "populacao" not in mun.columns:
        r = resumo.copy()
        r["cod_ibge"] = _norm_ibge(r["cod_ibge"])
        keep = [c for c in ["cod_ibge", "populacao", "pressao_calor_pct", "nivel", "score", "regional_saude"] if c in r.columns]
        mun = mun.merge(r[keep].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")

    pop = pd.to_numeric(mun.get("populacao"), errors="coerce")
    leitos_tot = pd.to_numeric(mun.get("cnes_leitos_total"), errors="coerce").fillna(0)
    estab_tot = pd.to_numeric(mun.get("cnes_estabelecimentos_total"), errors="coerce").fillna(0)
    leitos_10k = np.where(pop.notna() & (pop > 0), leitos_tot / pop * 10_000, np.nan)
    estab_10k = np.where(pop.notna() & (pop > 0), estab_tot / pop * 10_000, np.nan)
    mun["cnes_leitos_per_10k"] = leitos_10k
    mun["cnes_estab_per_10k"] = estab_10k

    score_leitos = pd.Series(leitos_10k, index=mun.index).fillna(0).clip(0, 25) / 25 * 55
    score_estab = pd.Series(estab_10k, index=mun.index).fillna(0).clip(0, 8) / 8 * 30
    score_uti = pd.to_numeric(mun.get("flag_uti"), errors="coerce").fillna(0).clip(0, 1) * 15
    mun["indice_capacidade_cnes"] = (score_leitos + score_estab + score_uti).clip(0, 100).round(1)
    mun["fonte"] = fonte
    mun["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    for col, default in [
        ("cnes_equipamentos_total", np.nan),
        ("cnes_profissionais_total", np.nan),
        ("flag_ventilador", pd.NA),
        ("flag_monitor", pd.NA),
    ]:
        if col not in mun.columns:
            mun[col] = default

    ops = mun.copy()
    ocup = pd.to_numeric(ops.get("ocupacao_leitos_pct"), errors="coerce")
    livres = (100 - ocup).clip(0, 100)
    ops["indice_resiliencia_proxy"] = np.where(
        ocup.notna(),
        (0.5 * ops["indice_capacidade_cnes"] + 0.5 * livres.fillna(0)).round(1),
        ops["indice_capacidade_cnes"],
    )
    ops["prioridade_operacional_proxy"] = (
        (100 - ops["indice_resiliencia_proxy"]).clip(0, 100)
        + pd.to_numeric(ops.get("pressao_calor_pct"), errors="coerce").fillna(0) * 2
    ).round(1)
    return mun, ops
