# -*- coding: utf-8 -*-
"""Indicadores SIVEP-Gripe / SRAG alinhados ao Ministério da Saúde.

Referências principais:
- Guia de Vigilância Integrada da covid-19, influenza e outros vírus respiratórios (MS/SVSA, 2024)
- Caderno de Análise de Indicadores da vigilância sentinela (MS, 2024; metas OMS)
- Nota Técnica Conjunta nº 01/257/2025 SVSA/SAPS/SAES/MS
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.engines.epidemiology import (
    _as_series,
    _dedup_columns,
    _filter_mt,
    _group_keys,
    _is_empty,
    _municipality_key,
    _normalize_cod_ibge,
    _standard_keys,
    _strip_accents,
    _to_number,
    _to_text,
    zscore_series,
)
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

CATALOG_PATH = ROOT / "config" / "indicadores_ms_sivep.yaml"


def load_ms_sivep_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {}
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def catalog_as_dataframe() -> pd.DataFrame:
    cat = load_ms_sivep_catalog()
    rows = cat.get("indicadores") or []
    return pd.DataFrame(rows)


def _epi_week(dates: pd.Series) -> pd.DataFrame:
    dt = pd.to_datetime(dates, errors="coerce")
    iso = dt.dt.isocalendar()
    out = pd.DataFrame({"ano_epi": iso.year.astype("Int64"), "semana_epi": iso.week.astype("Int64")}, index=dates.index)
    out["se_label"] = out.apply(
        lambda r: f"{int(r['ano_epi'])}-W{int(r['semana_epi']):02d}" if pd.notna(r["ano_epi"]) and pd.notna(r["semana_epi"]) else "",
        axis=1,
    )
    return out


def _classify_quality(pct: float, meta: float = 80.0) -> str:
    if pd.isna(pct):
        return "sem_dado"
    v = float(pct)
    if v <= 0:
        return "silencioso"
    if v < 21:
        return "baixissimo"
    if v < meta:
        return "baixo"
    return "meta_atingida"


def _normalize_virus(series: pd.Series) -> pd.Series:
    t = _strip_accents(_to_text(series)).str.lower()
    out = pd.Series(["nao_informado"] * len(series), index=series.index, dtype=object)
    out = out.mask(t.eq("") | t.isin(["nan", "none", "na", "ignorado", "ignorada", "nao realizado", "não realizado"]), "nao_informado")
    out = out.mask(t.str.contains("influenza a|flu a|h1n1|h3n2", na=False), "Influenza A")
    out = out.mask(t.str.contains("influenza b|flu b", na=False), "Influenza B")
    out = out.mask(t.str.contains("influenza", na=False) & ~t.str.contains("influenza a|influenza b", na=False), "Influenza")
    out = out.mask(t.str.contains("sars|covid|cov-2|coronavirus", na=False), "SARS-CoV-2")
    out = out.mask(t.str.contains("vsr|sincicial|rsv", na=False), "VSR")
    out = out.mask(t.str.contains("adenovirus|adeno", na=False), "Adenovirus")
    out = out.mask(t.str.contains("parainfluenza", na=False), "Parainfluenza")
    out = out.mask(t.str.contains("rinovirus|rhino", na=False), "Rinovirus")
    # mantém original limpo se ainda nao_informado e texto existia
    mask_keep = out.eq("nao_informado") & t.ne("") & ~t.isin(["nan", "none"])
    out = out.mask(mask_keep, _to_text(series).where(mask_keep, out))
    return out


def _prepare_case_level(df: pd.DataFrame) -> pd.DataFrame:
    if _is_empty(df):
        return pd.DataFrame()

    out = _dedup_columns(df)
    keys = _standard_keys(
        out,
        date_candidates=[
            "data_sintomas",
            "dt_sin_pri",
            "data_primeiros_sintomas",
            "data",
            "data_notificacao",
            "dt_notific",
            "data_internacao",
            "DT_SIN_PRI",
            "DT_NOTIFIC",
        ],
        cod_candidates=["cod_ibge", "cod_ibge_residencia", "cod_mun_res", "CO_MUN_RES", "co_mun_res"],
        municipio_candidates=["municipio", "municipio_residencia", "mun_res", "MunicipioResidencia"],
    )
    cases = keys.copy()
    src = out.loc[keys.index].copy()

    # datas auxiliares
    notif = _as_series(src, ["data_notificacao", "dt_notific", "DT_NOTIFIC", "data"], "")
    sint = _as_series(src, ["data_sintomas", "dt_sin_pri", "data_primeiros_sintomas", "DT_SIN_PRI"], "")
    cases["data_notificacao"] = pd.to_datetime(notif, errors="coerce")
    cases["data_sintomas"] = pd.to_datetime(sint, errors="coerce")
    # SE preferencialmente por início de sintomas (MS)
    ref_date = cases["data_sintomas"].fillna(pd.to_datetime(cases["data"], errors="coerce"))
    cases["data"] = ref_date.dt.date.astype(str).replace({"NaT": "", "nan": ""})
    epi = _epi_week(ref_date)
    cases = pd.concat([cases, epi], axis=1)

    uti = _to_number(_as_series(src, ["uti", "foi_internado_uti", "FoiInternadoEmUTI", "UTI", "internacao_uti"], 0), 0)
    cases["uti"] = (uti > 0).astype(int)

    if "obito" in src.columns:
        obito = _to_number(src["obito"], 0)
    else:
        evol = _strip_accents(_as_series(src, ["evolucao", "EvolucaoClinica", "EVOLUCAO"], "")).str.lower()
        obito = evol.str.contains("obito", na=False).astype(int)
    cases["obito"] = (obito > 0).astype(int)

    virus_raw = _as_series(
        src,
        ["virus", "etiologia", "agente", "pcr_resul", "PCR_RESUL", "an_sars2", "classifi_vinrus", "resultado_lab"],
        "",
    )
    cases["virus"] = _normalize_virus(virus_raw)
    cases["tem_etiologia"] = (~cases["virus"].isin(["nao_informado", ""])).astype(int)

    vent = _as_series(src, ["suporte_ventilatorio", "SUPORT_VEN", "suporte_ven", "ventilatorio"], "")
    vent_n = _to_number(vent, np.nan)
    vent_t = _strip_accents(_to_text(vent)).str.lower()
    cases["suporte_ventilatorio"] = np.where(
        vent_n.notna(),
        (vent_n > 0).astype(int),
        vent_t.str.contains("sim|invasiv|nao invasiv|sim", na=False).astype(int),
    )

    atraso = (cases["data_notificacao"] - cases["data_sintomas"]).dt.days
    cases["atraso_notif_dias"] = atraso.where(atraso >= 0)

    classif = _as_series(src, ["classificacao_final", "CLASSI_FIN", "classi_fin"], "")
    cases["classificacao_final"] = _to_text(classif)

    cases = _filter_mt(cases)
    return cases


def _attach_population(df: pd.DataFrame, populacao: pd.DataFrame | None) -> pd.DataFrame:
    out = df.copy()
    if populacao is None or populacao.empty or "cod_ibge" not in out.columns:
        out["populacao"] = np.nan
        return out
    pop = _dedup_columns(populacao).copy()
    if "cod_ibge" not in pop.columns:
        out["populacao"] = np.nan
        return out
    pop["cod_ibge"] = _normalize_cod_ibge(pop["cod_ibge"])
    pop_col = next((c for c in ["populacao_2025", "populacao", "pop", "populacao_estimada"] if c in pop.columns), None)
    if not pop_col:
        out["populacao"] = np.nan
        return out
    pop_u = pop[["cod_ibge", pop_col]].drop_duplicates("cod_ibge").rename(columns={pop_col: "populacao"})
    pop_u["populacao"] = _to_number(pop_u["populacao"], 0)
    out["cod_ibge"] = _normalize_cod_ibge(out["cod_ibge"])
    out = out.merge(pop_u, on="cod_ibge", how="left")
    return out


def sivep_ms_daily_summary(df: pd.DataFrame, populacao: pd.DataFrame | None = None) -> pd.DataFrame:
    """Resumo diário municipal com indicadores MS (substitui/amplia epi_sivep_srag)."""
    columns = [
        "data",
        "cod_ibge",
        "municipio",
        "casos_srag",
        "uti",
        "obitos",
        "letalidade_pct",
        "prop_uti_pct",
        "positividade_viral_pct",
        "cobertura_lab_pct",
        "suporte_ventilatorio",
        "prop_ventilatorio_pct",
        "atraso_notif_mediano_dias",
        "incidencia_srag_100k",
        "zscore_srag",
        "virus_dominante",
        "populacao",
    ]
    cases = _prepare_case_level(df)
    if cases.empty:
        return pd.DataFrame(columns=columns)

    gkeys = _group_keys(cases)
    g = cases.groupby(gkeys, as_index=False).agg(
        casos_srag=("data", "size"),
        uti=("uti", "sum"),
        obitos=("obito", "sum"),
        suporte_ventilatorio=("suporte_ventilatorio", "sum"),
        com_etiologia=("tem_etiologia", "sum"),
        atraso_notif_mediano_dias=("atraso_notif_dias", "median"),
    )
    # vírus dominante do dia
    vir = (
        cases[cases["tem_etiologia"] == 1]
        .groupby(gkeys + ["virus"], as_index=False)
        .size()
        .rename(columns={"size": "n"})
    )
    if not vir.empty:
        vir = vir.sort_values(gkeys + ["n"], ascending=[True] * len(gkeys) + [False])
        vir = vir.drop_duplicates(gkeys, keep="first")[gkeys + ["virus"]].rename(columns={"virus": "virus_dominante"})
        g = g.merge(vir, on=gkeys, how="left")
    else:
        g["virus_dominante"] = ""

    g["letalidade_pct"] = np.where(g["casos_srag"] > 0, g["obitos"] / g["casos_srag"] * 100, 0.0)
    g["prop_uti_pct"] = np.where(g["casos_srag"] > 0, g["uti"] / g["casos_srag"] * 100, 0.0)
    g["prop_ventilatorio_pct"] = np.where(g["casos_srag"] > 0, g["suporte_ventilatorio"] / g["casos_srag"] * 100, 0.0)
    g["cobertura_lab_pct"] = np.where(g["casos_srag"] > 0, g["com_etiologia"] / g["casos_srag"] * 100, 0.0)
    g["positividade_viral_pct"] = g["cobertura_lab_pct"]  # em bases sem denominador de testados = cobertura com vírus ID

    g = _attach_population(g, populacao)
    g["incidencia_srag_100k"] = np.where(
        _to_number(g["populacao"], 0) > 0,
        g["casos_srag"] / _to_number(g["populacao"], 0) * 100_000,
        np.nan,
    )

    mcols = _municipality_key(g)
    if mcols:
        g = g.sort_values(mcols + ["data"])
        g["zscore_srag"] = g.groupby(mcols, group_keys=False)["casos_srag"].transform(lambda s: zscore_series(s).fillna(0))
    else:
        g["zscore_srag"] = zscore_series(g["casos_srag"]).fillna(0)

    for c in columns:
        if c not in g.columns:
            g[c] = np.nan if c not in ["data", "cod_ibge", "municipio", "virus_dominante"] else ""
    return g[columns]


def sivep_ms_weekly_summary(df: pd.DataFrame, populacao: pd.DataFrame | None = None) -> pd.DataFrame:
    """Curva epidêmica por SE (SRAG-01/02/03/04/11)."""
    cases = _prepare_case_level(df)
    if cases.empty:
        return pd.DataFrame()

    cases = cases[cases["se_label"].astype(str).ne("")].copy()
    keys = [c for c in ["cod_ibge", "municipio", "ano_epi", "semana_epi", "se_label"] if c in cases.columns]
    g = cases.groupby(keys, as_index=False).agg(
        casos_srag=("data", "size"),
        uti=("uti", "sum"),
        obitos=("obito", "sum"),
        com_etiologia=("tem_etiologia", "sum"),
        atraso_notif_mediano_dias=("atraso_notif_dias", "median"),
    )
    g["letalidade_pct"] = np.where(g["casos_srag"] > 0, g["obitos"] / g["casos_srag"] * 100, 0.0)
    g["prop_uti_pct"] = np.where(g["casos_srag"] > 0, g["uti"] / g["casos_srag"] * 100, 0.0)
    g["cobertura_lab_pct"] = np.where(g["casos_srag"] > 0, g["com_etiologia"] / g["casos_srag"] * 100, 0.0)
    g = _attach_population(g, populacao)
    g["incidencia_srag_100k"] = np.where(
        _to_number(g["populacao"], 0) > 0,
        g["casos_srag"] / _to_number(g["populacao"], 0) * 100_000,
        np.nan,
    )
    mcols = [c for c in ["cod_ibge", "municipio"] if c in g.columns]
    if mcols:
        g = g.sort_values(mcols + ["ano_epi", "semana_epi"])
        g["zscore_srag"] = g.groupby(mcols, group_keys=False)["casos_srag"].transform(lambda s: zscore_series(s, window=12).fillna(0))
    return g


def sivep_ms_virus_by_week(df: pd.DataFrame) -> pd.DataFrame:
    """Distribuição viral por SE (SRAG-06)."""
    cases = _prepare_case_level(df)
    if cases.empty:
        return pd.DataFrame()
    cases = cases[cases["se_label"].astype(str).ne("")].copy()
    keys = [c for c in ["cod_ibge", "municipio", "ano_epi", "semana_epi", "se_label", "virus"] if c in cases.columns]
    g = cases.groupby(keys, as_index=False).size().rename(columns={"size": "casos"})
    return g.sort_values([c for c in ["ano_epi", "semana_epi", "casos"] if c in g.columns], ascending=[True, True, False][: len([c for c in ["ano_epi", "semana_epi", "casos"] if c in g.columns])])


def sivep_ms_quality_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Indicadores de qualidade municipais (SRAG-07/08/12) — snapshot do período carregado."""
    cases = _prepare_case_level(df)
    if cases.empty:
        return pd.DataFrame()
    cat = load_ms_sivep_catalog()
    meta = float(cat.get("meta_qualidade_oms_pct", 80) or 80)
    keys = [c for c in ["cod_ibge", "municipio"] if c in cases.columns]
    g = cases.groupby(keys, as_index=False).agg(
        casos_srag=("data", "size"),
        com_etiologia=("tem_etiologia", "sum"),
        uti=("uti", "sum"),
        obitos=("obito", "sum"),
        atraso_notif_mediano_dias=("atraso_notif_dias", "median"),
    )
    g["cobertura_lab_pct"] = np.where(g["casos_srag"] > 0, g["com_etiologia"] / g["casos_srag"] * 100, 0.0)
    g["prop_uti_pct"] = np.where(g["casos_srag"] > 0, g["uti"] / g["casos_srag"] * 100, 0.0)
    g["letalidade_pct"] = np.where(g["casos_srag"] > 0, g["obitos"] / g["casos_srag"] * 100, 0.0)
    g["classificacao_qualidade_lab"] = g["cobertura_lab_pct"].apply(lambda x: _classify_quality(x, meta))
    g["meta_qualidade_pct"] = meta
    g["indicador_id"] = "SRAG-07/08/12"
    return g


def sivep_ms_indicator_panel(df: pd.DataFrame, populacao: pd.DataFrame | None = None) -> pd.DataFrame:
    """Painel longo: um registro por município × indicador MS (última SE)."""
    weekly = sivep_ms_weekly_summary(df, populacao)
    quality = sivep_ms_quality_indicators(df)
    catalog = catalog_as_dataframe()
    rows: list[dict] = []

    if not weekly.empty:
        mcols = [c for c in ["cod_ibge", "municipio"] if c in weekly.columns]
        latest = weekly.sort_values(["ano_epi", "semana_epi"]).groupby(mcols, as_index=False).tail(1) if mcols else weekly.tail(1)
        mapping = {
            "SRAG-01": ("casos_srag", "casos"),
            "SRAG-02": ("incidencia_srag_100k", "por 100 mil"),
            "SRAG-03": ("letalidade_pct", "%"),
            "SRAG-04": ("prop_uti_pct", "%"),
            "SRAG-07": ("cobertura_lab_pct", "%"),
            "SRAG-08": ("atraso_notif_mediano_dias", "dias"),
            "SRAG-10": ("zscore_srag", "z-score"),
        }
        name_by_id = {r["id"]: r.get("nome", r["id"]) for _, r in catalog.iterrows()} if not catalog.empty else {}
        for _, r in latest.iterrows():
            for iid, (col, unit) in mapping.items():
                if col not in latest.columns:
                    continue
                rows.append(
                    {
                        "indicador_id": iid,
                        "indicador_nome": name_by_id.get(iid, iid),
                        "cod_ibge": r.get("cod_ibge"),
                        "municipio": r.get("municipio"),
                        "se_label": r.get("se_label"),
                        "valor": r.get(col),
                        "unidade": unit,
                        "fonte": "SIVEP-Gripe / MS",
                    }
                )

    if not quality.empty:
        for _, r in quality.iterrows():
            rows.append(
                {
                    "indicador_id": "SRAG-12",
                    "indicador_nome": "Classificação de desempenho da qualidade laboratorial",
                    "cod_ibge": r.get("cod_ibge"),
                    "municipio": r.get("municipio"),
                    "se_label": "",
                    "valor": r.get("cobertura_lab_pct"),
                    "unidade": "%",
                    "classificacao": r.get("classificacao_qualidade_lab"),
                    "fonte": "SIVEP-Gripe / MS",
                }
            )

    return pd.DataFrame(rows)


def compute_all_sivep_ms_outputs(
    df: pd.DataFrame,
    populacao: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Calcula todos os artefatos de indicadores MS/SIVEP."""
    daily = sivep_ms_daily_summary(df, populacao)
    return {
        "epi_sivep_srag": daily,
        "epi_sivep_se_municipal": sivep_ms_weekly_summary(df, populacao),
        "epi_sivep_virus_se": sivep_ms_virus_by_week(df),
        "epi_sivep_qualidade_ms": sivep_ms_quality_indicators(df),
        "epi_sivep_indicadores_ms": sivep_ms_indicator_panel(df, populacao),
        "dicionario_indicadores_ms_sivep": catalog_as_dataframe(),
    }
