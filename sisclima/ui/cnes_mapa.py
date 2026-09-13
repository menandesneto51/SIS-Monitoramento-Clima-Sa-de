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

# Paleta distinta (daltonismo-amigável) + tamanho por papel na rede
_GRUPO_STYLE = {
    "hospital": {"color": "#7f1d1d", "size": 14},
    "urgencia": {"color": "#c2410c", "size": 12},
    "aps": {"color": "#1d4ed8", "size": 9},
    "laboratorio": {"color": "#0f766e", "size": 10},
    "ambulatorio": {"color": "#6d28d9", "size": 8},
    "outros": {"color": "#64748b", "size": 7},
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


def _plot_cnes_por_tipo(pts: pd.DataFrame):
    """Uma trilha por tipo — legenda legível e tamanhos distintos."""
    import plotly.graph_objects as go

    fig = go.Figure()
    order = ["hospital", "urgencia", "aps", "laboratorio", "ambulatorio", "outros"]
    grupos = [g for g in order if g in set(pts.get("grupo_tipo", pd.Series(dtype=str)).dropna())]
    for g in pts.get("grupo_tipo", pd.Series(dtype=str)).dropna().unique():
        if g not in grupos:
            grupos.append(g)

    for g in grupos:
        sub = pts[pts["grupo_tipo"] == g] if "grupo_tipo" in pts.columns else pts
        if sub.empty:
            continue
        style = _GRUPO_STYLE.get(str(g), {"color": "#475569", "size": 8})
        # Centroide municipal: menor opacidade para não competir com ponto oficial
        if "fonte_coord" in sub.columns:
            opac = sub["fonte_coord"].astype(str).map(
                lambda f: 0.45 if f == "centroid_municipio" else 0.9
            )
        else:
            opac = pd.Series([0.85] * len(sub), index=sub.index)
        hover = (
            sub.get("nome_unidade", sub.get("cnes", "")).astype(str)
            + "<br>"
            + sub.get("tipo_unidade", "").astype(str)
            + "<br>"
            + sub.get("municipio", "").astype(str)
            + "<br>"
            + sub.get("fonte_coord", "").astype(str)
        )
        fig.add_trace(
            go.Scattermap(
                lat=sub["lat"],
                lon=sub["lon"],
                mode="markers",
                name=_GRUPO_LABEL.get(str(g), str(g)),
                marker={
                    "size": style["size"],
                    "color": style["color"],
                    "opacity": opac.tolist(),
                },
                text=hover,
                hovertemplate="%{text}<extra></extra>",
            )
        )
    fig.update_layout(
        map_style="carto-positron",
        margin=dict(l=0, r=0, t=8, b=0),
        height=520,
        legend=dict(
            title="Tipo de unidade",
            orientation="v",
            yanchor="top",
            y=0.98,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="#cbd5e1",
            borderwidth=1,
            font=dict(size=12),
        ),
        map=dict(center=dict(lat=-12.6, lon=-55.8), zoom=4.8),
    )
    return fig


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
        "Cor = tipo de unidade · tamanho = papel na rede (hospital maior que APS). "
        "Ponto semitransparente = centroide municipal (sem lat/lon no cadastro), não o endereço da porta.",
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
    so_oficial = st.checkbox(
        "Só coordenadas oficiais (ocultar centroides)",
        value=False,
        key="cnes_geo_so_oficial",
    )
    if escolhidos and not pts.empty:
        pts = pts[pts["grupo_tipo"].isin(escolhidos)]
    if so_oficial and not pts.empty and "fonte_coord" in pts.columns:
        pts = pts[pts["fonte_coord"].astype(str).isin(["opendata_cnes", "dw_cnes"])]
    if pts.empty:
        st.info("Nenhuma unidade com coordenada para os filtros atuais.")
        return
    if len(pts) > 4000:
        st.caption(f"Exibindo 4.000 de {len(pts)} pontos para o mapa permanecer utilizável.")
        pts = pts.head(4000)

    # Contagem por tipo — leitura rápida antes do mapa
    if "grupo_tipo" in pts.columns:
        cont = (
            pts["grupo_tipo"]
            .map(lambda g: _GRUPO_LABEL.get(g, g))
            .value_counts()
            .rename_axis("tipo")
            .reset_index(name="unidades")
        )
        st.dataframe(cont, hide_index=True, use_container_width=True, height=min(220, 40 + 28 * len(cont)))

    try:
        fig = _plot_cnes_por_tipo(pts)
        try:
            st.plotly_chart(fig, width="stretch")
        except TypeError:
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        import plotly.express as px

        pts = pts.copy()
        pts["tipo_rotulo"] = pts.get("grupo_tipo", "").map(lambda g: _GRUPO_LABEL.get(g, g))
        fig = px.scatter_map(
            pts,
            lat="lat",
            lon="lon",
            color="tipo_rotulo",
            hover_name="nome_unidade" if "nome_unidade" in pts.columns else None,
            hover_data=[c for c in ["cnes", "tipo_unidade", "municipio", "fonte_coord"] if c in pts.columns],
            zoom=5.1,
            height=520,
            color_discrete_sequence=["#7f1d1d", "#c2410c", "#1d4ed8", "#0f766e", "#6d28d9", "#64748b"],
        )
        fig.update_layout(map_style="carto-positron", margin=dict(l=0, r=0, t=0, b=0), legend_title_text="Tipo")
        try:
            st.plotly_chart(fig, width="stretch")
        except TypeError:
            st.plotly_chart(fig, use_container_width=True)

    tab_ok, tab_sem = st.tabs(["Unidades no mapa", "Sem coordenada oficial"])
    with tab_ok:
        cols = [c for c in ["cnes", "nome_unidade", "tipo_unidade", "grupo_tipo", "municipio", "fonte_coord"] if c in pts.columns]
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
