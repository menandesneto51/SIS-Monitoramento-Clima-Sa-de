# -*- coding: utf-8 -*-
"""Indicadores MS da vigilância sentinela de Síndrome Gripal (SG).

Entradas esperadas (CSV):
- agregado semanal por US/SE: atendimentos_sg, atendimentos_total, amostras_coletadas
- amostras individuais (opcional): definição de caso, preenchimento, RT-PCR, encerramento, vírus, idade
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)
CATALOG_PATH = ROOT / "config" / "indicadores_ms_sentinela_sg.yaml"


def load_sentinela_sg_catalog() -> dict[str, Any]:
    if not CATALOG_PATH.exists():
        return {}
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def catalog_as_dataframe() -> pd.DataFrame:
    return pd.DataFrame(load_sentinela_sg_catalog().get("indicadores") or [])


def _classify(pct: float, meta: float = 80.0) -> str:
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


def _num(s, default=np.nan):
    return pd.to_numeric(s, errors="coerce").fillna(default) if default == default else pd.to_numeric(s, errors="coerce")


def _norm_bool(series: pd.Series) -> pd.Series:
    t = series.astype(str).str.strip().str.lower()
    return t.isin(["1", "true", "sim", "s", "yes", "y"]).astype(int)


def _prepare_agregado(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).lower().strip().replace(" ", "_") for c in out.columns]
    rename = {
        "unidade_sentinela": "unidade_sentinela",
        "us": "unidade_sentinela",
        "nome_us": "unidade_sentinela",
        "semana_epidemiologica": "semana_epi",
        "se": "semana_epi",
        "ano": "ano_epi",
        "ano_epidemiologico": "ano_epi",
        "atendimentos_sg": "atendimentos_sg",
        "atendimento_sg": "atendimentos_sg",
        "atendimentos_totais": "atendimentos_total",
        "atendimentos_geral": "atendimentos_total",
        "atendimentos_gerais": "atendimentos_total",
        "amostras": "amostras_coletadas",
        "amostras_semana": "amostras_coletadas",
        "cod_ibge": "cod_ibge",
        "municipio": "municipio",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    for c in ["atendimentos_sg", "atendimentos_total", "amostras_coletadas", "semana_epi", "ano_epi"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "se_label" not in out.columns and {"ano_epi", "semana_epi"}.issubset(out.columns):
        out["se_label"] = out.apply(
            lambda r: f"{int(r['ano_epi'])}-W{int(r['semana_epi']):02d}"
            if pd.notna(r.get("ano_epi")) and pd.notna(r.get("semana_epi"))
            else "",
            axis=1,
        )
    if "unidade_sentinela" not in out.columns:
        out["unidade_sentinela"] = "US_NAO_INFORMADA"
    return out


def _prepare_amostras(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out.columns = [str(c).lower().strip().replace(" ", "_") for c in out.columns]
    rename = {
        "us": "unidade_sentinela",
        "unidade": "unidade_sentinela",
        "se": "semana_epi",
        "ano": "ano_epi",
        "atende_definicao_sg": "atende_definicao_sg",
        "definicao_caso_ok": "atende_definicao_sg",
        "raca_cor_preenchida": "raca_cor_preenchida",
        "escolaridade_preenchida": "escolaridade_preenchida",
        "antiviral_preenchido": "antiviral_preenchido",
        "rtpcr_processado": "rtpcr_processado",
        "rtpcr_ate_10_dias": "rtpcr_ate_10_dias",
        "encerrado_ate_60_dias": "encerrado_ate_60_dias",
        "virus": "virus",
        "resultado_virus": "virus",
        "faixa_etaria": "faixa_etaria",
        "idade": "idade",
        "positivo": "positivo",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    for c in [
        "atende_definicao_sg",
        "raca_cor_preenchida",
        "escolaridade_preenchida",
        "antiviral_preenchido",
        "rtpcr_processado",
        "rtpcr_ate_10_dias",
        "encerrado_ate_60_dias",
        "positivo",
    ]:
        if c in out.columns:
            out[c] = _norm_bool(out[c])
    if "idade" in out.columns and "faixa_etaria" not in out.columns:
        idade = pd.to_numeric(out["idade"], errors="coerce")
        bins = [-1, 4, 9, 19, 39, 59, 79, 200]
        labels = ["0-4", "5-9", "10-19", "20-39", "40-59", "60-79", "80+"]
        out["faixa_etaria"] = pd.cut(idade, bins=bins, labels=labels).astype(str)
    if "se_label" not in out.columns and {"ano_epi", "semana_epi"}.issubset(out.columns):
        out["semana_epi"] = pd.to_numeric(out["semana_epi"], errors="coerce")
        out["ano_epi"] = pd.to_numeric(out["ano_epi"], errors="coerce")
        out["se_label"] = out.apply(
            lambda r: f"{int(r['ano_epi'])}-W{int(r['semana_epi']):02d}"
            if pd.notna(r.get("ano_epi")) and pd.notna(r.get("semana_epi"))
            else "",
            axis=1,
        )
    if "unidade_sentinela" not in out.columns:
        out["unidade_sentinela"] = "US_NAO_INFORMADA"
    return out


def compute_sentinela_sg_indicators(
    agregado: pd.DataFrame,
    amostras: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    cat = load_sentinela_sg_catalog()
    meta = float(cat.get("meta_qualidade_oms_pct", 80) or 80)
    meta_amostras = float(cat.get("meta_amostras_por_se", 10) or 10)

    agg = _prepare_agregado(agregado)
    ams = _prepare_amostras(amostras) if amostras is not None else pd.DataFrame()

    if agg.empty and ams.empty:
        return {
            "epi_sentinela_sg_indicadores": pd.DataFrame(),
            "epi_sentinela_sg_semanal": pd.DataFrame(),
            "epi_sentinela_sg_virus_se": pd.DataFrame(),
            "epi_sentinela_sg_faixa_etaria": pd.DataFrame(),
            "dicionario_indicadores_ms_sentinela_sg": catalog_as_dataframe(),
        }

    # Semanal operacional (SG-10 + amostras)
    semanal = agg.copy() if not agg.empty else pd.DataFrame()
    if not semanal.empty:
        semanal["prop_sg_atendimentos_pct"] = np.where(
            semanal.get("atendimentos_total", 0).fillna(0) > 0,
            semanal["atendimentos_sg"] / semanal["atendimentos_total"] * 100,
            np.nan,
        )
        if "amostras_coletadas" in semanal.columns:
            semanal["meta_amostras_atingida"] = (semanal["amostras_coletadas"] >= meta_amostras).astype(int)
            semanal["classificacao_coleta"] = semanal["amostras_coletadas"].apply(
                lambda n: (
                    "excelente"
                    if pd.notna(n) and n >= 10
                    else "muito_bom"
                    if pd.notna(n) and n >= 7
                    else "bom"
                    if pd.notna(n) and n >= 4
                    else "baixo"
                    if pd.notna(n) and n >= 1
                    else "silencioso"
                )
            )

    # Indicadores por US (periodo carregado)
    rows = []
    us_set: set[str] = set()
    if not semanal.empty and "unidade_sentinela" in semanal.columns:
        us_set.update(semanal["unidade_sentinela"].dropna().astype(str).tolist())
    if not ams.empty and "unidade_sentinela" in ams.columns:
        us_set.update(ams["unidade_sentinela"].dropna().astype(str).tolist())
    us_list = sorted(us_set)
    if not us_list and not semanal.empty:
        us_list = ["TODAS"]

    for us in us_list:
        a = semanal[semanal["unidade_sentinela"].astype(str).eq(us)] if not semanal.empty and us != "TODAS" else semanal
        m = ams[ams["unidade_sentinela"].astype(str).eq(us)] if not ams.empty and us != "TODAS" else ams

        se_total = int(a["se_label"].nunique()) if not a.empty and "se_label" in a.columns else 0
        se_com_agregado = int(a.loc[a.get("atendimentos_total", pd.Series(dtype=float)).fillna(0) > 0, "se_label"].nunique()) if se_total else 0
        se_com_amostra = int(a.loc[a.get("amostras_coletadas", pd.Series(dtype=float)).fillna(0) > 0, "se_label"].nunique()) if se_total else 0
        media_amostras = float(a["amostras_coletadas"].mean()) if not a.empty and "amostras_coletadas" in a.columns else np.nan
        # homogeneidade: 100 - CV% (limitado 0-100); se constante = 100
        if not a.empty and "amostras_coletadas" in a.columns and a["amostras_coletadas"].notna().sum() > 1:
            mu = float(a["amostras_coletadas"].mean())
            sd = float(a["amostras_coletadas"].std(ddof=0))
            homogeneidade = float(max(0.0, min(100.0, 100.0 - (sd / mu * 100.0 if mu else 100.0))))
        else:
            homogeneidade = np.nan

        vals = {
            "SG-01": (se_com_agregado / se_total * 100) if se_total else np.nan,
            "SG-02": (se_com_amostra / se_total * 100) if se_total else np.nan,
            "SG-03": media_amostras,
            "SG-04": homogeneidade,
            "SG-10": float(a["prop_sg_atendimentos_pct"].mean()) if not a.empty and "prop_sg_atendimentos_pct" in a.columns else np.nan,
        }

        if not m.empty:
            n = len(m)
            vals["SG-05"] = float(m["atende_definicao_sg"].mean() * 100) if "atende_definicao_sg" in m.columns else np.nan
            fill_cols = [c for c in ["raca_cor_preenchida", "escolaridade_preenchida", "antiviral_preenchido"] if c in m.columns]
            vals["SG-06"] = float(m[fill_cols].mean().mean() * 100) if fill_cols else np.nan
            vals["SG-07"] = float(m["rtpcr_processado"].mean() * 100) if "rtpcr_processado" in m.columns else np.nan
            if "rtpcr_processado" in m.columns and "rtpcr_ate_10_dias" in m.columns:
                den = max(int(m["rtpcr_processado"].sum()), 1)
                vals["SG-08"] = float(m.loc[m["rtpcr_processado"] == 1, "rtpcr_ate_10_dias"].sum() / den * 100)
            else:
                vals["SG-08"] = np.nan
            vals["SG-09"] = float(m["encerrado_ate_60_dias"].mean() * 100) if "encerrado_ate_60_dias" in m.columns else np.nan
            if "positivo" in m.columns and "rtpcr_processado" in m.columns:
                den = max(int(m["rtpcr_processado"].sum()), 1)
                vals["SG-11"] = float(m.loc[m["rtpcr_processado"] == 1, "positivo"].sum() / den * 100)
            elif "virus" in m.columns:
                tested = m[m["virus"].astype(str).str.len() > 0]
                pos = tested[~tested["virus"].astype(str).str.lower().isin(["negativo", "nao detectado", "não detectado", ""])]
                vals["SG-11"] = (len(pos) / max(len(tested), 1) * 100) if len(tested) else np.nan
            else:
                vals["SG-11"] = np.nan

        nome = {r["id"]: r.get("nome", r["id"]) for _, r in catalog_as_dataframe().iterrows()}
        for iid, valor in vals.items():
            if pd.isna(valor):
                continue
            rows.append(
                {
                    "unidade_sentinela": us,
                    "indicador_id": iid,
                    "indicador_nome": nome.get(iid, iid),
                    "valor": valor,
                    "unidade": "%" if iid != "SG-03" else "amostras/SE",
                    "classificacao": _classify(valor, meta) if iid != "SG-03" else (
                        "excelente" if valor >= 10 else "muito_bom" if valor >= 7 else "bom" if valor >= 4 else "baixo" if valor >= 1 else "silencioso"
                    ),
                    "meta_referencia": meta if iid != "SG-03" else meta_amostras,
                    "fonte": "MS Sentinela SG",
                }
            )

    indicadores = pd.DataFrame(rows)

    virus_se = pd.DataFrame()
    faixa = pd.DataFrame()
    if not ams.empty and "virus" in ams.columns:
        keys = [c for c in ["unidade_sentinela", "se_label", "virus"] if c in ams.columns]
        virus_se = ams.groupby(keys, as_index=False).size().rename(columns={"size": "casos"})
    if not ams.empty and "faixa_etaria" in ams.columns and "virus" in ams.columns:
        keys = [c for c in ["unidade_sentinela", "faixa_etaria", "virus"] if c in ams.columns]
        faixa = ams.groupby(keys, as_index=False).size().rename(columns={"size": "casos"})

    return {
        "epi_sentinela_sg_indicadores": indicadores,
        "epi_sentinela_sg_semanal": semanal,
        "epi_sentinela_sg_virus_se": virus_se,
        "epi_sentinela_sg_faixa_etaria": faixa,
        "dicionario_indicadores_ms_sentinela_sg": catalog_as_dataframe(),
    }
