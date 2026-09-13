# -*- coding: utf-8 -*-
"""Mapa único de gestão: unidades CNES + aldeias/quilombos/assentamentos."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sisclima.core.db import read_table, table_exists
from sisclima.engines.cobertura_territorio import load_cobertura, persistir_cobertura
from sisclima.ingestion.cnes_geo import load_cnes_unidades_geo
from sisclima.ui.theme import callout, insight_cards

_GRUPO_CNES = {
    "hospital": "Hospital / maternidade",
    "urgencia": "UPA / urgência",
    "aps": "APS / UBS",
    "laboratorio": "Laboratório / vigilância",
    "ambulatorio": "Ambulatório / clínica",
    "outros": "Outros",
}
_GRUPO_STYLE = {
    "hospital": {"color": "#7f1d1d", "size": 13},
    "urgencia": {"color": "#c2410c", "size": 11},
    "aps": {"color": "#1d4ed8", "size": 8},
    "laboratorio": {"color": "#0f766e", "size": 9},
    "ambulatorio": {"color": "#6d28d9", "size": 7},
    "outros": {"color": "#64748b", "size": 6},
}
_CAT_TERR = {
    "aldeia indígena": "Aldeia",
    "quilombo": "Quilombo",
    "assentamento": "Assentamento",
}
_CAT_TERR_STYLE = {
    "Aldeia": {"color": "#15803d", "size": 12},
    "Quilombo": {"color": "#a16207", "size": 12},
    "Assentamento": {"color": "#b45309", "size": 11},
}


def _ibge7(s: pd.Series) -> pd.Series:
    """Chave municipal: IBGE-7 (resumo) e IBGE-6 (CNES) cruzam pelos 6 primeiros dígitos."""
    digits = s.astype(str).str.replace(r"\D", "", regex=True)
    return digits.str.extract(r"(\d{6,7})", expand=False).str[:6]


def _recorte(df: pd.DataFrame, resumo: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or resumo is None or resumo.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    if "cod_ibge" in out.columns and "cod_ibge" in resumo.columns:
        ibges = set(_ibge7(resumo["cod_ibge"]).dropna())
        out["cod_ibge"] = _ibge7(out["cod_ibge"])
        return out[out["cod_ibge"].isin(ibges)]
    if "municipio" in out.columns and "municipio" in resumo.columns:
        muns = set(resumo["municipio"].dropna().astype(str).str.casefold())
        return out[out["municipio"].astype(str).str.casefold().isin(muns)]
    return out


def _territorios() -> pd.DataFrame:
    for name in ("vigibarragens_populacoes", "vigibarragens_populacoes"):
        if table_exists(name):
            df = read_table(name)
            if df is not None and not df.empty:
                return df
    return pd.DataFrame()


def render_mapa_gestao_territorio(resumo: pd.DataFrame, *, allow_fetch: bool = False) -> None:
    cnes = load_cnes_unidades_geo(resumo, fetch=False, persist=False)
    if (cnes is None or cnes.empty) and allow_fetch:
        with st.spinner("Buscando estabelecimentos CNES (UF 51)…"):
            cnes = load_cnes_unidades_geo(resumo, fetch=True, persist=True)
    cnes = cnes if cnes is not None else pd.DataFrame()
    cnes = _recorte(cnes, resumo)

    cob = load_cobertura()
    if cob.empty and not _territorios().empty and not cnes.empty:
        cob = persistir_cobertura(resumo)
    cob = _recorte(cob, resumo)

    n_cnes = 0
    if not cnes.empty and {"lat", "lon"}.issubset(cnes.columns):
        n_cnes = int(cnes["lat"].notna().sum())
    n_terr = 0 if cob.empty else len(cob)
    n_longe = int(cob["longe_rede"].fillna(False).sum()) if not cob.empty and "longe_rede" in cob.columns else 0
    n_oficial = 0
    if not cnes.empty and "fonte_coord" in cnes.columns:
        n_oficial = int(cnes["fonte_coord"].astype(str).isin(["opendata_cnes", "dw_cnes"]).sum())
    insight_cards(
        [
            ("Unidades CNES", str(n_cnes), "com coordenada no recorte"),
            ("Ponto oficial CNES", str(n_oficial), "entra no cálculo de km"),
            ("Territórios com lat/lon", str(n_terr), "aldeia / quilombo / assentamento"),
            ("Longe da rede", str(n_longe), "APS > 30 km ou hospital > 50 km"),
        ]
    )
    callout(
        "Distância operacional é o trajeto viário (OSRM). A linha reta só pré-seleciona candidatos "
        "e entra se a rota falhar. Centroide municipal não conta como endereço da unidade. "
        "Exposição climática do município não é o mesmo que ‘sem UBS’.",
        "info",
    )

    so_longe = st.checkbox("Só territórios longe da APS ou do hospital", value=False, key="geo_so_longe")
    grupos = []
    if not cnes.empty and "grupo_tipo" in cnes.columns:
        grupos = sorted(cnes["grupo_tipo"].dropna().unique().tolist())
    escolhidos = st.multiselect(
        "Tipo de unidade CNES",
        grupos,
        default=grupos,
        format_func=lambda g: _GRUPO_CNES.get(g, g),
        key="geo_gestao_tipos_cnes",
    )

    pts_cnes = pd.DataFrame()
    if not cnes.empty and {"lat", "lon"}.issubset(cnes.columns):
        pts_cnes = cnes.dropna(subset=["lat", "lon"]).copy()
        if escolhidos:
            pts_cnes = pts_cnes[pts_cnes["grupo_tipo"].isin(escolhidos)]
        pts_cnes = pts_cnes.head(3500)
        pts_cnes["camada"] = pts_cnes.get("grupo_tipo", "cnes").map(lambda g: _GRUPO_CNES.get(g, "CNES"))
        pts_cnes["rotulo"] = pts_cnes.get("nome_unidade", pts_cnes.get("cnes", ""))

    pts_terr = cob.copy() if not cob.empty else pd.DataFrame()
    if not pts_terr.empty:
        if so_longe and "longe_rede" in pts_terr.columns:
            pts_terr = pts_terr[pts_terr["longe_rede"].fillna(False)]
        pts_terr = pts_terr.dropna(subset=["lat", "lon"])
        pts_terr["camada"] = pts_terr.get("categoria", "território").map(lambda c: _CAT_TERR.get(str(c), str(c)))
        pts_terr["rotulo"] = pts_terr.get("nome", "")

    if pts_cnes.empty and pts_terr.empty:
        callout(
            "Sem pontos georreferenciados neste recorte. Rode o pipeline ou atualize o CNES.",
            "warn",
        )
        if allow_fetch and st.button("Atualizar CNES agora", key="btn_fetch_cnes_gestao"):
            with st.spinner("Consultando Dados Abertos CNES…"):
                load_cnes_unidades_geo(resumo, fetch=True, persist=True)
                persistir_cobertura(resumo)
            st.rerun()
        return

    import plotly.graph_objects as go

    fig = go.Figure()
    if not pts_cnes.empty:
        order = ["hospital", "urgencia", "aps", "laboratorio", "ambulatorio", "outros"]
        grupos_plot = [g for g in order if g in set(pts_cnes.get("grupo_tipo", pd.Series(dtype=str)).dropna())]
        for g in pts_cnes.get("grupo_tipo", pd.Series(dtype=str)).dropna().unique():
            if g not in grupos_plot:
                grupos_plot.append(g)
        for g in grupos_plot:
            sub = pts_cnes[pts_cnes["grupo_tipo"] == g] if "grupo_tipo" in pts_cnes.columns else pts_cnes
            if sub.empty:
                continue
            style = _GRUPO_STYLE.get(str(g), {"color": "#475569", "size": 7})
            opac = 0.9
            if "fonte_coord" in sub.columns:
                # média simples: centroides mais claros
                n_cent = int((sub["fonte_coord"].astype(str) == "centroid_municipio").sum())
                if n_cent == len(sub):
                    opac = 0.45
                elif n_cent > 0:
                    opac = 0.7
            hover = (
                sub["rotulo"].astype(str)
                + "<br>"
                + sub.get("tipo_unidade", pd.Series([""] * len(sub))).astype(str)
                + "<br>"
                + sub.get("municipio", pd.Series([""] * len(sub))).astype(str)
            )
            fig.add_trace(
                go.Scattermap(
                    lat=sub["lat"],
                    lon=sub["lon"],
                    mode="markers",
                    name=_GRUPO_CNES.get(str(g), str(g)),
                    marker={"size": style["size"], "color": style["color"], "opacity": opac},
                    text=hover,
                    hovertemplate="%{text}<extra>CNES</extra>",
                )
            )
    if not pts_terr.empty:
        for camada in pts_terr["camada"].dropna().unique():
            sub = pts_terr[pts_terr["camada"] == camada]
            style = _CAT_TERR_STYLE.get(str(camada), {"color": "#b45309", "size": 11})
            fig.add_trace(
                go.Scattermap(
                    lat=sub["lat"],
                    lon=sub["lon"],
                    mode="markers",
                    name=str(camada),
                    marker={"size": style["size"], "color": style["color"], "opacity": 0.95},
                    text=sub["rotulo"].astype(str)
                    + " · "
                    + sub.get("camada", "").astype(str)
                    + (
                        "<br>APS "
                        + sub["km_aps"].astype(str)
                        + " km"
                        + (
                            sub["min_aps"].map(lambda v: f" ({int(v)} min)" if pd.notna(v) else "")
                            if "min_aps" in sub.columns
                            else ""
                        )
                        + " · hosp. "
                        + sub["km_hospital"].astype(str)
                        + " km"
                        if "km_aps" in sub.columns
                        else ""
                    ),
                    hovertemplate="%{text}<extra>Território</extra>",
                )
            )
    fig.update_layout(
        map_style="carto-positron",
        margin=dict(l=0, r=0, t=8, b=0),
        height=520,
        legend=dict(
            title="Tipo / território",
            orientation="v",
            yanchor="top",
            y=0.98,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#cbd5e1",
            borderwidth=1,
            font=dict(size=11),
        ),
        map={"center": {"lat": -12.6, "lon": -55.7}, "zoom": 4.8},
    )
    try:
        st.plotly_chart(fig, width="stretch")
    except Exception:
        try:
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.warning("Mapa interativo indisponível neste ambiente. Veja a tabela abaixo.")

    if not cob.empty:
        cols = [
            c
            for c in [
                "nome",
                "categoria",
                "municipio",
                "nivel",
                "km_aps",
                "min_aps",
                "metodo_aps",
                "nome_aps",
                "km_hospital",
                "min_hospital",
                "nome_hospital",
                "longe_rede",
            ]
            if c in cob.columns
        ]
        view = cob[cob["longe_rede"].fillna(False)] if so_longe and "longe_rede" in cob.columns else cob
        st.caption(
            "km e minutos = trajeto viário (OSRM, sem trânsito em tempo real). "
            "Se a rota falhar, usa linha reta (sem minutos). Centroide não entra. Quilombo certificado ≠ titulação."
        )
        st.dataframe(
            view[cols].sort_values(["longe_rede", "km_aps"], ascending=[False, False])
            if "km_aps" in view.columns
            else view[cols],
            hide_index=True,
            height=280,
        )
