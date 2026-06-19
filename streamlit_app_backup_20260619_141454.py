# -*- coding: utf-8 -*-
"""
SIS Clima-Saúde MT - Streamlit Cloud

Versão cloud baseada em arquivos CSV exportados para data/public.
Não acessa SQL Server, IndicaSUS, Datawarehouse, .env ou banco SQLite local.
"""

from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import plotly.express as px
import streamlit as st


BASE = Path(__file__).parent
PUBLIC = BASE / "data" / "public"

CORES = {
    "verde": "#2E8B57",
    "amarela": "#D4A719",
    "laranja": "#F47C20",
    "vermelha": "#D83232",
    "roxa": "#7E22CE",
    "cinza": "#6B7280",
}
ORDEM = {"cinza": 0, "verde": 1, "amarela": 2, "laranja": 3, "vermelha": 4, "roxa": 5}


def load_csv(name: str) -> pd.DataFrame:
    path = PUBLIC / name
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        st.warning(f"Falha ao carregar {name}: {exc}")
        return pd.DataFrame()


def normalize_level(value) -> str:
    s = str(value or "").strip().lower()
    mapa = {
        "verde": "verde",
        "amarelo": "amarela",
        "amarela": "amarela",
        "laranja": "laranja",
        "vermelho": "vermelha",
        "vermelha": "vermelha",
        "roxo": "roxa",
        "roxa": "roxa",
        "cinza": "cinza",
        "gray": "cinza",
        "grey": "cinza",
    }
    return mapa.get(s, "cinza")


def detect_col(df: pd.DataFrame, options: list[str]) -> str | None:
    lookup = {str(c).lower(): c for c in df.columns}
    for option in options:
        if option.lower() in lookup:
            return lookup[option.lower()]
    return None


def numeric_metric(df: pd.DataFrame, col: str, agg: str = "max"):
    if df.empty or col not in df.columns:
        return None
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    if s.empty:
        return None
    if agg == "mean":
        return float(s.mean())
    if agg == "sum":
        return float(s.sum())
    return float(s.max())


def fmt(value, suffix: str = "", digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digits}f}{suffix}"


def prepare_resumo() -> tuple[pd.DataFrame, dict[str, str | None]]:
    resumo = load_csv("resumo_municipal_atual.csv")
    cols = {
        "municipio": detect_col(resumo, ["municipio", "Município", "nome_municipio"]),
        "regional": detect_col(resumo, ["regional_saude", "regional", "regiao_saude"]),
        "nivel": detect_col(resumo, ["nivel_operacional", "nivel", "alerta_nivel", "estagio"]),
        "cod_ibge": detect_col(resumo, ["cod_ibge", "ibge", "codigo_ibge"]),
    }
    if not resumo.empty:
        if cols["nivel"]:
            resumo["nivel_norm"] = resumo[cols["nivel"]].apply(normalize_level)
        else:
            resumo["nivel_norm"] = "cinza"
    return resumo, cols


st.set_page_config(page_title="SIS Clima-Saúde MT", page_icon="🌡️", layout="wide")

resumo, cols = prepare_resumo()

st.title("🌡️ SIS Integrado Clima-Saúde MT")
st.caption(
    "Versão cloud baseada em dados exportados da rotina local. "
    "Não acessa SQL Server interno, IndicaSUS, Datawarehouse, .env ou SQLite operacional."
)

if resumo.empty:
    st.error("Arquivo data/public/resumo_municipal_atual.csv não encontrado ou vazio.")
    st.info("Rode EXPORTAR_DADOS_PUBLICOS_CLOUD_V11_24.cmd na pasta operacional e faça novo push.")
    st.stop()

with st.sidebar:
    st.header("Filtros globais")

    df_filtrado = resumo.copy()

    if cols["regional"]:
        regionais = sorted(df_filtrado[cols["regional"]].dropna().astype(str).unique())
        selecionadas = st.multiselect("Regional de Saúde", regionais)
        if selecionadas:
            df_filtrado = df_filtrado[df_filtrado[cols["regional"]].astype(str).isin(selecionadas)]

    if cols["municipio"]:
        municipios = sorted(df_filtrado[cols["municipio"]].dropna().astype(str).unique())
        selecionados = st.multiselect("Município", municipios)
        if selecionados:
            df_filtrado = df_filtrado[df_filtrado[cols["municipio"]].astype(str).isin(selecionados)]

    st.divider()
    st.caption("Dados publicados em data/public.")

df = df_filtrado.copy()
nivel_estadual = "cinza"
if not df.empty:
    nivel_estadual = max(df["nivel_norm"], key=lambda x: ORDEM.get(x, 0))

cor = CORES.get(nivel_estadual, CORES["cinza"])

st.markdown(
    f"""
    <div style="background:{cor};padding:24px;border-radius:12px;color:white;margin-bottom:18px">
      <h2 style="margin:0">NÍVEL OPERACIONAL ESTADUAL: {nivel_estadual.upper()}</h2>
      <p style="margin-top:8px">Painel municipalizado para apoio à decisão em clima e saúde.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Municípios", len(df))
m2.metric("Tmax máx.", fmt(numeric_metric(df, "tmax"), " °C"))
m3.metric("UTCI máx.", fmt(numeric_metric(df, "utci_proxy")))
m4.metric("Risco 3d máx.", fmt(numeric_metric(df, "risco_cumulativo_3d"), digits=2))
m5.metric("Ocupação média", fmt(numeric_metric(df, "ocupacao_leitos_pct", "mean"), "%"))
m6.metric("PM2.5 máx.", fmt(numeric_metric(df, "pm25_ugm3")))

st.subheader("Distribuição por nível operacional")
dist = df["nivel_norm"].value_counts().reindex(["verde", "amarela", "laranja", "vermelha", "roxa", "cinza"]).fillna(0).astype(int)
cols_metric = st.columns(6)
for i, nivel in enumerate(dist.index):
    cols_metric[i].metric(nivel.capitalize(), int(dist[nivel]))

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Visão executiva", "Mapa municipal", "Predição 7 dias", "GeoCalor cardiorrespiratório", "Dados"]
)

with tab1:
    st.subheader("Ranking operacional")
    rank = df.copy()
    rank["nivel_ordem"] = rank["nivel_norm"].map(ORDEM).fillna(0)
    preferidas = [
        cols["municipio"],
        cols["regional"],
        "nivel_norm",
        "tmax",
        "utci_proxy",
        "risco_cumulativo_3d",
        "ocupacao_leitos_pct",
        "pressao_calor_pct",
        "pm25_ugm3",
    ]
    mostrar = [c for c in preferidas if c and c in rank.columns]
    ordenar = [c for c in ["nivel_ordem", "risco_cumulativo_3d"] if c in rank.columns]
    if ordenar:
        rank = rank.sort_values(ordenar, ascending=False)
    st.dataframe(rank[mostrar] if mostrar else rank, use_container_width=True)

with tab2:
    st.subheader("Mapa municipal")
    geo_path = PUBLIC / "municipios_mt_2025_simplificado.geojson"
    if geo_path.exists() and cols["cod_ibge"]:
        try:
            geojson = json.loads(geo_path.read_text(encoding="utf-8"))
            map_df = df.copy()
            map_df[cols["cod_ibge"]] = map_df[cols["cod_ibge"]].astype(str)
            fig = px.choropleth_map(
                map_df,
                geojson=geojson,
                locations=cols["cod_ibge"],
                featureidkey="properties.CD_MUN",
                color="nivel_norm",
                hover_name=cols["municipio"] if cols["municipio"] else None,
                color_discrete_map=CORES,
                map_style="carto-positron",
                zoom=4.7,
                center={"lat": -12.8, "lon": -55.8},
                height=650,
            )
            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig, use_container_width=True)
        except Exception as exc:
            st.warning(f"Não foi possível renderizar o mapa: {exc}")
            st.dataframe(df, use_container_width=True)
    else:
        st.info("GeoJSON municipal ou coluna cod_ibge não disponível. Exibindo tabela.")
        st.dataframe(df, use_container_width=True)

with tab3:
    st.subheader("Predição 7 dias")
    pred = load_csv("predicao_calor_7d_municipal_v6.csv")
    if pred.empty:
        st.info("Tabela predicao_calor_7d_municipal_v6.csv não disponível.")
    else:
        nivel_pred = detect_col(pred, ["nivel_predicao_7d"])
        if nivel_pred:
            pred[nivel_pred] = pred[nivel_pred].apply(normalize_level)
        st.dataframe(pred, use_container_width=True)

with tab4:
    st.subheader("GeoCalor cardiorrespiratório")
    status = load_csv("geocalor_status_modelagem_v11_12.csv")
    cuiaba = load_csv("geocalor_cuiaba_cardioresp_v11_12.csv")
    rr = load_csv("geocalor_cardioresp_rr_municipal_v11_12.csv")

    if not status.empty:
        st.markdown("### Status da modelagem")
        st.dataframe(status, use_container_width=True)

    if not cuiaba.empty:
        st.markdown("### Cuiabá")
        st.dataframe(cuiaba, use_container_width=True)

    if not rr.empty:
        st.markdown("### Resultados municipais")
        mun_col = detect_col(rr, ["municipio"])
        rr_filtrado = rr.copy()
        if mun_col:
            municipios_geo = sorted(rr[mun_col].dropna().astype(str).unique())
            idx = municipios_geo.index("Cuiabá") if "Cuiabá" in municipios_geo else 0
            sel = st.selectbox("Município", municipios_geo, index=idx)
            rr_filtrado = rr[rr[mun_col].astype(str) == sel]
        st.dataframe(rr_filtrado, use_container_width=True)

    st.info(
        "Sem base diária com isHW e desfechos cardiorrespiratórios, "
        "o sistema registra dados insuficientes e não apresenta RR local."
    )

with tab5:
    st.subheader("Bases publicadas")
    st.markdown("### Resumo municipal")
    st.dataframe(df, use_container_width=True)

    for fname, label in [
        ("alerta_inteligente_municipal_v6.csv", "Alerta inteligente"),
        ("v9_priorizacao_epidemiologica.csv", "Priorização epidemiológica V9"),
        ("qualidade_ar_municipal.csv", "Qualidade do ar"),
        ("hospital_ocupacao_municipio.csv", "Ocupação hospitalar"),
        ("ops_resumo_operacional_cnes.csv", "Operacional CNES"),
    ]:
        data = load_csv(fname)
        with st.expander(label):
            if data.empty:
                st.info(f"{fname} não disponível.")
            else:
                st.dataframe(data, use_container_width=True)
