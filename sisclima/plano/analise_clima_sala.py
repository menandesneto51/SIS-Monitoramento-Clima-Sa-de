# -*- coding: utf-8 -*-
"""Linha do tempo climática, sazonalidade e OR para o relatório da Sala.

Não inventa série: tabela ausente ou vazia vira aviso. OR é ecológico, não causal individual.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists

_MESES = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def _first_col(df: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lower = {str(c).lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _read_first(*tables: str) -> pd.DataFrame:
    for name in tables:
        if not table_exists(name):
            continue
        df = read_table(name)
        if df is not None and not df.empty:
            return df
    return pd.DataFrame()


def _to_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    col = _first_col(out, ("data", "dia", "time", "data_referencia"))
    if not col:
        return pd.DataFrame()
    out["data"] = pd.to_datetime(out[col], errors="coerce")
    return out.dropna(subset=["data"])


def serie_clima_estadual() -> pd.DataFrame:
    """Média estadual diária (Open-Meteo / biometeo + ar, se houver)."""
    met = _read_first("met_biometeo", "met_biometeo")
    met = _to_date(met)
    if met.empty:
        return pd.DataFrame()
    mapping = {
        "tmax": ("tmax", "tasmax", "temp_max"),
        "precipitacao_mm": ("precipitacao_mm", "precipitacao_mm", "chuva_mm"),
        "utci_proxy": ("utci_proxy", "utci"),
        "risco_calor_diario": ("risco_calor_diario",),
        "risco_cumulativo_3d": ("risco_cumulativo_3d", "risco_acumulado_3d"),
    }
    agg: dict[str, tuple[str, str]] = {}
    for dest, names in mapping.items():
        src = _first_col(met, names)
        if src:
            met[dest] = pd.to_numeric(met[src], errors="coerce")
            agg[dest] = (dest, "mean")
    if not agg:
        return pd.DataFrame()
    met["_dia"] = met["data"].dt.normalize()
    daily = met.groupby("_dia", as_index=False).agg(**agg).rename(columns={"_dia": "data"})

    ar = _read_first("qualidade_ar_estado_serie_v6", "qualidade_ar_municipal")
    ar = _to_date(ar)
    if not ar.empty:
        pm = _first_col(ar, ("pm25_ugm3", "pm25", "pm2_5"))
        if pm:
            ar["pm25_ugm3"] = pd.to_numeric(ar[pm], errors="coerce")
            ar["_dia"] = ar["data"].dt.normalize()
            ar_d = ar.groupby("_dia", as_index=False)["pm25_ugm3"].mean().rename(columns={"_dia": "data"})
            daily = daily.merge(ar_d, on="data", how="left")
    return daily.sort_values("data")


def _painel_municipal_semanal() -> pd.DataFrame:
    """Painel município-semana: clima da semana + ocupação/pressão/vulnerabilidade do resumo."""
    met = _read_first("met_biometeo", "met_biometeo")
    met = _to_date(met)
    ibge = _first_col(met, ("cod_ibge", "ibge", "ibge7"))
    if met.empty or not ibge or "tmax" not in met.columns:
        return pd.DataFrame()
    met["cod_ibge"] = met[ibge].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    met["tmax"] = pd.to_numeric(met["tmax"], errors="coerce")
    met["semana"] = met["data"].dt.to_period("W-SUN").dt.start_time
    painel = met.groupby(["semana", "cod_ibge"], as_index=False).agg(tmax=("tmax", "mean"))
    painel = painel.rename(columns={"semana": "data"})

    resumo = _read_first("resumo_municipal_atual")
    if resumo.empty:
        return painel
    ibge_r = _first_col(resumo, ("cod_ibge", "ibge", "ibge7"))
    if not ibge_r:
        return painel
    resumo = resumo.copy()
    resumo["cod_ibge"] = resumo[ibge_r].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    keep = ["cod_ibge"]
    for dest, names in (
        ("ocupacao_leitos_pct", ("ocupacao_leitos_pct", "ocupacao_pct")),
        ("pressao_calor_pct", ("pressao_calor_pct",)),
        ("indice_vulnerabilidade_calor", ("indice_vulnerabilidade_calor",)),
        ("regional_saude", ("regional_saude", "regiao_saude")),
        ("casos_arbovirus_7d", ("casos_arbovirus_7d", "casos_arbovirus_7d")),
        ("pm25_ugm3", ("pm25_ugm3", "pm25")),
    ):
        src = _first_col(resumo, names)
        if src:
            if dest == "regional_saude":
                resumo[dest] = resumo[src].astype(str)
            else:
                resumo[dest] = pd.to_numeric(resumo[src], errors="coerce")
            keep.append(dest)
    extra = resumo[keep].drop_duplicates("cod_ibge")
    return painel.merge(extra, on="cod_ibge", how="left")


def sazonalidade_mensal(serie_clima: pd.DataFrame | None = None) -> pd.DataFrame:
    stored = _read_first("sazonalidade_indice_mensal_v1", "sazonalidade_indice_mensal_v1")
    if not stored.empty:
        idx_col = _first_col(stored, ("indice_sazonal", "indice_sazonal"))
        mes_col = _first_col(stored, ("mes",))
        if idx_col and mes_col and pd.to_numeric(stored[idx_col], errors="coerce").notna().sum() >= 3:
            out = stored.rename(columns={idx_col: "indice_sazonal", mes_col: "mes"})
            if "mes_rotulo" not in out.columns:
                out["mes_rotulo"] = pd.to_numeric(out["mes"], errors="coerce").map(_MESES)
            return out
    clima = serie_clima if serie_clima is not None else serie_clima_estadual()
    if clima.empty or "tmax" not in clima.columns:
        return pd.DataFrame()
    work = clima.copy()
    work["mes"] = pd.to_datetime(work["data"]).dt.month
    base = work.groupby("mes", as_index=False)["tmax"].mean()
    media = float(base["tmax"].mean()) if not base.empty else 0.0
    if media <= 0:
        return pd.DataFrame()
    base["indice_sazonal"] = base["tmax"] / media
    base["mes_rotulo"] = base["mes"].map(_MESES)
    return base


def or_atual() -> pd.DataFrame:
    from sisclima.engines.odds_ratio import compute_climate_health_ors

    stored = _read_first("analise_clima_saude_odds_ratio_v1", "analise_clima_saude_odds_ratio_v1")
    if not stored.empty:
        return stored
    resumo = _read_first("resumo_municipal_atual")
    if resumo.empty:
        return pd.DataFrame()
    return compute_climate_health_ors(resumo)


def or_linha_tempo() -> pd.DataFrame:
    """OR semanal: municípios mais quentes na semana × ocupação/pressão/arbovirose do resumo."""
    from sisclima.engines.odds_ratio import or_binary

    painel = _painel_municipal_semanal()
    if painel.empty or "data" not in painel.columns:
        return pd.DataFrame()
    exp = "tmax"
    if exp not in painel.columns:
        return pd.DataFrame()
    outcomes = [c for c in ("ocupacao_leitos_pct", "pressao_calor_pct", "casos_arbovirus_7d") if c in painel.columns]
    if not outcomes:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for semana, sub in painel.groupby("data"):
        for out in outcomes:
            item = or_binary(sub, exp, out)
            if not item:
                continue
            item["data"] = pd.Timestamp(semana).strftime("%Y-%m-%d")
            item["n_municipios"] = int(sub["cod_ibge"].nunique()) if "cod_ibge" in sub.columns else int(len(sub))
            rows.append(item)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("data")


def or_grupos() -> pd.DataFrame:
    from sisclima.engines.odds_ratio import compute_or_by_group

    resumo = _read_first("resumo_municipal_atual")
    if resumo.empty:
        return pd.DataFrame()
    grupo = _first_col(resumo, ("regional_saude", "regiao_saude", "macroregiao_saude"))
    exp = _first_col(resumo, ("tmax", "utci_proxy", "pressao_calor_pct", "pm25_ugm3"))
    out = _first_col(resumo, ("ocupacao_leitos_pct", "pressao_calor_pct"))
    if not grupo or not exp or not out or grupo == out:
        return pd.DataFrame()
    if exp == out:
        out = _first_col(resumo, ("ocupacao_leitos_pct", "casos_arbovirus_7d"))
    if not out or exp == out:
        return pd.DataFrame()
    return compute_or_by_group(resumo, grupo, exp, out, min_n=8)


def painel_sala_clima() -> dict[str, Any]:
    clima = serie_clima_estadual()
    saz = sazonalidade_mensal(clima)
    ors = or_atual()
    or_t = or_linha_tempo()
    grupos = or_grupos()
    mes_atual = int(pd.Timestamp.now().month)
    pico = None
    if not saz.empty and "indice_sazonal" in saz.columns:
        valid = saz.dropna(subset=["indice_sazonal"])
        if not valid.empty:
            top = valid.sort_values("indice_sazonal", ascending=False).head(1)
            pico = {
                "mes": int(top.iloc[0].get("mes") or 0),
                "rotulo": str(top.iloc[0].get("mes_rotulo") or ""),
                "indice": float(top.iloc[0].get("indice_sazonal") or 0),
            }
    atual_idx = None
    if not saz.empty and "mes" in saz.columns:
        row = saz.loc[pd.to_numeric(saz["mes"], errors="coerce") == mes_atual]
        if not row.empty and pd.notna(row.iloc[0].get("indice_sazonal")):
            atual_idx = float(row.iloc[0].get("indice_sazonal") or 0)
    return {
        "serie_clima": clima,
        "sazonalidade": saz,
        "or_pares": ors,
        "or_timeline": or_t,
        "or_grupos": grupos,
        "pico_sazonal": pico,
        "indice_mes_atual": atual_idx,
        "mes_atual": mes_atual,
        "n_dias_clima": int(len(clima)),
        "disponivel": not clima.empty or not ors.empty,
    }
