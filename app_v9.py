# -*- coding: utf-8 -*-
"""
SIS Integrado Clima-Saúde MT - Dashboard V9

Melhorias da V6:
- Filtros globais por Regional de Saúde e Município.
- Indicadores estaduais no topo da página, antes das abas.
- Primeira aba com mapa municipal por shapefile, colorido por nível de risco.
- Mapas por polígono municipal para risco, clima, ocupação, pressão, qualidade do ar e vulnerabilidade.
- Deduplicação municipal na aba Geografia.
- Tratamento robusto de municipio_x/municipio_y e regional_saude_x/regional_saude_y.
- Aba metodológica explicando cálculos e indicadores.

Rodar:
.venv\\Scripts\\python.exe -m streamlit run app_v9.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st


DB_PATH = Path("data/output/sis_integrado.db")
CENTER_MT = {"lat": -12.9, "lon": -55.8}

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]
LEVEL_COLOR_MAP = {
    "cinza": "#6b7280",
    "verde": "#16803c",
    "amarela": "#d6a100",
    "laranja": "#f97316",
    "vermelha": "#dc2626",
    "roxa": "#7e22ce",
}


st.set_page_config(
    page_title="SIS Integrado Clima-Saúde MT",
    page_icon="🌡️",
    layout="wide",
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def load_table(table_name: str) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(DB_PATH) as con:
            exists = pd.read_sql(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                con,
                params=(table_name,),
            )
            if exists.empty:
                return pd.DataFrame()
            return pd.read_sql(f"SELECT * FROM {table_name}", con)
    except Exception as exc:
        st.warning(f"Não foi possível carregar {table_name}: {exc}")
        return pd.DataFrame()


def table_count(table_name: str) -> int:
    if not DB_PATH.exists():
        return 0
    try:
        with sqlite3.connect(DB_PATH) as con:
            return int(pd.read_sql(f"SELECT COUNT(*) n FROM {table_name}", con).iloc[0]["n"])
    except Exception:
        return 0


def normalize_cod_ibge(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{7})", expand=False)


def ensure_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def first_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def coalesce_columns(df: pd.DataFrame, target: str, candidates: list[str]) -> pd.DataFrame:
    out = df.copy()
    if target not in out.columns:
        out[target] = pd.NA
    for c in candidates:
        if c in out.columns:
            out[target] = out[target].fillna(out[c])
    return out


def safe_metric_value(value, suffix: str = "", digits: int = 1) -> str:
    try:
        if pd.isna(value):
            return "—"
        return f"{float(value):.{digits}f}{suffix}"
    except Exception:
        return "—"


def normalize_level(level: str) -> str:
    if pd.isna(level):
        return "cinza"
    text = str(level).strip().lower()
    if text in set(LEVEL_ORDER):
        return text
    return text or "cinza"


def level_score(level: str) -> int:
    return {
        "cinza": -1,
        "verde": 0,
        "amarela": 1,
        "laranja": 2,
        "vermelha": 3,
        "roxa": 4,
    }.get(normalize_level(level), 0)


def banner_color(level: str) -> str:
    return LEVEL_COLOR_MAP.get(normalize_level(level), "#334155")


def replace_motivo_indisponivel(row: pd.Series) -> str:
    motivo = "" if pd.isna(row.get("motivo")) else str(row.get("motivo"))
    if "ocupação de leitos indisponível" in motivo.lower() and pd.notna(row.get("ocupacao_leitos_pct")):
        motivo = motivo.replace(
            "ocupação de leitos indisponível",
            f"ocupação de leitos {float(row.get('ocupacao_leitos_pct')):.2f} sem gatilho",
        )
    if "pressão assistencial indisponível" in motivo.lower() and pd.notna(row.get("pressao_calor_pct")):
        motivo = motivo.replace(
            "pressão assistencial indisponível",
            f"pressão assistencial proxy {float(row.get('pressao_calor_pct')):.2f}%",
        )
    return motivo


@st.cache_data(show_spinner=False)
def load_shapefile_geojson() -> tuple[Optional[dict], pd.DataFrame, str]:
    try:
        import geopandas as gpd
    except Exception as exc:
        return None, pd.DataFrame(), f"geopandas não disponível: {exc}"

    candidates = [
        Path("data/geo/municipios_mt/MT_Municipios_2025.shp"),
        Path("data/geo/MT_Municipios_2025.shp"),
        Path("data/input/MT_Municipios_2025.shp"),
        Path("MT_Municipios_2025.shp"),
    ]
    candidates.extend(list(Path("data").rglob("*Municipios*.shp")))
    candidates.extend(list(Path("data").rglob("*MUNICIP*.shp")))
    candidates = list(dict.fromkeys(candidates))

    shp = None
    for path in candidates:
        if path.exists():
            shp = path
            break
    if shp is None:
        return None, pd.DataFrame(), "Shapefile municipal não encontrado em data/."

    try:
        gdf = gpd.read_file(shp)
        if gdf.empty:
            return None, pd.DataFrame(), f"Shapefile vazio: {shp}"

        if gdf.crs is not None:
            gdf = gdf.to_crs(epsg=4326)

        cod_col = first_col(
            gdf,
            [
                "cod_ibge", "CD_MUN", "CD_MUNGE", "CD_GEOCMU", "GEOCODIGO",
                "GEOCODIG_M", "cod_mun", "codigo_ibge", "CodigoIBGE", "codigo",
            ],
        )
        if cod_col is None:
            for c in gdf.columns:
                if c == "geometry":
                    continue
                vals = gdf[c].astype(str).str.extract(r"(\d{7})", expand=False)
                if vals.notna().sum() >= 100:
                    cod_col = c
                    break

        if cod_col is None:
            return None, pd.DataFrame(), f"Não encontrei coluna de código IBGE no shapefile: {shp}"

        gdf["cod_ibge"] = normalize_cod_ibge(gdf[cod_col])
        gdf = gdf[gdf["cod_ibge"].notna()].copy()
        gdf = gdf.drop_duplicates("cod_ibge")

        mun_col = first_col(
            gdf,
            [
                "municipio", "NM_MUN", "NM_MUNICIP", "NOME", "Nome",
                "name", "nome_municipio", "municipio_x", "municipio_y",
            ],
        )
        if mun_col:
            gdf["municipio_shape"] = gdf[mun_col].astype(str)
        else:
            gdf["municipio_shape"] = gdf["cod_ibge"]

        geojson = json.loads(gdf[["cod_ibge", "municipio_shape", "geometry"]].to_json())
        attrs = pd.DataFrame(gdf.drop(columns="geometry"))
        return geojson, attrs, f"Shapefile carregado: {shp} | municípios: {len(attrs)}"
    except Exception as exc:
        return None, pd.DataFrame(), f"Erro ao carregar shapefile: {exc}"


def prepare_resumo() -> pd.DataFrame:
    resumo = load_table("resumo_municipal_atual")
    if resumo.empty:
        return resumo

    resumo = resumo.copy()
    if "cod_ibge" in resumo.columns:
        resumo["cod_ibge"] = normalize_cod_ibge(resumo["cod_ibge"])

    resumo = coalesce_columns(
        resumo,
        "municipio",
        ["municipio", "municipio_x", "municipio_y", "municipio_base", "municipio_indicasus", "municipio_shape"],
    )
    resumo["municipio"] = resumo["municipio"].fillna(resumo.get("cod_ibge", "Município")).astype(str)

    resumo = coalesce_columns(
        resumo,
        "regional_saude",
        ["regional_saude", "regional_saude_x", "regional_saude_y", "regiao_saude", "RegiaoSaude", "regiao"],
    )
    resumo["regional_saude"] = resumo["regional_saude"].fillna("Regional não informada").astype(str)

    resumo = coalesce_columns(
        resumo,
        "macroregiao_saude",
        ["macroregiao_saude", "macroregiao_saude_x", "macroregiao_saude_y", "macro"],
    )

    if "nivel" in resumo.columns:
        resumo["nivel"] = resumo["nivel"].apply(normalize_level)
    else:
        resumo["nivel"] = "cinza"

    if "score" not in resumo.columns:
        resumo["score"] = resumo["nivel"].apply(level_score)

    numeric_cols = [
        "score", "tmax", "tmin", "tmedia", "utci_proxy", "heat_index",
        "risco_calor_diario", "risco_cumulativo_3d", "pressao_calor_pct",
        "pressao_assistencial_pct", "ocupacao_leitos_pct", "leitos_total",
        "leitos_ocupados", "leitos_livres", "pm25_ugm3", "pm10_ugm3",
        "o3_ugm3", "no2_ugm3", "iq_ar_score", "indice_vulnerabilidade_calor",
        "autonomia_min_dias", "falhas_infra_pct", "indice_resiliencia",
    ]
    resumo = ensure_numeric(resumo, numeric_cols)

    sort_cols = [c for c in ["score", "risco_cumulativo_3d", "ocupacao_leitos_pct"] if c in resumo.columns]
    if sort_cols and "cod_ibge" in resumo.columns:
        resumo = resumo.sort_values(sort_cols, ascending=[False] * len(sort_cols))
        resumo = resumo.drop_duplicates("cod_ibge", keep="first")

    if "motivo" in resumo.columns:
        resumo["motivo"] = resumo.apply(replace_motivo_indisponivel, axis=1)

    return resumo


def prepare_map_df(resumo: pd.DataFrame) -> tuple[pd.DataFrame, Optional[dict], str]:
    geojson, attrs, status = load_shapefile_geojson()
    if resumo.empty:
        return resumo, geojson, status

    df = resumo.copy()
    if not attrs.empty and "cod_ibge" in attrs.columns and "cod_ibge" in df.columns:
        keep_attrs = [c for c in ["cod_ibge", "municipio_shape"] if c in attrs.columns]
        df = df.merge(attrs[keep_attrs].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        if "municipio_shape" in df.columns:
            df["municipio"] = df["municipio"].fillna(df["municipio_shape"])
    return df, geojson, status


def apply_global_filters(df: pd.DataFrame, regionais: list[str], municipios: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "regional_saude" in out.columns and regionais:
        out = out[out["regional_saude"].isin(regionais)]
    if "municipio" in out.columns and municipios:
        out = out[out["municipio"].isin(municipios)]
    return out


def choropleth_or_points(
    df: pd.DataFrame,
    geojson: Optional[dict],
    color_col: str,
    title: str,
    hover_cols: Optional[list[str]] = None,
    categorical: bool = False,
):
    if df.empty:
        st.info("Sem dados para este mapa com os filtros selecionados.")
        return

    hover_cols = hover_cols or []
    df = df.copy()

    for c in [color_col] + hover_cols:
        if c in df.columns and c not in ["nivel", "municipio", "cod_ibge", "fonte_ocupacao", "regional_saude"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if categorical and color_col in df.columns:
        df[color_col] = df[color_col].apply(normalize_level)

    if geojson is not None and "cod_ibge" in df.columns:
        plot_df = df[df["cod_ibge"].notna()].copy()
        if plot_df.empty:
            st.info("Sem código IBGE para cruzamento com shapefile.")
            return

        if categorical:
            fig = px.choropleth_mapbox(
                plot_df,
                geojson=geojson,
                locations="cod_ibge",
                featureidkey="properties.cod_ibge",
                color=color_col,
                category_orders={color_col: LEVEL_ORDER},
                color_discrete_map=LEVEL_COLOR_MAP,
                hover_name="municipio",
                hover_data=[c for c in hover_cols if c in plot_df.columns],
                center=CENTER_MT,
                zoom=4.5,
                opacity=0.72,
                height=660,
                mapbox_style="carto-positron",
                title=title,
            )
        else:
            fig = px.choropleth_mapbox(
                plot_df,
                geojson=geojson,
                locations="cod_ibge",
                featureidkey="properties.cod_ibge",
                color=color_col,
                hover_name="municipio",
                hover_data=[c for c in hover_cols if c in plot_df.columns],
                center=CENTER_MT,
                zoom=4.5,
                opacity=0.72,
                height=660,
                mapbox_style="carto-positron",
                title=title,
            )
        fig.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
        st.plotly_chart(fig, use_container_width=True)
        return

    if {"lat", "lon"}.issubset(df.columns):
        plot_df = df.dropna(subset=["lat", "lon"]).copy()
        if plot_df.empty:
            st.info("Sem lat/lon para mapa de pontos.")
            return
        fig = px.scatter_mapbox(
            plot_df,
            lat="lat",
            lon="lon",
            color=color_col if color_col in plot_df.columns else None,
            color_discrete_map=LEVEL_COLOR_MAP if categorical else None,
            hover_name="municipio" if "municipio" in plot_df.columns else None,
            hover_data=[c for c in hover_cols if c in plot_df.columns],
            center=CENTER_MT,
            zoom=4.5,
            height=660,
            mapbox_style="carto-positron",
            title=title,
        )
        fig.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem shapefile e sem lat/lon para mapa.")


def show_df(df: pd.DataFrame, cols: Optional[list[str]] = None, height: int = 420):
    if df.empty:
        st.info("Sem dados com os filtros selecionados.")
        return
    if cols:
        cols = [c for c in cols if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, height=height)
    else:
        st.dataframe(df, use_container_width=True, height=height)


def make_bar(df: pd.DataFrame, x: str, y: str, title: str, top: int = 20):
    if df.empty or x not in df.columns or y not in df.columns:
        st.info(f"Sem dados para gráfico: {title}")
        return
    plot = df[[x, y]].copy()
    plot[y] = pd.to_numeric(plot[y], errors="coerce")
    plot = plot.dropna(subset=[y]).sort_values(y, ascending=False).head(top)
    if plot.empty:
        st.info(f"Sem valores numéricos para gráfico: {title}")
        return
    fig = px.bar(plot, x=x, y=y, title=title)
    st.plotly_chart(fig, use_container_width=True)


def make_line(df: pd.DataFrame, date_col: str, value_cols: list[str], title: str, group_col: str = "municipio"):
    if df.empty or date_col not in df.columns:
        st.info(f"Sem dados temporais para gráfico: {title}")
        return

    plot = df.copy()
    plot[date_col] = pd.to_datetime(plot[date_col], errors="coerce")
    vals = [c for c in value_cols if c in plot.columns]
    for c in vals:
        plot[c] = pd.to_numeric(plot[c], errors="coerce")

    if not vals:
        st.info(f"Sem colunas numéricas para gráfico: {title}")
        return

    id_vars = [date_col]
    if group_col in plot.columns:
        id_vars.append(group_col)

    long = plot.melt(id_vars=id_vars, value_vars=vals, var_name="indicador", value_name="valor")
    long = long.dropna(subset=[date_col, "valor"])
    if long.empty:
        st.info(f"Sem valores válidos para gráfico: {title}")
        return

    if group_col in long.columns:
        long["serie"] = long[group_col].astype(str) + " - " + long["indicador"].astype(str)
        color_col = "serie"
    else:
        color_col = "indicador"

    fig = px.line(long, x=date_col, y="valor", color=color_col, title=title)
    st.plotly_chart(fig, use_container_width=True)


def state_summary_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    scores = pd.to_numeric(df.get("score", pd.Series(dtype=float)), errors="coerce").fillna(0)
    out = {
        "municipios": df["cod_ibge"].nunique() if "cod_ibge" in df.columns else len(df),
        "verde": int((df["nivel"] == "verde").sum()) if "nivel" in df.columns else 0,
        "amarela": int((df["nivel"] == "amarela").sum()) if "nivel" in df.columns else 0,
        "laranja": int((df["nivel"] == "laranja").sum()) if "nivel" in df.columns else 0,
        "vermelha": int((df["nivel"] == "vermelha").sum()) if "nivel" in df.columns else 0,
        "roxa": int((df["nivel"] == "roxa").sum()) if "nivel" in df.columns else 0,
        "criticos": int((scores >= 2).sum()),
        "tmax": df["tmax"].max() if "tmax" in df.columns else pd.NA,
        "utci": df["utci_proxy"].max() if "utci_proxy" in df.columns else pd.NA,
        "risco3d": df["risco_cumulativo_3d"].max() if "risco_cumulativo_3d" in df.columns else pd.NA,
        "ocup_media": df["ocupacao_leitos_pct"].mean() if "ocupacao_leitos_pct" in df.columns else pd.NA,
        "ocup_max": df["ocupacao_leitos_pct"].max() if "ocupacao_leitos_pct" in df.columns else pd.NA,
        "pressao_media": df["pressao_calor_pct"].mean() if "pressao_calor_pct" in df.columns else pd.NA,
        "pressao_max": df["pressao_calor_pct"].max() if "pressao_calor_pct" in df.columns else pd.NA,
        "pm25_max": df["pm25_ugm3"].max() if "pm25_ugm3" in df.columns else pd.NA,
        "iqar_max": df["iq_ar_score"].max() if "iq_ar_score" in df.columns else pd.NA,
    }
    return out


# ---------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------

resumo_all = prepare_resumo()
map_df_all, geojson_mun, shapefile_status = prepare_map_df(resumo_all)

met = load_table("met_biometeo")
aq = load_table("qualidade_ar_municipal")
occ = load_table("hospital_ocupacao_municipio")
press = load_table("epi_pressao_assistencial")
stock = load_table("ops_estoque_autonomia")
infra = load_table("ops_infraestrutura_resumo")
ops_proxy = load_table("ops_resumo_operacional_proxy")
ops_cnes = load_table("ops_resumo_operacional_cnes")
saude_calor_mun = load_table("saude_calor_municipio")
saude_calor_serie = load_table("saude_calor_serie_estado")
saude_dic = load_table("dicionario_monitoramento_saude_v6")
gal_pos_mun = load_table("gal_positividade_municipal_v6")
gal_pos_serie = load_table("gal_positividade_estado_serie_v6")
sim_obitos_mun = load_table("sim_obitos_calor_municipal_v6")
sim_obitos_serie = load_table("sim_obitos_calor_estado_serie_v6")
aq_estado_serie = load_table("qualidade_ar_estado_serie_v6")
alerta_mun_v6 = load_table("alerta_inteligente_municipal_v6")
alerta_reg_v6 = load_table("alerta_inteligente_regional_v6")
pred_v6 = load_table("predicao_calor_7d_municipal_v6")
pred_reg_v6 = load_table("predicao_calor_7d_regional_v6")
analise_base_v8 = load_table("analise_clima_saude_base_municipal_v8")
analise_corr_v8 = load_table("analise_clima_saude_correlacoes_v8")
analise_alertas_v8 = load_table("analise_clima_saude_alertas_estatisticos_v8")
validacao_v75 = load_table("validacao_v7_5")
v9_status = load_table("v9_status_modelagem_temporal")
v9_validacao = load_table("v9_validacao")
v9_saude_mensal = load_table("v9_painel_saude_municipal_mensal")
v9_clima = load_table("v9_clima_municipal_mensal_detectado")
v9_painel = load_table("v9_painel_clima_saude_mensal")
v9_lags = load_table("v9_lags_clima_saude")
v9_modelos = load_table("v9_modelos_temporais")
v9_priorizacao = load_table("v9_priorizacao_epidemiologica")

for df in [met, aq, occ, press, stock, infra, ops_cnes, saude_calor_mun, gal_pos_mun, sim_obitos_mun, alerta_mun_v6, pred_v6, pred_reg_v6, analise_base_v8, analise_alertas_v8, v9_saude_mensal, v9_clima, v9_painel, v9_priorizacao]:
    if not df.empty and "cod_ibge" in df.columns:
        df["cod_ibge"] = normalize_cod_ibge(df["cod_ibge"])


# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------

st.title("🌡️ SIS Integrado Clima-Saúde MT")
st.caption("Monitoramento municipalizado: TITAN + SENTINELA + AESOP + SIVEP + LACEN + IndicaSUS + Copernicus/CAMS + INMET + Vigidesastres")

if resumo_all.empty:
    st.error("A tabela resumo_municipal_atual não foi encontrada ou está vazia. Rode o pipeline antes de abrir o painel.")
    st.stop()

resumo_all["score"] = pd.to_numeric(resumo_all.get("score", 0), errors="coerce").fillna(0)
sentinel = resumo_all.sort_values(["score", "risco_cumulativo_3d"], ascending=[False, False]).iloc[0]
nivel_estado = normalize_level(sentinel.get("nivel"))
municipio_sentinel = sentinel.get("municipio", "—")
motivo_estado = replace_motivo_indisponivel(sentinel)

st.markdown(
    f"""
    <div style="background:{banner_color(nivel_estado)};color:white;padding:22px;border-radius:10px;margin-bottom:14px">
        <h2 style="margin:0">NÍVEL OPERACIONAL ESTADUAL: {nivel_estado.upper()}</h2>
        <p style="margin:10px 0 4px 0"><b>Município sentinela/mais crítico:</b> {municipio_sentinel}</p>
        <p style="margin:0;font-size:0.95rem">{motivo_estado}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Indicadores estaduais gerais antes dos filtros e abas
metrics = state_summary_metrics(resumo_all)
st.markdown("### Situação geral do Estado")
r1 = st.columns(8)
r1[0].metric("Municípios monitorados", f"{metrics.get('municipios', 0)}")
r1[1].metric("Tmax máx.", safe_metric_value(metrics.get("tmax"), " °C", 1))
r1[2].metric("UTCI máx.", safe_metric_value(metrics.get("utci"), "", 1))
r1[3].metric("Risco 3d máx.", safe_metric_value(metrics.get("risco3d"), "", 2))
r1[4].metric("Ocupação média", safe_metric_value(metrics.get("ocup_media"), "%", 1))
r1[5].metric("Pressão média", safe_metric_value(metrics.get("pressao_media"), "%", 1))
r1[6].metric("PM2.5 máx.", safe_metric_value(metrics.get("pm25_max"), "", 1))
r1[7].metric("IQA máx.", safe_metric_value(metrics.get("iqar_max"), "", 1))


# Linha única com contagem por cor operacional
st.markdown("### Distribuição por nível operacional")
dist_cols = st.columns(5)
for _idx, (_nivel, _label) in enumerate([
    ("verde", "Verde"),
    ("amarela", "Amarela"),
    ("laranja", "Laranja"),
    ("vermelha", "Vermelha"),
    ("roxa", "Roxa"),
]):
    _valor = metrics.get(_nivel, 0)
    with dist_cols[_idx]:
        st.markdown(
            f"""
            <div style="background:{LEVEL_COLOR_MAP[_nivel]};color:white;padding:14px;border-radius:10px;text-align:center">
                <div style="font-size:0.85rem;font-weight:600">{_label}</div>
                <div style="font-size:1.8rem;font-weight:800">{_valor}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# Filtros globais
with st.sidebar:
    st.header("Filtros globais")
    regionais_disponiveis = sorted(
        [x for x in resumo_all.get("regional_saude", pd.Series(dtype=str)).dropna().astype(str).unique() if x]
    )
    municipios_disponiveis = sorted(
        [x for x in resumo_all.get("municipio", pd.Series(dtype=str)).dropna().astype(str).unique() if x]
    )
    regionais_sel = st.multiselect("Regional de Saúde", regionais_disponiveis, default=[])
    tmp = resumo_all.copy()
    if regionais_sel and "regional_saude" in tmp.columns:
        tmp = tmp[tmp["regional_saude"].isin(regionais_sel)]
    municipios_filtrados = sorted(tmp["municipio"].dropna().astype(str).unique()) if "municipio" in tmp.columns else municipios_disponiveis
    municipios_sel = st.multiselect("Município", municipios_filtrados, default=[])

    st.divider()
    st.caption("Os indicadores no topo são estaduais gerais. As abas e mapas abaixo respeitam estes filtros.")
    st.caption(shapefile_status)

resumo = apply_global_filters(resumo_all, regionais_sel, municipios_sel)
map_df = apply_global_filters(map_df_all, regionais_sel, municipios_sel)


tabs = st.tabs([
    "Visão executiva",
    "Mapas municipais",
    "Clima/TITAN",
    "Assistência/IndicaSUS/AESOP",
    "Qualidade do ar/Copernicus",
    "Operacional",
    "Geografia",
    "Cálculos e indicadores",
    "Inteligência e alertas",
    "Alertas e auditoria",
])


# ---------------------------------------------------------------------
# Tab 1
# ---------------------------------------------------------------------
with tabs[0]:
    st.subheader("Mapa municipal por nível operacional")
    st.info(shapefile_status)

    choropleth_or_points(
        map_df,
        geojson_mun,
        "nivel",
        "Nível operacional municipal por shapefile",
        hover_cols=[
            "regional_saude", "score", "tmax", "utci_proxy", "risco_cumulativo_3d",
            "ocupacao_leitos_pct", "pressao_calor_pct", "motivo",
        ],
        categorical=True,
    )

    st.markdown("#### Municípios priorizados")
    cols = [
        "cod_ibge", "municipio", "regional_saude", "nivel", "score", "tmax", "utci_proxy",
        "risco_cumulativo_3d", "ocupacao_leitos_pct", "pressao_calor_pct",
        "qualidade_ar_nivel", "motivo",
    ]
    show_df(resumo.sort_values(["score", "risco_cumulativo_3d"], ascending=[False, False]), cols, height=520)


# ---------------------------------------------------------------------
# Tab 2
# ---------------------------------------------------------------------
with tabs[1]:
    st.subheader("Mapas municipais por shapefile/polígono")

    st.markdown("#### Mapa principal selecionável")
    indicadores = {
        "Nível operacional / risco": "nivel",
        "Score operacional": "score",
        "Risco cumulativo 3 dias": "risco_cumulativo_3d",
        "UTCI proxy": "utci_proxy",
        "Temperatura máxima": "tmax",
        "Ocupação de leitos IndicaSUS": "ocupacao_leitos_pct",
        "Pressão assistencial proxy": "pressao_calor_pct",
        "Vulnerabilidade ao calor": "indice_vulnerabilidade_calor",
        "PM2.5": "pm25_ugm3",
        "Índice de qualidade do ar": "iq_ar_score",
    }
    label = st.selectbox("Indicador do mapa", list(indicadores.keys()))
    col = indicadores[label]
    if col not in map_df.columns:
        st.warning(f"O indicador {col} ainda não está disponível no resumo municipal.")
    else:
        choropleth_or_points(
            map_df,
            geojson_mun,
            col,
            label,
            hover_cols=[
                "regional_saude", "nivel", "score", "tmax", "utci_proxy", "risco_cumulativo_3d",
                "ocupacao_leitos_pct", "pressao_calor_pct", "indice_vulnerabilidade_calor",
                "pm25_ugm3", "iq_ar_score",
            ],
            categorical=(col == "nivel"),
        )

    st.markdown("#### Painel de mapas temáticos")
    mapas_tematicos = [
        ("Risco cumulativo 3 dias", "risco_cumulativo_3d"),
        ("Ocupação de leitos IndicaSUS", "ocupacao_leitos_pct"),
        ("Pressão assistencial proxy", "pressao_calor_pct"),
        ("Vulnerabilidade ao calor", "indice_vulnerabilidade_calor"),
        ("PM2.5", "pm25_ugm3"),
        ("Índice de qualidade do ar", "iq_ar_score"),
    ]
    for _titulo, _col in mapas_tematicos:
        with st.expander(_titulo, expanded=False):
            if _col in map_df.columns:
                choropleth_or_points(
                    map_df,
                    geojson_mun,
                    _col,
                    _titulo,
                    hover_cols=["regional_saude", "nivel", "score", "risco_cumulativo_3d", "ocupacao_leitos_pct", "pressao_calor_pct"],
                )
            else:
                st.info(f"Indicador {_col} ainda não disponível.")


# ---------------------------------------------------------------------
# Tab 3
# ---------------------------------------------------------------------
with tabs[2]:
    st.subheader("Clima, biometeorologia e risco cumulativo")

    met_f = met.copy()
    if not met_f.empty and "cod_ibge" in met_f.columns and "cod_ibge" in resumo.columns:
        met_f = met_f[met_f["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
    elif not met_f.empty and municipios_sel and "municipio" in met_f.columns:
        met_f = met_f[met_f["municipio"].isin(municipios_sel)]

    if not met_f.empty:
        met_f = ensure_numeric(met_f, ["tmax", "tmin", "tmedia", "utci_proxy", "risco_cumulativo_3d", "heat_index"])
        if "data" in met_f.columns:
            met_f["data"] = pd.to_datetime(met_f["data"], errors="coerce")

        col_a, col_b = st.columns(2)
        with col_a:
            make_bar(resumo, "municipio", "risco_cumulativo_3d", "Top risco cumulativo 3 dias")
        with col_b:
            make_bar(resumo, "municipio", "utci_proxy", "Top UTCI proxy")

        municipios = sorted(met_f["municipio"].dropna().astype(str).unique()) if "municipio" in met_f.columns else []
        default_muns = municipios[:8]
        selected = st.multiselect("Municípios no gráfico temporal de clima", municipios, default=default_muns)
        plot_met = met_f[met_f["municipio"].isin(selected)] if selected and "municipio" in met_f.columns else met_f
        make_line(
            plot_met,
            "data",
            ["tmax", "tmedia", "utci_proxy", "risco_cumulativo_3d"],
            "Série temporal climática e biometeorológica",
        )

        show_df(
            resumo.sort_values("risco_cumulativo_3d", ascending=False),
            ["cod_ibge", "municipio", "regional_saude", "nivel", "score", "tmax", "tmedia", "utci_proxy", "risco_cumulativo_3d", "onda_calor_p95_2d", "motivo"],
        )
    else:
        st.info("Tabela met_biometeo não disponível para os filtros selecionados.")


# ---------------------------------------------------------------------
# Tab 4
# ---------------------------------------------------------------------
with tabs[3]:
    st.subheader("Assistência, ocupação IndicaSUS e pressão assistencial")

    col_a, col_b = st.columns(2)
    with col_a:
        make_bar(resumo, "municipio", "pressao_calor_pct", "Pressão assistencial proxy - Top")
    with col_b:
        make_bar(resumo, "municipio", "ocupacao_leitos_pct", "Ocupação de leitos IndicaSUS - Top")

    st.markdown("#### Mapa da ocupação de leitos")
    choropleth_or_points(
        map_df,
        geojson_mun,
        "ocupacao_leitos_pct",
        "Ocupação de leitos IndicaSUS",
        hover_cols=["regional_saude", "nivel", "score", "leitos_total", "leitos_ocupados", "pressao_calor_pct"],
    )

    st.markdown("#### Mapa da pressão assistencial")
    choropleth_or_points(
        map_df,
        geojson_mun,
        "pressao_calor_pct",
        "Pressão assistencial proxy",
        hover_cols=["regional_saude", "nivel", "score", "ocupacao_leitos_pct", "risco_cumulativo_3d", "utci_proxy"],
    )


    st.markdown("#### Dicionário do monitoramento saúde-calor")
    show_df(saude_dic, ["fonte", "base_dw", "agravo_monitorado", "grupo_agravo_calor"], height=260)

    st.markdown("#### GAL/LACEN — taxa de positividade")
    if not gal_pos_serie.empty:
        gp = gal_pos_serie.copy()
        if "mes" in gp.columns:
            gp["mes"] = pd.to_datetime(gp["mes"].astype(str) + "-01", errors="coerce")
            fig = px.line(gp, x="mes", y="positividade_pct", color="agravo_exame", title="Taxa de positividade GAL/LACEN — série estadual")
            st.plotly_chart(fig, use_container_width=True)
    show_df(gal_pos_mun, ["cod_ibge", "agravo_exame", "testes", "positivos", "positividade_pct"], height=300)

    st.markdown("#### SIM — óbitos monitorados por grupo CID")
    if not sim_obitos_serie.empty:
        so = sim_obitos_serie.copy()
        if "mes" in so.columns:
            so["mes"] = pd.to_datetime(so["mes"].astype(str) + "-01", errors="coerce")
            fig = px.line(so, x="mes", y="obitos", color="grupo_obito_calor", title="Óbitos SIM sensíveis ao calor — série estadual")
            st.plotly_chart(fig, use_container_width=True)
    show_df(sim_obitos_mun, ["cod_ibge", "grupo_obito_calor", "obitos"], height=300)


    st.markdown("#### Agravos e doenças sensíveis ao calor — bases reais disponíveis")
    if not saude_calor_serie.empty:
        serie = saude_calor_serie.copy()
        if "mes" in serie.columns:
            serie["mes"] = pd.to_datetime(serie["mes"].astype(str) + "-01", errors="coerce")
            fig = px.line(
                serie,
                x="mes",
                y="eventos",
                color="grupo_agravo_calor" if "grupo_agravo_calor" in serie.columns else "fonte",
                line_dash="fonte" if "fonte" in serie.columns else None,
                title="Série estadual de agravos sensíveis ao calor por fonte"
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Ainda não foi consolidada série estadual de SINAN/SIM/GAL/SIVEP para agravos sensíveis ao calor. Rode corrigir_resumo_v5_regionais_ar_cnes_saude.py.")

    if not saude_calor_mun.empty:
        mun = saude_calor_mun.copy()
        if "cod_ibge" in mun.columns and "cod_ibge" in resumo.columns:
            mun["cod_ibge"] = normalize_cod_ibge(mun["cod_ibge"])
            mun = mun[mun["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
        show_df(
            mun.sort_values("eventos", ascending=False) if "eventos" in mun.columns else mun,
            ["cod_ibge", "municipio", "regional_saude", "fonte", "grupo_agravo_calor", "eventos"],
            height=360,
        )
    else:
        st.warning("Base consolidada saude_calor_municipio ainda vazia. O app está preparado para SINAN, SIM, GAL/LACEN e SIVEP quando as tabelas estiverem no SQLite.")


    st.markdown("#### Tabela municipal assistencial")
    show_df(
        resumo.sort_values(["ocupacao_leitos_pct", "pressao_calor_pct"], ascending=[False, False]),
        [
            "cod_ibge", "municipio", "regional_saude", "nivel", "score", "ocupacao_leitos_pct",
            "pressao_calor_pct", "leitos_total", "leitos_ocupados", "leitos_livres",
            "fonte_ocupacao", "fonte_pressao", "motivo",
        ],
        height=520,
    )


# ---------------------------------------------------------------------
# Tab 5
# ---------------------------------------------------------------------
with tabs[4]:
    st.subheader("Qualidade do ar - Copernicus/CAMS ou CSV local")

    pols = ["pm25_ugm3", "pm10_ugm3", "o3_ugm3", "no2_ugm3", "co_mgm3", "so2_ugm3", "iq_ar_score"]

    st.markdown("#### Série histórica estadual — média dos municípios")
    estado = aq_estado_serie.copy() if not aq_estado_serie.empty else pd.DataFrame()
    if estado.empty and not aq.empty:
        estado = aq.copy()
        if "data" in estado.columns:
            estado["data"] = pd.to_datetime(estado["data"], errors="coerce")
            for c in pols:
                if c in estado.columns:
                    estado[c] = pd.to_numeric(estado[c], errors="coerce")
            present = [c for c in pols if c in estado.columns]
            estado = estado.groupby("data", as_index=False)[present].mean(numeric_only=True) if present else pd.DataFrame()

    if not estado.empty and "data" in estado.columns:
        estado["data"] = pd.to_datetime(estado["data"], errors="coerce")
        present = [c for c in pols if c in estado.columns]
        long_estado = estado.melt(id_vars=["data"], value_vars=present, var_name="poluente", value_name="valor").dropna(subset=["data", "valor"])
        if long_estado.empty:
            st.info("A série estadual existe, mas sem valores numéricos válidos para PM2.5/IQA.")
        else:
            fig = px.line(long_estado, x="data", y="valor", color="poluente", title="Média estadual diária da qualidade do ar")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Série estadual de qualidade do ar ainda não criada. Rode corrigir_resumo_final_v6.py.")

    st.markdown("#### Série municipal filtrável")
    aq_f = aq.copy()
    if not aq_f.empty and "cod_ibge" in aq_f.columns and "cod_ibge" in resumo.columns:
        aq_f["cod_ibge"] = normalize_cod_ibge(aq_f["cod_ibge"])
        aq_f = aq_f[aq_f["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
    elif not aq_f.empty and municipios_sel and "municipio" in aq_f.columns:
        aq_f = aq_f[aq_f["municipio"].isin(municipios_sel)]

    if aq_f.empty:
        st.info("Tabela qualidade_ar_municipal não disponível para os filtros selecionados.")
    else:
        aq_plot = aq_f.copy()
        if "data" in aq_plot.columns:
            aq_plot["data"] = pd.to_datetime(aq_plot["data"], errors="coerce")
        for c in pols:
            if c in aq_plot.columns:
                aq_plot[c] = pd.to_numeric(aq_plot[c], errors="coerce")
        present_pols = [c for c in pols if c in aq_plot.columns]
        long = aq_plot.melt(
            id_vars=[c for c in ["data", "municipio"] if c in aq_plot.columns],
            value_vars=present_pols,
            var_name="poluente",
            value_name="valor",
        ).dropna(subset=["valor"])
        if not long.empty:
            if "municipio" in long.columns:
                long["serie"] = long["municipio"].astype(str) + " - " + long["poluente"].astype(str)
                color = "serie"
            else:
                color = "poluente"
            fig = px.line(long, x="data" if "data" in long.columns else long.index, y="valor", color=color, title="Série municipal de poluentes")
            st.plotly_chart(fig, use_container_width=True)

        map_col = first_col(map_df, ["iq_ar_score", "pm25_ugm3", "pm10_ugm3", "o3_ugm3"])
        if map_col:
            choropleth_or_points(map_df, geojson_mun, map_col, f"Qualidade do ar - {map_col}", hover_cols=["qualidade_ar_nivel", "poluente_dominante"])
        show_df(aq_plot, height=450)


# ---------------------------------------------------------------------
# Tab 6
# ---------------------------------------------------------------------
with tabs[5]:
    st.subheader("Operacional: estoque, infraestrutura e resiliência")

    c1, c2, c3 = st.columns(3)
    c1.metric("Estoque/logística", "Base específica pendente" if stock.empty else "Integrado")
    c2.metric("CNES operacional", "Integrado" if not ops_cnes.empty else ("Integrado" if not ops_proxy.empty else "Pendente"))
    c3.metric("Índice operacional", "Disponível" if (not ops_cnes.empty or "indice_resiliencia" in resumo.columns) else "Pendente")

    if stock.empty and infra.empty:
        st.info(
            "Estoque logístico real ainda depende de base específica. "
            "A capacidade instalada e infraestrutura assistencial estão sendo representadas por CNES/DW, ocupação IndicaSUS e pressão assistencial."
        )

    ops_base = ops_cnes if not ops_cnes.empty else ops_proxy
    if not ops_base.empty:
        ops_f = ops_base.copy()
        if "cod_ibge" in ops_f.columns and "cod_ibge" in resumo.columns:
            ops_f["cod_ibge"] = normalize_cod_ibge(ops_f["cod_ibge"])
            ops_f = ops_f[ops_f["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
        make_bar(ops_f, "municipio", "prioridade_operacional_proxy", "Prioridade operacional proxy - Top")
        if "indice_capacidade_cnes" in ops_f.columns:
            make_bar(ops_f, "municipio", "indice_capacidade_cnes", "Capacidade instalada CNES - Top")
        show_df(
            ops_f.sort_values("prioridade_operacional_proxy", ascending=False) if "prioridade_operacional_proxy" in ops_f.columns else ops_f,
            ["cod_ibge", "municipio", "regional_saude", "nivel", "score", "prioridade_operacional_proxy", "indice_resiliencia_proxy", "indice_capacidade_cnes", "cnes_leitos_total", "cnes_estabelecimentos_total", "cnes_equipamentos_total", "cnes_profissionais_total", "flag_ventilador", "flag_monitor", "ocupacao_leitos_pct", "pressao_calor_pct", "indice_vulnerabilidade_calor", "status_estoque", "status_infraestrutura"],
            height=480,
        )
    elif "indice_resiliencia" in resumo.columns:
        make_bar(resumo, "municipio", "indice_resiliencia", "Índice de resiliência - Top")

    st.markdown("#### Campos operacionais no resumo")
    show_df(
        resumo,
        [
            "cod_ibge", "municipio", "regional_saude", "nivel", "score", "autonomia_min_dias",
            "falhas_infra_pct", "indice_resiliencia", "resil_capacidade_leitos",
            "resil_estoque", "resil_infraestrutura", "resil_busca_ativa",
            "resil_comunicacao",
        ],
        height=420,
    )

    st.markdown("#### Estoque/autonomia")
    show_df(stock, height=260)

    st.markdown("#### Infraestrutura")
    show_df(infra, height=260)


# ---------------------------------------------------------------------
# Tab 7
# ---------------------------------------------------------------------
with tabs[6]:
    st.subheader("Geografia, base territorial e shapefile")

    st.info(shapefile_status)

    st.markdown("#### Mapa de vulnerabilidade territorial ao calor")
    if "indice_vulnerabilidade_calor" in map_df.columns:
        choropleth_or_points(
            map_df,
            geojson_mun,
            "indice_vulnerabilidade_calor",
            "Vulnerabilidade territorial ao calor",
            hover_cols=["municipio", "regional_saude", "populacao", "populacao_2025", "area_km2_ibge"],
        )
    else:
        st.warning("Campo indice_vulnerabilidade_calor não encontrado no resumo municipal.")

    st.markdown("#### Tabela geográfica deduplicada")
    geo_cols = [
        "cod_ibge", "municipio", "regional_saude", "macroregiao_saude",
        "populacao", "populacao_2025", "lat", "lon",
        "indice_vulnerabilidade_calor",
    ]
    geo_table = map_df.drop_duplicates("cod_ibge") if "cod_ibge" in map_df.columns else map_df
    show_df(geo_table.sort_values("municipio") if "municipio" in geo_table.columns else geo_table, geo_cols, height=520)


# ---------------------------------------------------------------------
# Tab 8
# ---------------------------------------------------------------------
with tabs[7]:
    st.subheader("Cálculos e indicadores do sistema")

    st.markdown(
        """
### 1. Nível operacional municipal

O nível operacional é uma síntese de múltiplos blocos: clima/biometeorologia, risco cumulativo, onda de calor por percentil, qualidade do ar, assistência, ocupação, pressão assistencial e indicadores operacionais.

| Nível | Interpretação operacional |
|---|---|
| Cinza | dados insuficientes |
| Verde | normalidade operacional |
| Amarela | atenção |
| Laranja | alerta |
| Vermelha | resposta intensificada |
| Roxa | situação crítica/excepcional |

### 2. Risco cumulativo de calor em 3 dias

O indicador `risco_cumulativo_3d` sintetiza a persistência do calor recente. Ele considera o calor acumulado em janela curta, permitindo identificar municípios com estresse térmico progressivo mesmo quando a Tmax isolada ainda não dispara gatilhos altos.

### 3. Onda de calor P95

O campo `onda_calor_p95_2d` indica se houve pelo menos 2 dias consecutivos acima do limiar local de temperatura média diária, estimado pelo percentil 95 municipal.

### 4. UTCI/proxy e Heat Index

O `utci_proxy` aproxima o estresse térmico percebido, combinando temperatura, umidade e outros elementos meteorológicos disponíveis. O `heat_index` estima desconforto associado à combinação de calor e umidade.

### 5. Ocupação de leitos IndicaSUS

A ocupação de leitos vem da tabela `hospital_ocupacao_municipio`, integrada por `cod_ibge`. Para municípios sem dado municipal no IndicaSUS, o painel aplica fallback estadual para evitar campo vazio no mapa.

### 6. Pressão assistencial proxy

A pressão assistencial proxy combina ocupação de leitos IndicaSUS, risco cumulativo de calor e UTCI/proxy. Ela funciona como sinalizador operacional, mas não substitui fila, tempo de espera, regulação ou censo hospitalar validado.

### 7. Qualidade do ar

A aba usa `qualidade_ar_municipal`, com PM2.5, PM10, O3, NO2, CO e SO2 quando disponíveis. O sistema também pode calcular `iq_ar_score` e `qualidade_ar_nivel`.

### 8. Vulnerabilidade territorial

A vulnerabilidade territorial ao calor cruza dados territoriais, populacionais e geográficos por `cod_ibge` de 7 dígitos.

### 9. Pendências de integração plena

- estoque e autonomia de insumos por município;
- infraestrutura crítica das unidades;
- pressão assistencial real com fila/regulação/tempo de espera;
- atualização automática contínua via agendador;
- boletim operacional automatizado.
        """
    )



# ---------------------------------------------------------------------
# Tab 9 - Inteligência, predição e análise estatística
# ---------------------------------------------------------------------
with tabs[8]:
    st.subheader("Inteligência, predição 7 dias e análise clima-saúde")

    st.markdown(
        """
        Esta aba combina três camadas: **alerta inteligente municipal**, **predição operacional de 7 dias**
        e **análise estatística ecológica clima-saúde**. As associações estatísticas são exploratórias e devem
        ser interpretadas como apoio à priorização, não como inferência causal individual.
        """
    )

    # ---------------------------------------------------------------
    # Predição 7 dias
    # ---------------------------------------------------------------
    st.markdown("### Predição operacional 7 dias")

    if pred_v6.empty:
        st.info("Tabela predicao_calor_7d_municipal_v6 ainda não criada. Rode corrigir_predicao_alerta_analise_v7_5.py.")
    else:
        pv = pred_v6.copy()
        if "cod_ibge" in pv.columns and "cod_ibge" in resumo.columns:
            pv["cod_ibge"] = normalize_cod_ibge(pv["cod_ibge"])
            pv = pv[pv["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Municípios com predição", len(pv))
        c2.metric("≥ Laranja 7d", int(pv["nivel_predicao_7d"].isin(["laranja", "vermelha", "roxa"]).sum()) if "nivel_predicao_7d" in pv.columns else 0)
        c3.metric("Vermelha/Roxa 7d", int(pv["nivel_predicao_7d"].isin(["vermelha", "roxa"]).sum()) if "nivel_predicao_7d" in pv.columns else 0)
        c4.metric("Score preditivo máx.", safe_metric_value(pd.to_numeric(pv.get("risco_preditivo_score", pd.Series(dtype=float)), errors="coerce").max(), "", 1))

        if "nivel_predicao_7d" in pv.columns:
            dist_pred = pv["nivel_predicao_7d"].value_counts().reindex(["verde", "amarela", "laranja", "vermelha", "roxa"]).fillna(0).reset_index()
            dist_pred.columns = ["nível", "municípios"]
            fig = px.bar(dist_pred, x="nível", y="municípios", title="Distribuição da predição 7 dias")
            st.plotly_chart(fig, use_container_width=True)

            map_pred = map_df.merge(
                pv[[
                    c for c in [
                        "cod_ibge", "nivel_predicao_7d", "risco_preditivo_score",
                        "tmax_max_7d", "utci_proxy_max_7d",
                        "risco_cumulativo_3d_max_7d", "dias_onda_calor_prevista_7d",
                        "fonte_predicao"
                    ] if c in pv.columns
                ]].drop_duplicates("cod_ibge"),
                on="cod_ibge",
                how="left",
            )

            choropleth_or_points(
                map_pred,
                geojson_mun,
                "nivel_predicao_7d",
                "Mapa preditivo 7 dias por nível",
                hover_cols=[
                    "regional_saude", "nivel", "nivel_predicao_7d", "risco_preditivo_score",
                    "tmax_max_7d", "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d",
                    "dias_onda_calor_prevista_7d", "ocupacao_leitos_pct", "pressao_calor_pct",
                ],
                categorical=True,
            )

        if "risco_preditivo_score" in pv.columns:
            map_pred_score = map_df.merge(
                pv[["cod_ibge", "risco_preditivo_score"]].drop_duplicates("cod_ibge"),
                on="cod_ibge",
                how="left",
            )
            choropleth_or_points(
                map_pred_score,
                geojson_mun,
                "risco_preditivo_score",
                "Mapa do score preditivo 7 dias",
                hover_cols=["regional_saude", "nivel", "risco_preditivo_score", "risco_cumulativo_3d", "ocupacao_leitos_pct", "pressao_calor_pct"],
            )

            make_bar(
                pv.sort_values("risco_preditivo_score", ascending=False).head(25),
                "municipio",
                "risco_preditivo_score",
                "Ranking municipal do risco preditivo 7 dias",
            )

        show_df(
            pv.sort_values("risco_preditivo_score", ascending=False) if "risco_preditivo_score" in pv.columns else pv,
            [
                "cod_ibge", "municipio", "regional_saude", "nivel_predicao_7d",
                "risco_preditivo_score", "tmax_max_7d", "utci_proxy_max_7d",
                "risco_cumulativo_3d_max_7d", "dias_onda_calor_prevista_7d",
                "ocupacao_leitos_pct", "pressao_calor_pct", "fonte_predicao",
            ],
            height=420,
        )

    st.markdown("#### Predição regional")
    show_df(pred_reg_v6, height=260)

    # ---------------------------------------------------------------
    # Alerta inteligente
    # ---------------------------------------------------------------
    st.markdown("### Alerta inteligente municipal")

    if alerta_mun_v6.empty:
        st.info("Tabela alerta_inteligente_municipal_v6 ainda não criada.")
    else:
        am = alerta_mun_v6.copy()
        if "cod_ibge" in am.columns and "cod_ibge" in resumo.columns:
            am["cod_ibge"] = normalize_cod_ibge(am["cod_ibge"])
            am = am[am["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]

        if "alerta_inteligente_nivel" in am.columns:
            dist_alerta = am["alerta_inteligente_nivel"].value_counts().reindex(["verde", "amarela", "laranja", "vermelha", "roxa"]).fillna(0).reset_index()
            dist_alerta.columns = ["nível", "municípios"]
            fig = px.bar(dist_alerta, x="nível", y="municípios", title="Distribuição do alerta inteligente")
            st.plotly_chart(fig, use_container_width=True)

            map_alert = map_df.merge(
                am[["cod_ibge", "alerta_inteligente_nivel", "alerta_inteligente_score"]].drop_duplicates("cod_ibge"),
                on="cod_ibge",
                how="left",
            )
            choropleth_or_points(
                map_alert,
                geojson_mun,
                "alerta_inteligente_nivel",
                "Mapa do alerta inteligente",
                hover_cols=[
                    "regional_saude", "nivel", "score", "alerta_inteligente_score",
                    "risco_cumulativo_3d", "ocupacao_leitos_pct", "pressao_calor_pct",
                    "pm25_ugm3", "iq_ar_score",
                ],
                categorical=True,
            )

        make_bar(
            am.sort_values("alerta_inteligente_score", ascending=False).head(25) if "alerta_inteligente_score" in am.columns else am.head(25),
            "municipio",
            "alerta_inteligente_score",
            "Ranking do alerta inteligente",
        )

        show_df(
            am.sort_values("alerta_inteligente_score", ascending=False) if "alerta_inteligente_score" in am.columns else am,
            [
                "cod_ibge", "municipio", "regional_saude", "nivel",
                "alerta_inteligente_nivel", "alerta_inteligente_score",
                "nivel_predicao_7d", "risco_preditivo_score",
                "risco_cumulativo_3d", "ocupacao_leitos_pct",
                "pressao_calor_pct", "pm25_ugm3", "recomendacao_operacional",
            ],
            height=420,
        )

    st.markdown("#### Alerta regional")
    show_df(alerta_reg_v6, height=260)

    # ---------------------------------------------------------------
    # Análise estatística
    # ---------------------------------------------------------------
    st.markdown("### Análise estatística clima-saúde")

    if analise_corr_v8.empty:
        st.info("Tabela analise_clima_saude_correlacoes_v8 ainda não criada. Rode analise_estatistica_clima_saude_v8.py ou o hotfix V7.5.")
    else:
        corr = analise_corr_v8.copy()
        for c in ["rho", "p_valor", "n_municipios", "abs_rho"]:
            if c in corr.columns:
                corr[c] = pd.to_numeric(corr[c], errors="coerce")

        corr_top = corr.sort_values("abs_rho", ascending=False).head(25) if "abs_rho" in corr.columns else corr.head(25)
        corr_top["par"] = corr_top["exposicao"].astype(str) + " → " + corr_top["desfecho"].astype(str)

        fig = px.bar(
            corr_top.sort_values("abs_rho", ascending=True),
            x="abs_rho",
            y="par",
            orientation="h",
            title="Maiores associações exploratórias clima-saúde — |rho Spearman|",
            hover_data=[c for c in ["rho", "p_valor", "n_municipios"] if c in corr_top.columns],
        )
        st.plotly_chart(fig, use_container_width=True)

        show_df(
            corr.sort_values("abs_rho", ascending=False) if "abs_rho" in corr.columns else corr,
            ["exposicao", "desfecho", "metodo", "rho", "p_valor", "n_municipios", "abs_rho"],
            height=420,
        )

    st.markdown("### Alerta estatístico municipal")

    if analise_alertas_v8.empty:
        st.info("Tabela analise_clima_saude_alertas_estatisticos_v8 ainda não criada.")
    else:
        ae = analise_alertas_v8.copy()
        if "cod_ibge" in ae.columns and "cod_ibge" in resumo.columns:
            ae["cod_ibge"] = normalize_cod_ibge(ae["cod_ibge"])
            ae = ae[ae["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]

        if "nivel_alerta_estatistico" in ae.columns:
            map_stat = map_df.merge(
                ae[["cod_ibge", "nivel_alerta_estatistico", "score_alerta_estatistico"]].drop_duplicates("cod_ibge"),
                on="cod_ibge",
                how="left",
            )
            choropleth_or_points(
                map_stat,
                geojson_mun,
                "nivel_alerta_estatistico",
                "Mapa do alerta estatístico clima-saúde",
                hover_cols=[
                    "regional_saude", "nivel", "score_alerta_estatistico",
                    "risco_cumulativo_3d", "pm25_ugm3", "ocupacao_leitos_pct",
                    "pressao_calor_pct",
                ],
                categorical=True,
            )

        make_bar(
            ae.sort_values("score_alerta_estatistico", ascending=False).head(25) if "score_alerta_estatistico" in ae.columns else ae.head(25),
            "municipio",
            "score_alerta_estatistico",
            "Ranking do alerta estatístico clima-saúde",
        )

        show_df(
            ae.sort_values("score_alerta_estatistico", ascending=False) if "score_alerta_estatistico" in ae.columns else ae,
            [
                "cod_ibge", "municipio", "regional_saude", "nivel",
                "score_alerta_estatistico", "nivel_alerta_estatistico",
                "risco_cumulativo_3d", "utci_proxy", "tmax", "pm25_ugm3",
                "ocupacao_leitos_pct", "pressao_calor_pct",
                "gal_positividade_pct", "sim_obitos_calor_total_por100k",
                "flag_clima_alto", "flag_ar_alto", "flag_assistencia_alta", "flag_saude_alta",
            ],
            height=460,
        )


    # ---------------------------------------------------------------
    # V9 - Epidemiologia temporal
    # ---------------------------------------------------------------
    st.markdown("### V9 — Epidemiologia temporal e priorização")

    if v9_status.empty:
        st.info("Tabelas V9 ainda não criadas. Rode analise_epidemiologica_temporal_v9.py.")
    else:
        st.markdown("#### Status da modelagem temporal")
        show_df(v9_status, height=180)

        st.markdown("#### Validação V9")
        show_df(v9_validacao, height=220)

        if not v9_priorizacao.empty:
            vp = v9_priorizacao.copy()
            if "cod_ibge" in vp.columns and "cod_ibge" in resumo.columns:
                vp["cod_ibge"] = normalize_cod_ibge(vp["cod_ibge"])
                vp = vp[vp["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Municípios V9", len(vp))
            c2.metric("Prioridade alta/muito alta", int(vp["nivel_priorizacao_v9"].isin(["alto", "muito alto"]).sum()) if "nivel_priorizacao_v9" in vp.columns else 0)
            c3.metric("Score V9 máx.", safe_metric_value(pd.to_numeric(vp.get("score_priorizacao_v9", pd.Series(dtype=float)), errors="coerce").max(), "", 1))
            c4.metric("Painel temporal", "Sim" if len(v9_painel) > 0 else "Não")

            if "nivel_priorizacao_v9" in vp.columns:
                map_v9 = map_df.merge(
                    vp[["cod_ibge", "nivel_priorizacao_v9", "score_priorizacao_v9"]].drop_duplicates("cod_ibge"),
                    on="cod_ibge",
                    how="left",
                )
                choropleth_or_points(
                    map_v9,
                    geojson_mun,
                    "nivel_priorizacao_v9",
                    "Mapa de priorização epidemiológica V9",
                    hover_cols=[
                        "regional_saude", "nivel", "score_priorizacao_v9",
                        "risco_cumulativo_3d", "ocupacao_leitos_pct", "pressao_calor_pct"
                    ],
                    categorical=True,
                )

            make_bar(
                vp.sort_values("score_priorizacao_v9", ascending=False).head(25) if "score_priorizacao_v9" in vp.columns else vp.head(25),
                "municipio",
                "score_priorizacao_v9",
                "Ranking de priorização epidemiológica V9",
            )

            show_df(
                vp.sort_values("score_priorizacao_v9", ascending=False) if "score_priorizacao_v9" in vp.columns else vp,
                [
                    "cod_ibge", "municipio", "regional_saude",
                    "score_priorizacao_v9", "nivel_priorizacao_v9",
                    "score_saude_v9", "score_exposicao_v9",
                    "sim_obitos_calor_total", "gal_positivos_total", "gal_testes_total",
                    "tmax", "utci_proxy", "risco_cumulativo_3d", "pm25_ugm3",
                    "tem_modelagem_temporal",
                ],
                height=420,
            )

        st.markdown("#### Lags clima-saúde V9")
        if not v9_lags.empty and "rho" in v9_lags.columns:
            vl = v9_lags.copy()
            for c in ["rho", "p_valor", "abs_rho", "n_observacoes"]:
                if c in vl.columns:
                    vl[c] = pd.to_numeric(vl[c], errors="coerce")
            vl_top = vl.sort_values("abs_rho", ascending=False).head(25) if "abs_rho" in vl.columns else vl.head(25)
            if {"exposicao", "desfecho", "abs_rho"}.issubset(vl_top.columns):
                vl_top["par"] = vl_top["exposicao"].astype(str) + " → " + vl_top["desfecho"].astype(str) + " (lag " + vl_top.get("lag_meses", "").astype(str) + ")"
                fig = px.bar(vl_top.sort_values("abs_rho", ascending=True), x="abs_rho", y="par", orientation="h", title="Associações temporais por lag — V9")
                st.plotly_chart(fig, use_container_width=True)
        show_df(v9_lags, height=320)

        st.markdown("#### Modelos temporais V9")
        show_df(v9_modelos, height=300)

        st.markdown("#### Painel saúde mensal V9")
        show_df(v9_saude_mensal, height=320)

        st.markdown("#### Painel clima-saúde V9")
        show_df(v9_painel, height=320)


    st.markdown("#### Base municipal integrada para análise")
    show_df(analise_base_v8, height=320)



# ---------------------------------------------------------------------
# Tab 10
# ---------------------------------------------------------------------
with tabs[9]:
    st.subheader("Alertas, auditoria e disponibilidade das bases")

    tables = [
        "resumo_municipal_atual",
        "met_biometeo",
        "qualidade_ar_municipal",
        "hospital_ocupacao_municipio",
        "hospital_ocupacao_estado",
        "epi_pressao_assistencial",
        "ops_estoque_autonomia",
        "ops_infraestrutura_resumo",
        "ops_resumo_operacional_cnes",
        "ops_cnes_municipio",
        "saude_calor_municipio",
        "saude_calor_serie_estado",
        "dicionario_monitoramento_saude_v6",
        "gal_positividade_municipal_v6",
        "gal_positividade_estado_serie_v6",
        "sim_obitos_calor_municipal_v6",
        "sim_obitos_calor_estado_serie_v6",
        "qualidade_ar_estado_serie_v6",
        "alerta_inteligente_municipal_v6",
        "alerta_inteligente_regional_v6",
        "predicao_calor_7d_municipal_v6",
        "predicao_calor_7d_regional_v6",
        "analise_clima_saude_base_municipal_v8",
        "analise_clima_saude_correlacoes_v8",
        "analise_clima_saude_alertas_estatisticos_v8",
        "validacao_v7_5",
        "v9_status_modelagem_temporal",
        "v9_validacao",
        "v9_painel_saude_municipal_mensal",
        "v9_painel_clima_saude_mensal",
        "v9_lags_clima_saude",
        "v9_modelos_temporais",
        "v9_priorizacao_epidemiologica",
        "inmet_alertas",
        "raw_indicasus_ocupacao_tempo_real",
        "raw_qualidade_ar_copernicus",
    ]
    audit = pd.DataFrame([{"tabela": t, "linhas": table_count(t)} for t in tables])
    st.dataframe(audit, use_container_width=True)

    st.markdown("#### Municípios em maior nível operacional")
    show_df(
        resumo.sort_values(["score", "risco_cumulativo_3d"], ascending=[False, False]),
        ["cod_ibge", "municipio", "regional_saude", "nivel", "score", "tmax", "utci_proxy", "risco_cumulativo_3d", "ocupacao_leitos_pct", "pressao_calor_pct", "motivo"],
        height=520,
    )
