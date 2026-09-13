# -*- coding: utf-8 -*-
"""Mapas CNES: equipamentos e profissionais por ocupação (sem PII)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sisclima.core.config import as_bool, env
from sisclima.engines.cnes_rede_mapas import (
    load_or_fetch_equipamentos_tipo,
    load_or_fetch_profissionais_ocupacao,
    pivot_equipamentos_municipio,
    pivot_profissionais_municipio,
    prepare_equipamentos_por_tipo,
    prepare_profissionais_por_ocupacao,
)
from sisclima.engines.geospatial import make_choropleth_or_points, prepare_map_dataframe
from sisclima.ui.theme import callout, insight_cards


def _ibge7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d{7})", expand=False)


def _recorte_mun(df: pd.DataFrame, resumo: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or resumo is None or resumo.empty or "cod_ibge" not in df.columns:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    out["_k"] = out["cod_ibge"].astype(str).str.extract(r"(\d{6,7})", expand=False).str[:6]
    keys = set(resumo["cod_ibge"].astype(str).str.extract(r"(\d{6,7})", expand=False).str[:6].dropna())
    return out[out["_k"].isin(keys)].drop(columns=["_k"], errors="ignore")


def _merge_mapa(resumo: pd.DataFrame, agg: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    base = resumo.copy()
    if "cod_ibge" not in base.columns:
        return pd.DataFrame()
    base["cod_ibge"] = _ibge7(base["cod_ibge"])
    right = agg.copy()
    right["cod_ibge"] = right["cod_ibge"].astype(str).str.extract(r"(\d{6,7})", expand=False)
    # Prefer IBGE-7 from resumo via 6-digit join
    base["_k"] = base["cod_ibge"].str[:6]
    right["_k"] = right["cod_ibge"].str[:6]
    cols = ["_k"] + [c for c in value_cols if c in right.columns]
    if "municipio" in right.columns and "municipio" not in cols:
        cols.append("municipio")
    m = base.merge(right[cols].drop_duplicates("_k"), on="_k", how="left", suffixes=("", "_x"))
    return m.drop(columns=["_k"], errors="ignore")


def render_mapa_equipamentos_cnes(resumo: pd.DataFrame, *, allow_fetch: bool = False) -> None:
    callout(
        "Equipamentos CNES agregados por município (DW). Sem identificação de estabelecimento "
        "além da contagem. Nebulização = tipo/grupo contendo NEBUL.",
        "info",
    )
    try_dw = bool(allow_fetch and as_bool(env("USE_DW_CNES", "false"), False))
    raw = load_or_fetch_equipamentos_tipo(try_dw=try_dw, persist=try_dw)
    raw = _recorte_mun(raw, resumo)

    # Fallback: totais já no resumo
    if raw.empty and resumo is not None and not resumo.empty:
        cols = [c for c in ("cod_ibge", "municipio", "equipamentos_total", "equipamentos_nebulizacao") if c in resumo.columns]
        if "equipamentos_total" in cols or "equipamentos_nebulizacao" in cols:
            agg = resumo[cols].copy()
            if "equipamentos_total" not in agg.columns:
                agg["equipamentos_total"] = pd.NA
            if "equipamentos_nebulizacao" not in agg.columns:
                agg["equipamentos_nebulizacao"] = pd.NA
        else:
            st.info("Sem equipamentos CNES neste recorte. Rode o pipeline com USE_DW_CNES=true (VPN SES).")
            return
    else:
        agg = pivot_equipamentos_municipio(raw)

    if agg.empty:
        st.info("Sem equipamentos CNES neste recorte.")
        return

    tot = int(pd.to_numeric(agg.get("equipamentos_total"), errors="coerce").fillna(0).sum())
    neb = int(pd.to_numeric(agg.get("equipamentos_nebulizacao"), errors="coerce").fillna(0).sum())
    insight_cards(
        [
            ("Equipamentos (soma mun.)", str(tot), "competência CNES"),
            ("Nebulização", str(neb), "tipo/grupo NEBUL"),
            ("Municípios com dado", str(int((pd.to_numeric(agg.get("equipamentos_total"), errors="coerce").fillna(0) > 0).sum())), "recorte"),
        ]
    )

    metrica = st.radio(
        "Métrica do mapa",
        ["equipamentos_total", "equipamentos_nebulizacao"],
        format_func=lambda x: "Total de equipamentos" if x == "equipamentos_total" else "Nebulizadores",
        horizontal=True,
        key="cnes_eq_metrica",
    )
    map_src = _merge_mapa(resumo, agg, ["equipamentos_total", "equipamentos_nebulizacao"])
    map_df, geojson, status = prepare_map_dataframe(map_src)
    st.caption(status)
    if metrica in map_df.columns:
        fig = make_choropleth_or_points(
            map_df,
            geojson,
            color_col=metrica,
            title="CNES — equipamentos por município",
            hover_cols=[c for c in ["equipamentos_total", "equipamentos_nebulizacao", "regional_saude"] if c in map_df.columns],
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    if not raw.empty:
        st.markdown("##### Ranking por tipo (recorte)")
        tipo = prepare_equipamentos_por_tipo(raw)
        top = (
            tipo.groupby(["equipamento_grupo", "equipamento_tipo"], as_index=False)["equipamentos_existentes"]
            .sum()
            .sort_values("equipamentos_existentes", ascending=False)
            .head(40)
        )
        st.dataframe(top, hide_index=True, use_container_width=True, height=280)


def render_mapa_profissionais_cnes(resumo: pd.DataFrame, *, allow_fetch: bool = False) -> None:
    callout(
        "Profissionais CNES só por família de ocupação (CBO). "
        "Não há nome, CNS, CPF nem registro — apenas contagens municipais.",
        "warn",
    )
    try_dw = bool(allow_fetch and as_bool(env("USE_DW_CNES", "false"), False))
    raw = load_or_fetch_profissionais_ocupacao(try_dw=try_dw, persist=try_dw)
    raw = _recorte_mun(raw, resumo)

    grupo_sel = "Todas"
    if raw.empty and resumo is not None and not resumo.empty and "cnes_profissionais_qtd" in resumo.columns:
        agg = resumo[[c for c in ("cod_ibge", "municipio", "cnes_profissionais_qtd") if c in resumo.columns]].copy()
        agg = agg.rename(columns={"cnes_profissionais_qtd": "profissionais_qtd"})
        st.caption("Exibindo total municipal do resumo (detalhe por CBO ainda não carregado).")
    elif raw.empty:
        st.info("Sem profissionais CNES por ocupação neste recorte. Rode o pipeline com USE_DW_CNES=true (VPN SES).")
        return
    else:
        prep = prepare_profissionais_por_ocupacao(raw)
        grupos = ["Todas"] + sorted(prep["grupo_ocupacao"].dropna().unique().tolist())
        grupo_sel = st.selectbox("Família profissional", grupos, key="cnes_prof_grupo")
        agg = pivot_profissionais_municipio(prep, grupo=None if grupo_sel == "Todas" else grupo_sel)

    tot = int(pd.to_numeric(agg.get("profissionais_qtd"), errors="coerce").fillna(0).sum())
    insight_cards(
        [
            ("Profissionais (contagem)", str(tot), "sem identificação pessoal"),
            ("Filtro", grupo_sel, "família CBO"),
            ("Municípios com dado", str(int((pd.to_numeric(agg.get("profissionais_qtd"), errors="coerce").fillna(0) > 0).sum())), "recorte"),
        ]
    )

    map_src = _merge_mapa(resumo, agg, ["profissionais_qtd"])
    map_df, geojson, status = prepare_map_dataframe(map_src)
    st.caption(status)
    if "profissionais_qtd" in map_df.columns:
        fig = make_choropleth_or_points(
            map_df,
            geojson,
            color_col="profissionais_qtd",
            title=f"CNES — profissionais por município ({grupo_sel})",
            hover_cols=[c for c in ["profissionais_qtd", "regional_saude"] if c in map_df.columns],
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    if not raw.empty:
        st.markdown("##### Distribuição por família de ocupação (recorte)")
        prep = prepare_profissionais_por_ocupacao(raw)
        dist = (
            prep.groupby("grupo_ocupacao", as_index=False)["profissionais_qtd"]
            .sum()
            .sort_values("profissionais_qtd", ascending=False)
        )
        st.dataframe(dist, hide_index=True, use_container_width=True, height=280)
        with st.expander("Detalhe CBO (código × município — sem nomes)", expanded=False):
            det = prep.sort_values("profissionais_qtd", ascending=False).head(200)
            cols = [c for c in ("municipio", "cod_ibge", "ocupacao_codigo", "grupo_ocupacao", "profissionais_qtd") if c in det.columns]
            st.dataframe(det[cols], hide_index=True, use_container_width=True, height=320)


def render_mapas_rede_cnes(resumo: pd.DataFrame, *, allow_fetch: bool = False) -> None:
    """Bloco único: equipamentos + profissionais."""
    tab_eq, tab_prof = st.tabs(["Equipamentos CNES", "Profissionais por ocupação"])
    with tab_eq:
        render_mapa_equipamentos_cnes(resumo, allow_fetch=allow_fetch)
    with tab_prof:
        render_mapa_profissionais_cnes(resumo, allow_fetch=allow_fetch)
