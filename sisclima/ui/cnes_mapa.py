# -*- coding: utf-8 -*-
"""Mapa de unidades de saúde georreferenciadas (CNES)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sisclima.ingestion.cnes_geo import load_cnes_unidades_geo
from sisclima.ui.theme import callout, insight_cards

_GRUPO_LABEL = {
    "hospital": "Hospital / maternidade",
    "urgencia": "UPA / urgência",
    "aps": "APS / UBS",
    "laboratorio": "Laboratório / vigilância",
    "ambulatorio": "Ambulatório / clínica",
    "outros": "Outros",
}


def _filter_recorte(df: pd.DataFrame, resumo: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or resumo is None or resumo.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    if "cod_ibge" in out.columns and "cod_ibge" in resumo.columns:
        ibges = set(resumo["cod_ibge"].dropna().astype(str).str.zfill(7))
        out["cod_ibge"] = out["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
        out = out[out["cod_ibge"].isin(ibges)]
    elif "municipio" in out.columns and "municipio" in resumo.columns:
        muns = set(resumo["municipio"].dropna().astype(str).str.casefold())
        out = out[out["municipio"].astype(str).str.casefold().isin(muns)]
    return out


def render_mapa_cnes(resumo: pd.DataFrame, *, allow_fetch: bool = False) -> None:
    df = load_cnes_unidades_geo(resumo, fetch=False, persist=False)
    if (df is None or df.empty) and allow_fetch:
        with st.spinner("Buscando estabelecimentos CNES (UF 51)…"):
            df = load_cnes_unidades_geo(resumo, fetch=True, persist=True)
    elif df is None:
        df = pd.DataFrame()

    df = _filter_recorte(df, resumo)
    if df.empty:
        callout(
            "Ainda não há unidades CNES georreferenciadas neste recorte. "
            "Rode o pipeline com DW/API ou use Atualizar CNES (rede). "
            "Unidades sem lat/lon no cadastro podem aparecer no centroide do município.",
            "warn",
        )
        if allow_fetch and st.button("Atualizar CNES agora", key="btn_fetch_cnes_geo"):
            with st.spinner("Consultando Dados Abertos CNES…"):
                load_cnes_unidades_geo(resumo, fetch=True, persist=True)
            st.rerun()
        return

    n = len(df)
    n_geo = int((pd.to_numeric(df.get("lat"), errors="coerce").notna() & pd.to_numeric(df.get("lon"), errors="coerce").notna()).sum())
    n_oficial = int((df.get("fonte_coord", pd.Series(dtype=str)).astype(str).isin(["opendata_cnes", "dw_cnes"])).sum()) if "fonte_coord" in df.columns else n_geo
    n_cent = int((df.get("fonte_coord", pd.Series(dtype=str)).astype(str) == "centroid_municipio").sum()) if "fonte_coord" in df.columns else 0
    insight_cards(
        [
            ("Unidades no recorte", str(n), "CNES"),
            ("Com coordenada", str(n_geo), f"{n_oficial} oficiais"),
            ("Centroide municipal", str(n_cent), "cadastro sem lat/lon"),
            ("Sem ponto", str(n - n_geo), "não entram no mapa"),
        ]
    )
    callout(
        "Ponto oficial = lat/lon do CNES (MS/DW). Centroide municipal = unidade sem geolocalização no cadastro — "
        "não é o endereço da porta. Filtre o tipo para leitura operacional.",
        "info",
    )

    pts = df.dropna(subset=["lat", "lon"]).copy() if {"lat", "lon"}.issubset(df.columns) else pd.DataFrame()
    grupos = sorted(pts["grupo_tipo"].dropna().unique().tolist()) if not pts.empty and "grupo_tipo" in pts.columns else []
    escolhidos = st.multiselect(
        "Tipo de unidade",
        grupos,
        default=grupos,
        format_func=lambda g: _GRUPO_LABEL.get(g, g),
        key="cnes_geo_tipos",
    )
    if escolhidos and not pts.empty:
        pts = pts[pts["grupo_tipo"].isin(escolhidos)]
    if pts.empty:
        st.info("Nenhuma unidade com coordenada para os filtros atuais.")
        return
    if len(pts) > 4000:
        st.caption(f"Exibindo 4.000 de {len(pts)} pontos para o mapa permanecer utilizável.")
        pts = pts.head(4000)

    import plotly.express as px

    hover = [c for c in ["cnes", "tipo_unidade", "municipio", "fonte_coord"] if c in pts.columns]
    color = "grupo_tipo" if "grupo_tipo" in pts.columns else None
    try:
        fig = px.scatter_map(
            pts,
            lat="lat",
            lon="lon",
            color=color,
            hover_name="nome_unidade" if "nome_unidade" in pts.columns else None,
            hover_data=hover,
            zoom=5.1,
            height=460,
        )
        fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), legend_title_text="Tipo")
    except Exception:
        fig = px.scatter_geo(
            pts,
            lat="lat",
            lon="lon",
            color=color,
            hover_name="nome_unidade" if "nome_unidade" in pts.columns else None,
            height=460,
        )
        fig.update_geos(
            fitbounds="locations",
            visible=False,
            projection_type="mercator",
            lataxis_range=[-18.6, -7.0],
            lonaxis_range=[-62.0, -50.0],
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), legend_title_text="Tipo")
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)

    tab_ok, tab_sem = st.tabs(["Unidades no mapa", "Sem coordenada oficial"])
    with tab_ok:
        cols = [c for c in ["cnes", "nome_unidade", "tipo_unidade", "municipio", "fonte_coord"] if c in pts.columns]
        st.dataframe(pts[cols].sort_values("municipio") if "municipio" in pts.columns else pts[cols], hide_index=True, height=280)
    with tab_sem:
        sem = df[pd.to_numeric(df.get("lat"), errors="coerce").isna() | (df.get("fonte_coord", "") == "")]
        if sem.empty:
            st.caption("Todas as unidades do recorte têm alguma coordenada.")
        else:
            cols = [c for c in ["cnes", "nome_unidade", "tipo_unidade", "municipio"] if c in sem.columns]
            st.dataframe(sem[cols], hide_index=True, height=240)

    if allow_fetch:
        st.caption("Fonte: CNES / Ministério da Saúde (Dados Abertos) e DW SES-MT, quando disponível.")
        if st.button("Atualizar CNES agora", key="btn_fetch_cnes_geo_refresh"):
            with st.spinner("Consultando Dados Abertos CNES…"):
                load_cnes_unidades_geo(resumo, fetch=True, persist=True)
            st.rerun()
