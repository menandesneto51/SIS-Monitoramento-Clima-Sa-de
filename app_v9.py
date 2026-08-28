# -*- coding: utf-8 -*-
"""
ARARAS MT - Dashboard V9

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

import inspect
import os
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st

from sisclima.core.db import backend_name, read_table, table_count, table_exists
from sisclima.engines.geospatial import (
    LEVEL_COLOR_MAP,
    LEVEL_ORDER,
    load_municipal_geojson,
    make_choropleth_or_points,
    prepare_map_dataframe,
)
from sisclima.engines.panel_indicators import enrich_panel_indicators, state_indicator_summary
from sisclima.engines.recommendations import recommendations_for_stage
from sisclima.engines.stages import STAGE_ORDER
from sisclima.ui import theme as ui_theme
try:
    from sisclima.ui.alerts_sop import (
        ALERT_CHECKLIST,
        ALERT_SOP_STEPS,
        CRITERIOS_ESCALONAMENTO,
        alert_channel_status,
        boletim_destinatario_resumo,
        format_boletim_painel,
        municipal_alert_candidates,
        persist_checklist_validation,
        preview_boletim_executivo_ses,
        preview_state_alert,
        recent_alert_log,
        recent_nivel_historico,
        recent_validacoes_humanas,
        routing_status_summary,
    )
except ImportError as _alerts_imp_err:
    st.error(
        "Não foi possível carregar `sisclima.ui.alerts_sop`. "
        f"Módulo: {getattr(_alerts_imp_err, 'name', '—')} · {_alerts_imp_err}"
    )
    raise
from sisclima.ui.home_ops import (
    AVISO_SINAL_VS_ATIVACAO,
    ameaca_dominante_estado,
    build_fonte_frescor_home,
    explicar_nivel_municipio,
    frescor_resumo,
    pressao_card_caption,
    pressao_card_value,
    pressao_rotulo,
    tabela_prioridades_hoje,
    tendencia_card_caption,
    tendencia_card_value,
    tendencia_estado_rotulo,
)
from sisclima.ui.correlation import compute_spearman_pairs
from sisclima.ui.explainers import HOW_TO_READ_PANEL, INDICATOR_GLOSSARY, LEVEL_GUIDE

try:
    from sisclima.ui.explainers import GLOSSARIO_PUBLICO, HOW_TO_READ_PUBLIC
except ImportError:
    HOW_TO_READ_PUBLIC = [
        "1. Abra a aba Visão: faixa de nível, cards do recorte e o mapa de risco de 3 dias.",
        "2. Filtre regional ou município no topo — o recorte vale para todas as abas.",
        "3. Em Mapas, compare calor, fumaça, vulnerabilidade e a predição de 7 dias.",
        "4. Em Território, confira a malha municipal e as populações vulneráveis.",
        "5. Em Qualidade do ar, veja PM2,5, IQA e focos de queimadas.",
        "6. Em El Niño, leia o cenário oficial (ASO) e o boletim da semana.",
        "7. Em Arboviroses, acompanhe dengue, zika e chikungunya (casos 7 dias e mapa).",
        "8. Em Cemaden / ANA, veja alertas de desastre, nível de rio e chuva.",
        "9. Em Sazonalidade / OR, compare o mês atual com o histórico e o odds ratio ecológico.",
        "10. Em Cálculos, leia como cada indicador publicado é composto.",
    ]
    GLOSSARIO_PUBLICO = [
        "nivel",
        "tmax",
        "utci_proxy",
        "risco_cumulativo_3d",
        "indice_tensao_climatica",
        "indice_carga_saude",
        "indice_vigilancia_integrada",
        "indice_prioridade_global",
        "faixa_prioridade_global",
        "tendencia_7d",
        "tendencia_prioridade_7d",
        "pressao_calor_pct",
        "indice_pressao_saude",
        "ocupacao_leitos_pct",
        "pm25_ugm3",
        "iq_ar_score",
        "qualidade_ar_nivel",
        "focos_queimadas_7d",
        "focos_queimadas_24h",
        "nivel_queimadas",
        "indice_vulnerabilidade_calor",
        "casos_arbovirus_7d",
        "incidencia_arbovirus_100k",
        "risco_vetorial_climatico",
        "indice_saturacao_solo",
        "situacao_hidro",
        "indice_sazonal",
        "odds_ratio",
    ]
from sisclima.ui.interpretacoes import (
    GUIDE_ALERTAS,
    GUIDE_AR,
    GUIDE_ASSISTENCIA,
    GUIDE_CALC,
    GUIDE_CLIMA_TITAN,
    GUIDE_CORR,
    GUIDE_EXECUTIVO,
    GUIDE_GEO,
    GUIDE_INTEL,
    GUIDE_MAPAS,
    GUIDE_OPERACIONAL,
    GUIDE_PRONTIDAO,
    GUIDE_SAZONAL_OR,
    narrativa_alertas,
    narrativa_ar,
    narrativa_assistencia,
    narrativa_calculos,
    narrativa_clima_titan,
    narrativa_correlacao,
    narrativa_executivo,
    narrativa_geo,
    narrativa_inteligencia,
    narrativa_mapas,
    narrativa_operacional,
    narrativa_sazonal_or,
    render_interpretacao,
)
from sisclima.ui.views_extra import (
    render_adaptasus,
    render_arboviroses,
    render_geocalor,
    render_hidrologia,
    render_sentinela_sg,
    render_sivep,
)


def _call_view(fn, **kwargs):
    """Chama a view só com os argumentos que a função aceita (evita TypeError de cache antigo)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return fn()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return fn(**kwargs)
    accepted = {k: v for k, v in kwargs.items() if k in params}
    try:
        return fn(**accepted) if accepted else fn()
    except TypeError:
        return fn()


from sisclima.ui.prontidao import render_prontidao
from sisclima.alerts.change_detector import alerts_enabled
from sisclima.branding import ARARAS_SYMBOL_PATH, SYSTEM_EXPANSION, SYSTEM_NAME, SYSTEM_TAGLINE
from sisclima.engines.boletim_el_nino_semanal import build_boletim_semanal, load_cenario_oficial


def _load_painel_el_nino() -> dict:
    """Cenário oficial do boletim mensal (não é output do pipeline)."""
    return load_cenario_oficial()


try:
    st.set_page_config(
        page_title=f"{SYSTEM_NAME} · {SYSTEM_TAGLINE}",
        page_icon=str(ARARAS_SYMBOL_PATH) if ARARAS_SYMBOL_PATH.exists() else None,
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass
ui_theme.apply_theme()
ui_theme.ses_masthead(
    sistema=SYSTEM_NAME,
    subtitulo=SYSTEM_TAGLINE,
    base=backend_name(),
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=300)
def load_table(table_name: str) -> pd.DataFrame:
    try:
        return read_table(table_name)
    except Exception:
        return pd.DataFrame()


def load_table_ui(table_name: str) -> pd.DataFrame:
    """Carrega tabela com aviso na UI (usa cache de load_table)."""
    try:
        df = load_table(table_name)
        if df.empty and not table_exists(table_name):
            return df
        return df
    except Exception as exc:
        st.warning(f"Não foi possível carregar {table_name}: {exc}")
        return pd.DataFrame()


def table_count_ui(table_name: str) -> int:
    try:
        return table_count(table_name)
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
    """Carrega polígonos municipais a partir do shapefile oficial (fallback GeoJSON)."""
    return load_municipal_geojson(prefer_shapefile=True)


def _enrich_assistencia(resumo: pd.DataFrame) -> pd.DataFrame:
    """Completa ocupação/pressão a partir das tabelas assistenciais quando faltarem no resumo."""
    out = resumo.copy()
    if "cod_ibge" not in out.columns:
        return out
    out["cod_ibge"] = normalize_cod_ibge(out["cod_ibge"])

    if "ocupacao_leitos_pct" not in out.columns or out["ocupacao_leitos_pct"].isna().all():
        occ = load_table("hospital_ocupacao_municipio")
        if not occ.empty and "cod_ibge" in occ.columns:
            occ = occ.copy()
            occ["cod_ibge"] = normalize_cod_ibge(occ["cod_ibge"])
            rename = {
                "ocupacao_pct": "ocupacao_leitos_pct",
                "leitos_existentes": "leitos_total",
                "fonte": "fonte_ocupacao",
            }
            occ = occ.rename(columns={k: v for k, v in rename.items() if k in occ.columns})
            keep = [
                c for c in [
                    "cod_ibge", "ocupacao_leitos_pct", "leitos_total", "leitos_ocupados",
                    "leitos_livres", "fonte_ocupacao",
                ]
                if c in occ.columns
            ]
            occ = occ[keep].drop_duplicates("cod_ibge")
            drop_overlap = [c for c in keep if c != "cod_ibge" and c in out.columns]
            if drop_overlap:
                out = out.drop(columns=drop_overlap)
            out = out.merge(occ, on="cod_ibge", how="left")

    if "pressao_calor_pct" not in out.columns or out["pressao_calor_pct"].isna().all():
        press = load_table("epi_pressao_assistencial")
        if not press.empty and "cod_ibge" in press.columns:
            press = press.copy()
            press["cod_ibge"] = normalize_cod_ibge(press["cod_ibge"])
            if "pressao_calor_pct" not in press.columns and "pressao_assistencial_pct" in press.columns:
                press = press.rename(columns={"pressao_assistencial_pct": "pressao_calor_pct"})
            keep = [c for c in ["cod_ibge", "pressao_calor_pct", "fonte_pressao"] if c in press.columns]
            if "pressao_calor_pct" in keep:
                press = press[keep].drop_duplicates("cod_ibge")
                if "pressao_calor_pct" in out.columns:
                    out = out.drop(columns=["pressao_calor_pct"])
                if "fonte_pressao" in out.columns and "fonte_pressao" in press.columns:
                    out = out.drop(columns=["fonte_pressao"])
                out = out.merge(press, on="cod_ibge", how="left")
    return out


def _enrich_qualidade_ar(resumo: pd.DataFrame) -> pd.DataFrame:
    """Garante PM2,5 / IQA no resumo a partir de qualidade_ar_municipal (última data)."""
    if resumo is None or resumo.empty or "cod_ibge" not in resumo.columns:
        return resumo
    out = resumo.copy()
    need_pm = "pm25_ugm3" not in out.columns or pd.to_numeric(out.get("pm25_ugm3"), errors="coerce").isna().all()
    need_iq = "iq_ar_score" not in out.columns or pd.to_numeric(out.get("iq_ar_score"), errors="coerce").isna().all()
    if not need_pm and not need_iq:
        # ainda preenche buracos pontuais
        pass
    try:
        aq = load_table("qualidade_ar_municipal")
    except Exception:
        return out
    if aq is None or aq.empty or "cod_ibge" not in aq.columns:
        return out
    aq = aq.copy()
    aq["cod_ibge"] = normalize_cod_ibge(aq["cod_ibge"])
    if "data" in aq.columns:
        aq["_ord"] = pd.to_datetime(aq["data"], errors="coerce")
        aq = aq.sort_values("_ord").drop_duplicates("cod_ibge", keep="last")
    else:
        aq = aq.drop_duplicates("cod_ibge", keep="last")
    cols = [c for c in ["cod_ibge", "pm25_ugm3", "pm10_ugm3", "o3_ugm3", "no2_ugm3", "iq_ar_score", "qualidade_ar_nivel", "poluente_dominante"] if c in aq.columns]
    if len(cols) <= 1:
        return out
    m = aq[cols]
    out["cod_ibge"] = normalize_cod_ibge(out["cod_ibge"])
    for col in cols:
        if col == "cod_ibge":
            continue
        if col not in out.columns:
            out = out.merge(m[["cod_ibge", col]], on="cod_ibge", how="left")
        else:
            joined = out[["cod_ibge"]].merge(m[["cod_ibge", col]], on="cod_ibge", how="left")
            if col in ("qualidade_ar_nivel", "poluente_dominante"):
                out[col] = out[col].fillna(joined[col])
            else:
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(pd.to_numeric(joined[col], errors="coerce"))
    return out


def prepare_resumo() -> pd.DataFrame:
    resumo = load_table("resumo_municipal_atual")
    if resumo.empty:
        return resumo

    resumo = resumo.copy()
    if "cod_ibge" in resumo.columns:
        resumo["cod_ibge"] = normalize_cod_ibge(resumo["cod_ibge"])
    resumo = _enrich_assistencia(resumo)
    resumo = _enrich_qualidade_ar(resumo)

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
    resumo = coalesce_columns(
        resumo,
        "macroregiao_saude",
        ["macroregiao_saude", "macroregiao_saude_x", "macroregiao_saude_y", "macro"],
    )
    try:
        from sisclima.ingestion.regionais_ses import aplicar_regionais_ses

        resumo = aplicar_regionais_ses(resumo)
    except Exception:
        pass
    resumo["regional_saude"] = resumo.get("regional_saude", pd.Series(dtype=str)).fillna("Regional não informada").astype(str)

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
        "indice_tensao_climatica", "indice_carga_saude", "indice_vigilancia_integrada",
        "percentil_risco_estadual", "completude_dados_pct", "casos_srag",
        "casos_arbovirus_7d", "incidencia_srag_100k", "umidade_media",
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
    return prepare_map_dataframe(resumo, geojson=geojson, attrs=attrs, status=status)


def apply_global_filters(df: pd.DataFrame, regionais: list[str], municipios: list[str]) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if "regional_saude" in out.columns and regionais:
        out = out[out["regional_saude"].isin(regionais)]
    if "municipio" in out.columns and municipios:
        out = out[out["municipio"].isin(municipios)]
    return out


_PLACEHOLDER_REG = {"", "nan", "none", "nat", "regional não informada", "regional nao informada"}


def rotulo_recorte(regionais: list[str], municipios: list[str]) -> str:
    if municipios:
        if len(municipios) == 1:
            return str(municipios[0])
        return f"{len(municipios)} municípios"
    if regionais:
        if len(regionais) == 1:
            return str(regionais[0])
        return f"{len(regionais)} regionais"
    return "Estado"


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
    if color_col not in df.columns:
        st.info(
            f"Indicador **{color_col}** indisponível nesta rodada "
            "(ex.: IndicaSUS sem login ou base ainda não consolidada)."
        )
        return

    fig = make_choropleth_or_points(
        df,
        geojson,
        color_col=color_col,
        title=title,
        hover_cols=hover_cols,
        categorical=categorical,
        allow_points_fallback=True,
    )
    if fig is None:
        if geojson is None:
            st.warning(
                "Geometria municipal indisponível. Verifique o shapefile em "
                "`data/geo/municipios_mt/MT_Municipios_2025.shp` ou o GeoJSON em "
                "`data/processed/municipios_mt_2025_simplificado.geojson`."
            )
        elif "cod_ibge" not in df.columns or df["cod_ibge"].isna().all():
            st.info("Sem código IBGE para cruzamento com shapefile.")
        else:
            st.info("Sem dados geográficos suficientes para cloropleta municipal.")
        return
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def show_df(df: pd.DataFrame, cols: Optional[list[str]] = None, height: int = 420):
    if df.empty:
        st.info("Sem dados disponíveis nesta tabela (vazia ou ainda não consolidada na base).")
        return
    if cols:
        cols = [c for c in cols if c in df.columns]
        view = df[cols] if cols else df
    else:
        view = df
    try:
        st.dataframe(view, width="stretch", height=height)
    except TypeError:
        st.dataframe(view, use_container_width=True, height=height)


def safe_sort(df: pd.DataFrame, cols: list[str], ascending: bool | list[bool] = False) -> pd.DataFrame:
    """Ordena só pelas colunas que existem (evita KeyError com bases incompletas)."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    present = [c for c in cols if c in df.columns]
    if not present:
        return df
    if isinstance(ascending, list):
        asc_map = dict(zip(cols, ascending))
        asc = [asc_map.get(c, False) for c in present]
    else:
        asc = [bool(ascending)] * len(present)
    return df.sort_values(present, ascending=asc)


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
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
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
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
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
        "tmax": pd.to_numeric(df["tmax"], errors="coerce").max() if "tmax" in df.columns else pd.NA,
        "utci": pd.to_numeric(df["utci_proxy"], errors="coerce").max() if "utci_proxy" in df.columns else pd.NA,
        "risco3d": pd.to_numeric(df["risco_cumulativo_3d"], errors="coerce").max() if "risco_cumulativo_3d" in df.columns else pd.NA,
        "ocup_media": df["ocupacao_leitos_pct"].mean() if "ocupacao_leitos_pct" in df.columns else pd.NA,
        "ocup_max": df["ocupacao_leitos_pct"].max() if "ocupacao_leitos_pct" in df.columns else pd.NA,
        "pressao_media": df["pressao_calor_pct"].mean() if "pressao_calor_pct" in df.columns else pd.NA,
        "pressao_max": df["pressao_calor_pct"].max() if "pressao_calor_pct" in df.columns else pd.NA,
        "pm25_max": df["pm25_ugm3"].max() if "pm25_ugm3" in df.columns else pd.NA,
        "iqar_max": df["iq_ar_score"].max() if "iq_ar_score" in df.columns else pd.NA,
    }
    return out


def _trend_from_counts(atual: int, pred: int) -> str:
    if pred > atual:
        return "aumento"
    if pred < atual:
        return "queda"
    return "manutenção"


def _trend_from_values(atual, pred, tol: float = 0.05) -> str:
    try:
        if pd.isna(atual) or pd.isna(pred):
            return "—"
        a, p = float(atual), float(pred)
        if abs(p - a) <= tol:
            return "manutenção"
        return "aumento" if p > a else "queda"
    except Exception:
        return "—"


def _trend_icon(label: str) -> str:
    return {"aumento": "↑", "queda": "↓", "manutenção": "→", "subindo": "↑", "descendo": "↓", "estável": "→"}.get(
        str(label).lower(), "—"
    )


def _trend_pt(label: str) -> str:
    key = str(label).lower()
    return {
        "aumento": "aumento",
        "queda": "queda",
        "manutenção": "manutenção",
        "subindo": "aumento",
        "descendo": "queda",
        "estável": "manutenção",
    }.get(key, "—")


def _modal_tendencia(df: pd.DataFrame, col: str = "tendencia_7d") -> str:
    if df is None or df.empty or col not in df.columns:
        return "—"
    vc = (
        df[col]
        .astype(str)
        .str.lower()
        .replace({"subindo": "aumento", "descendo": "queda", "estável": "manutenção", "estavel": "manutenção"})
        .value_counts()
    )
    known = vc.reindex(["aumento", "manutenção", "queda"]).fillna(0)
    if float(known.sum()) <= 0:
        return "—"
    return str(known.idxmax())


def state_summary_with_prediction(resumo: pd.DataFrame, pred: pd.DataFrame) -> dict:
    """Métricas estaduais atuais + predição 7d + tendência (queda/manutenção/aumento)."""
    out = state_summary_metrics(resumo)
    pred_levels = {n: 0 for n in ("verde", "amarela", "laranja", "vermelha", "roxa")}
    out.update(
        {
            "pred_levels": pred_levels,
            "tmax_pred": pd.NA,
            "utci_pred": pd.NA,
            "risco3d_pred": pd.NA,
            "tendencia_clima": _modal_tendencia(resumo),
        }
    )
    if pred is None or pred.empty:
        for n in pred_levels:
            out[f"tendencia_{n}"] = "—"
        return out

    pv = pred.copy()
    if "cod_ibge" in resumo.columns and "cod_ibge" in pv.columns:
        ids = set(normalize_cod_ibge(resumo["cod_ibge"]).dropna())
        pv["cod_ibge"] = normalize_cod_ibge(pv["cod_ibge"])
        pv = pv[pv["cod_ibge"].isin(ids)]

    if "nivel_predicao_7d" in pv.columns:
        for n in pred_levels:
            pred_levels[n] = int((pv["nivel_predicao_7d"].astype(str).str.lower() == n).sum())
    out["pred_levels"] = pred_levels
    for n in pred_levels:
        out[f"tendencia_{n}"] = _trend_from_counts(int(out.get(n, 0)), int(pred_levels[n]))

    if "tmax_max_7d" in pv.columns:
        out["tmax_pred"] = pd.to_numeric(pv["tmax_max_7d"], errors="coerce").max()
    if "utci_proxy_max_7d" in pv.columns:
        out["utci_pred"] = pd.to_numeric(pv["utci_proxy_max_7d"], errors="coerce").max()
    if "risco_cumulativo_3d_max_7d" in pv.columns:
        out["risco3d_pred"] = pd.to_numeric(pv["risco_cumulativo_3d_max_7d"], errors="coerce").max()

    out["tendencia_tmax"] = _trend_from_values(out.get("tmax"), out.get("tmax_pred"), tol=0.15)
    out["tendencia_utci"] = _trend_from_values(out.get("utci"), out.get("utci_pred"), tol=0.15)
    out["tendencia_risco3d"] = _trend_from_values(out.get("risco3d"), out.get("risco3d_pred"), tol=0.05)
    return out


def metric_with_pred(col, label: str, atual, pred, tendencia: str, suffix: str = "", digits: int = 1) -> None:
    """st.metric com valor atual e delta = predição 7d + tendência."""
    value = safe_metric_value(atual, suffix, digits)
    tend = _trend_pt(tendencia)
    icon = _trend_icon(tendencia if tend != "—" else tendencia)
    if pred is not None and not (isinstance(pred, float) and pd.isna(pred)) and str(pred) not in {"", "nan", "<NA>"}:
        try:
            if pd.isna(pred):
                pred_txt = "—"
            else:
                pred_txt = safe_metric_value(pred, suffix, digits)
        except Exception:
            pred_txt = "—"
    else:
        pred_txt = "—"
    delta = f"7d {pred_txt} · {icon} {tend}" if tend != "—" else f"7d {pred_txt}"
    col.metric(label, value, delta=delta, delta_color="off")


# ---------------------------------------------------------------------
# Data (núcleo no topo; demais tabelas sob demanda por aba)
# ---------------------------------------------------------------------

resumo_all = prepare_resumo()
map_df_all, geojson_mun, shapefile_status = prepare_map_df(resumo_all)

from sisclima.auth.access import (
    apply_local_interno_preview,
    bootstrap_admin,
    catalogo_municipios,
    catalogo_regionais,
    current_user,
    is_admin,
    modo_publico,
    recorte_usuario,
)
from sisclima.plano.acesso import pode_abrir_sala
from sisclima.ui.acesso import render_access_bar, render_gestao_usuarios

bootstrap_admin()
apply_local_interno_preview()
_pub_reg = catalogo_regionais()
_pub_mun = catalogo_municipios()
if not _pub_reg:
    _pub_reg = sorted(
        [
            x
            for x in resumo_all.get("regional_saude", pd.Series(dtype=str)).dropna().astype(str).unique()
            if x.strip().lower() not in {"", "nan", "none", "nat", "regional não informada", "regional nao informada"}
        ]
    )
if not _pub_mun:
    _pub_mun = sorted(
        [
            x
            for x in resumo_all.get("municipio", pd.Series(dtype=str)).dropna().astype(str).unique()
            if x.strip().lower() not in {"", "nan", "none"}
        ]
    )
render_access_bar(regionais=_pub_reg, municipios=_pub_mun)
_PAINEL_PUBLICO = modo_publico()
_ABRIR_SALA = (not _PAINEL_PUBLICO) and pode_abrir_sala(current_user())

# Núcleo compartilhado: header, pressão e predição 7d (público reutiliza o painel restrito, com recortes)
def _with_norm_ibge(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "cod_ibge" not in df.columns:
        return df
    out = df.copy()
    out["cod_ibge"] = normalize_cod_ibge(out["cod_ibge"])
    return out


sisreg_tab = _with_norm_ibge(load_table("ops_sisreg_municipio"))
saude_calor_mun = _with_norm_ibge(load_table("saude_calor_municipio"))
sim_obitos_mun = _with_norm_ibge(load_table("sim_obitos_calor_municipal_v6"))
pred_v6 = _with_norm_ibge(load_table("predicao_calor_7d_municipal_v6"))

# Placeholders — preenchidos após a escolha da aba (carga sob demanda)
met = aq = occ = press = stock = infra = ops_proxy = ops_cnes = pd.DataFrame()
solo_sat = hidro_risco = alerta_integrado = inmet_alertas = cemaden_alertas_tab = ana_risco_tab = pd.DataFrame()
saude_calor_serie = saude_dic = gal_pos_mun = gal_pos_serie = sim_obitos_serie = aq_estado_serie = pd.DataFrame()
alerta_mun_v6 = alerta_reg_v6 = pred_reg_v6 = pd.DataFrame()
pred_skill_resumo = pred_ml_aux = epi_nowcast = epi_nowcast_skill = pd.DataFrame()
analise_base_v8 = analise_corr_v8 = analise_or_v1 = analise_alertas_v8 = pd.DataFrame()
sazon_mensal_v1 = sazon_heat_v1 = sazon_perfil_v1 = sazon_picos_v1 = lags_v1 = pd.DataFrame()
validacao_v75 = v9_status = v9_validacao = v9_saude_mensal = v9_clima = pd.DataFrame()
v9_painel = v9_lags = v9_modelos = v9_priorizacao = pd.DataFrame()

SECTION_TABLE_DEPS: dict[str, set[str]] = {
    "Mapas": {
        "sim_obitos_calor_estado_serie_v6",
        "saude_calor_serie_estado",
        "predicao_calor_7d_municipal_v6",
        "cnes_unidades_geo",
        "cobertura_territorio_cnes",
        "vigibarragens_populacoes",
    },
    "Visão executiva": {"alerta_integrado_sis_titan", "cemaden_alertas", "inmet_alertas"},
    "Clima / TITAN": {
        "met_biometeo",
        "solo_saturacao_municipal",
        "hidro_risco_municipal",
        "inmet_alertas",
        "cemaden_alertas",
        "ana_risco_municipal",
    },
    "Assistência": {
        "saude_calor_serie_estado",
        "dicionario_monitoramento_saude_v6",
        "gal_positividade_municipal_v6",
        "gal_positividade_estado_serie_v6",
        "sim_obitos_calor_estado_serie_v6",
    },
    "Qualidade do ar": {"qualidade_ar_municipal", "qualidade_ar_estado_serie_v6", "queimadas_focos_municipal"},
    "Operacional": {
        "ops_estoque_autonomia",
        "ops_infraestrutura_resumo",
        "ops_resumo_operacional_proxy",
        "ops_resumo_operacional_cnes",
        "cnes_unidades_geo",
    },
    "Geografia": {"cnes_unidades_geo", "cobertura_territorio_cnes", "vigibarragens_populacoes"},
    "Inteligência": {
        "alerta_inteligente_municipal_v6",
        "alerta_inteligente_regional_v6",
        "predicao_calor_7d_regional_v6",
        "predicao_calor_7d_skill_resumo_v1",
        "predicao_calor_7d_ml_aux_v1",
        "epi_nowcast_municipal_v1",
        "epi_nowcast_skill_resumo_v1",
        "analise_clima_saude_base_municipal_v8",
        "analise_clima_saude_correlacoes_v8",
        "analise_clima_saude_alertas_estatisticos_v8",
        "v9_status_modelagem_temporal",
        "v9_validacao",
        "v9_painel_saude_municipal_mensal",
        "v9_painel_clima_saude_mensal",
        "v9_lags_clima_saude",
        "v9_modelos_temporais",
        "v9_priorizacao_epidemiologica",
    },
    "Prontidão climática": {
        "prontidao_municipal",
        "prontidao_redistribuicao_regional",
        "prontidao_plano_acao",
        "vigibarragens_populacoes",
        "vigibarragens_municipal",
        "ops_estoque_autonomia",
        "ops_resumo_operacional_cnes",
        "queimadas_focos_municipal",
    },
    "Alertas": {
        "alerta_integrado_sis_titan",
        "inmet_alertas",
        "cemaden_alertas",
        "hidro_risco_municipal",
    },
    "Sazonalidade / OR": {
        "analise_clima_saude_odds_ratio_v1",
        "sazonalidade_indice_mensal_v1",
        "sazonalidade_heatmap_semana_ano_v1",
        "sazonalidade_picos_v1",
        "clima_desfecho_lags_v1",
    },
    "Correlação clima-saúde": {
        "analise_clima_saude_base_municipal_v8",
        "analise_clima_saude_correlacoes_v8",
        "analise_clima_saude_alertas_estatisticos_v8",
    },
}

TABLE_VAR_BINDINGS: dict[str, str] = {
    "met_biometeo": "met",
    "qualidade_ar_municipal": "aq",
    "hospital_ocupacao_municipio": "occ",
    "epi_pressao_assistencial": "press",
    "ops_estoque_autonomia": "stock",
    "ops_infraestrutura_resumo": "infra",
    "ops_resumo_operacional_proxy": "ops_proxy",
    "ops_resumo_operacional_cnes": "ops_cnes",
    "solo_saturacao_municipal": "solo_sat",
    "hidro_risco_municipal": "hidro_risco",
    "alerta_integrado_sis_titan": "alerta_integrado",
    "inmet_alertas": "inmet_alertas",
    "cemaden_alertas": "cemaden_alertas_tab",
    "ana_risco_municipal": "ana_risco_tab",
    "saude_calor_serie_estado": "saude_calor_serie",
    "dicionario_monitoramento_saude_v6": "saude_dic",
    "gal_positividade_municipal_v6": "gal_pos_mun",
    "gal_positividade_estado_serie_v6": "gal_pos_serie",
    "sim_obitos_calor_estado_serie_v6": "sim_obitos_serie",
    "qualidade_ar_estado_serie_v6": "aq_estado_serie",
    "alerta_inteligente_municipal_v6": "alerta_mun_v6",
    "alerta_inteligente_regional_v6": "alerta_reg_v6",
    "predicao_calor_7d_regional_v6": "pred_reg_v6",
    "predicao_calor_7d_municipal_v6": "pred_v6",
    "predicao_calor_7d_skill_resumo_v1": "pred_skill_resumo",
    "predicao_calor_7d_ml_aux_v1": "pred_ml_aux",
    "epi_nowcast_municipal_v1": "epi_nowcast",
    "epi_nowcast_skill_resumo_v1": "epi_nowcast_skill",
    "analise_clima_saude_base_municipal_v8": "analise_base_v8",
    "analise_clima_saude_correlacoes_v8": "analise_corr_v8",
    "analise_clima_saude_odds_ratio_v1": "analise_or_v1",
    "analise_clima_saude_alertas_estatisticos_v8": "analise_alertas_v8",
    "sazonalidade_indice_mensal_v1": "sazon_mensal_v1",
    "sazonalidade_heatmap_semana_ano_v1": "sazon_heat_v1",
    "sazonalidade_perfil_semana_epi_v1": "sazon_perfil_v1",
    "sazonalidade_picos_v1": "sazon_picos_v1",
    "clima_desfecho_lags_v1": "lags_v1",
    "validacao_v7_5": "validacao_v75",
    "v9_status_modelagem_temporal": "v9_status",
    "v9_validacao": "v9_validacao",
    "v9_painel_saude_municipal_mensal": "v9_saude_mensal",
    "v9_clima_municipal_mensal_detectado": "v9_clima",
    "v9_painel_clima_saude_mensal": "v9_painel",
    "v9_lags_clima_saude": "v9_lags",
    "v9_modelos_temporais": "v9_modelos",
    "v9_priorizacao_epidemiologica": "v9_priorizacao",
}


def hydrate_section_tables(section: str) -> None:
    """Carrega somente as tabelas necessárias para a aba ativa (menos memória no boot)."""
    needed = SECTION_TABLE_DEPS.get(section, set())
    g = globals()
    for table_name in needed:
        var = TABLE_VAR_BINDINGS.get(table_name)
        if not var:
            continue
        g[var] = _with_norm_ibge(load_table(table_name))


# Indicadores compostos (tensão climática, vigilância, tendência…) — ao vivo no painel
from sisclima.engines.adaptasus_intelligence import enrich_adaptasus_intelligence
from sisclima.engines.prioridade_global import enrich_prioridade_global, state_prioridade_summary

resumo_all = enrich_panel_indicators(resumo_all, pred_v6 if not pred_v6.empty else None)
resumo_all, _, _ = enrich_adaptasus_intelligence(resumo_all)
resumo_all = enrich_prioridade_global(resumo_all)
map_df_all, geojson_mun, shapefile_status = prepare_map_df(resumo_all)
intel_state = state_indicator_summary(resumo_all)
prioridade_state = state_prioridade_summary(resumo_all)

# ---------------------------------------------------------------------
# Header + filtros no topo (sem navegação lateral)
# ---------------------------------------------------------------------

if _PAINEL_PUBLICO:
    ui_theme.hero(
        SYSTEM_NAME,
        f"{SYSTEM_EXPANSION} · painel público · SES-MT | CIEVS-MT",
        chips=["SES-MT", "CIEVS-MT", "Público", "Clima e saúde"],
    )
else:
    ui_theme.hero(
        SYSTEM_NAME,
        f"{SYSTEM_EXPANSION} · painel interno · SES-MT | CIEVS-MT",
        chips=["SES-MT", "CIEVS-MT", "Interno", "Clima e saúde"],
    )

# Aviso de backend (sqlite vs Postgres) fica na aba «Fontes e qualidade» — não na home.

if resumo_all.empty:
    st.error("A tabela resumo_municipal_atual não foi encontrada ou está vazia. Rode o pipeline antes de abrir o painel.")
    st.stop()

resumo_all["score"] = pd.to_numeric(resumo_all.get("score", 0), errors="coerce").fillna(0)

st.markdown("<div class='sis-panel soft'><div class='sis-panel-title'>Filtros territoriais</div>", unsafe_allow_html=True)
f1, f2, f3 = st.columns([1.2, 1.2, 1.0])
regionais_disponiveis = sorted(
    [
        x
        for x in resumo_all.get("regional_saude", pd.Series(dtype=str)).dropna().astype(str).unique()
        if x.strip().lower() not in _PLACEHOLDER_REG
    ]
)
if not regionais_disponiveis:
    regionais_disponiveis = sorted(
        [x for x in resumo_all.get("regional_saude", pd.Series(dtype=str)).dropna().astype(str).unique() if x]
    )
municipios_disponiveis = sorted(
    [
        x
        for x in resumo_all.get("municipio", pd.Series(dtype=str)).dropna().astype(str).unique()
        if x.strip().lower() not in {"", "nan", "none"}
    ]
)
_recorte = recorte_usuario(current_user())
if _recorte["lock_regional"] and _recorte["regionais"]:
    for _reg in _recorte["regionais"]:
        if _reg not in regionais_disponiveis:
            regionais_disponiveis = [_reg, *regionais_disponiveis]
    regionais_disponiveis = [x for x in regionais_disponiveis if x in _recorte["regionais"]]
if _recorte["lock_municipal"] and _recorte["municipios"]:
    for _mun in _recorte["municipios"]:
        if _mun not in municipios_disponiveis:
            municipios_disponiveis = [_mun, *municipios_disponiveis]
    municipios_disponiveis = [x for x in municipios_disponiveis if x in _recorte["municipios"]]
elif _recorte["lock_regional"] and _recorte["municipios"]:
    municipios_disponiveis = [x for x in municipios_disponiveis if x in set(_recorte["municipios"])] or list(_recorte["municipios"])
_default_reg = list(_recorte["regionais"]) if _recorte["lock_regional"] else []
_default_mun = list(_recorte["municipios"]) if _recorte["lock_municipal"] else []
with f1:
    regionais_sel = st.multiselect(
        "Regional de Saúde",
        regionais_disponiveis,
        default=_default_reg,
        placeholder="Todas as regionais SES-MT",
        help="Vazio = Estado inteiro. CRS oficiais da SES-MT.",
        key="filtro_regional_saude",
        disabled=bool(_recorte["lock_regional"]),
    )
if _recorte["lock_regional"]:
    regionais_sel = list(_recorte["regionais"])
tmp = resumo_all.copy()
if regionais_sel and "regional_saude" in tmp.columns:
    tmp = tmp[tmp["regional_saude"].isin(regionais_sel)]
municipios_filtrados = (
    sorted(tmp["municipio"].dropna().astype(str).unique())
    if "municipio" in tmp.columns
    else municipios_disponiveis
)
if _recorte["lock_municipal"] and _recorte["municipios"]:
    for _mun in _recorte["municipios"]:
        if _mun not in municipios_filtrados:
            municipios_filtrados = [_mun, *municipios_filtrados]
    municipios_filtrados = [x for x in municipios_filtrados if x in _recorte["municipios"]]
with f2:
    municipios_sel = st.multiselect(
        "Município",
        municipios_filtrados,
        default=_default_mun,
        placeholder="Todos os municípios do recorte",
        help="Opcional. Combina com a regional.",
        key="filtro_municipio",
        disabled=bool(_recorte["lock_municipal"]),
    )
if _recorte["lock_municipal"]:
    municipios_sel = list(_recorte["municipios"])
_niveis_opts = ["amarela", "laranja", "vermelha", "roxa"]
with f3:
    niveis_sel = st.multiselect(
        "Nível operacional",
        _niveis_opts,
        default=[],
        placeholder="Todos os níveis",
        help="Filtra mapas/tabelas pelo nível ARARAS (ex.: só laranja+).",
        key="filtro_nivel_operacional",
    )
_so_prioritarios = st.checkbox(
    "Só prioritários (laranja / vermelha / roxa)",
    value=False,
    key="filtro_so_prioritarios",
    help="Atalho equivalente a selecionar laranja+ no filtro de nível.",
)
st.markdown("</div>", unsafe_allow_html=True)

resumo = apply_global_filters(resumo_all, regionais_sel, municipios_sel)
map_df = apply_global_filters(map_df_all, regionais_sel, municipios_sel)
_niveis_efetivos = list(niveis_sel)
if _so_prioritarios:
    _niveis_efetivos = sorted(set(_niveis_efetivos) | {"laranja", "vermelha", "roxa"})
if _niveis_efetivos:
    if "nivel" in resumo.columns:
        resumo = resumo[resumo["nivel"].astype(str).str.lower().isin(_niveis_efetivos)]
    if "nivel" in map_df.columns:
        map_df = map_df[map_df["nivel"].astype(str).str.lower().isin(_niveis_efetivos)]
_rotulo_recorte = rotulo_recorte(regionais_sel, municipios_sel)
_view = resumo if not resumo.empty else resumo_all
sentinel = safe_sort(_view, ["score", "risco_cumulativo_3d"], ascending=[False, False]).iloc[0]
nivel_estado = normalize_level(sentinel.get("nivel"))
municipio_sentinel = sentinel.get("municipio", "—")
motivo_estado = replace_motivo_indisponivel(sentinel)
orientacao_sentinel = str(sentinel.get("orientacao_leiga", "") or "")
_reg_contexto = str(sentinel.get("regional_saude") or "").strip()
if municipios_sel and len(municipios_sel) == 1 and _reg_contexto:
    _rotulo_recorte = f"{municipios_sel[0]} · {_reg_contexto}"
_data_ref = ""
for _col in ("data_referencia", "data_processamento", "atualizado_em"):
    if _col in _view.columns and _view[_col].notna().any():
        _data_ref = str(_view[_col].dropna().astype(str).iloc[0])[:16]
        break

NAV_SECTIONS: list[str] = [
    "Guia do leitor",
    "Visão executiva",
    "Mapas",
    "Fontes e qualidade",
    "El Niño / Contingência",
    "Prontidão climática",
    "Clima / TITAN",
    "Qualidade do ar",
    "Assistência",
    "Arboviroses",
    "SIVEP",
    "Sentinela SG",
    "GeoCalor",
    "AdaptaSUS / Guia MS",
    "Eventos em saúde",
    "Correlação clima-saúde",
    "Cemaden / ANA",
    "Sazonalidade / OR",
    "Operacional",
    "Geografia",
    "Inteligência",
    "Alertas",
    "Cálculos",
]
SALA_PLANO_NAV = "Sala de Situação / Plano El Niño"
if _ABRIR_SALA:
    NAV_SECTIONS.append(SALA_PLANO_NAV)


def _nav_button_groups(*, publico: bool, abrir_sala: bool) -> list[tuple[str, list[tuple[str, str]]]]:
    """Mesmo layout de botões do painel público; o interno só acrescenta abas no mesmo padrão."""
    leitura = [
        ("Guia do leitor", "Guia do leitor"),
        ("Visão", "Visão executiva"),
        ("Mapas", "Mapas"),
        ("Território", "Geografia"),
    ]
    clima = [
        ("Qualidade do ar", "Qualidade do ar"),
        ("El Niño", "El Niño / Contingência"),
        ("Cemaden / ANA", "Cemaden / ANA"),
    ]
    saude = [
        ("Arboviroses", "Arboviroses"),
    ]
    analise = [
        ("Sazonalidade / OR", "Sazonalidade / OR"),
        ("Cálculos", "Cálculos"),
    ]
    if not publico:
        leitura.extend(
            [
                ("Fontes", "Fontes e qualidade"),
                ("Prontidão", "Prontidão climática"),
            ]
        )
        clima.extend(
            [
                ("Clima / TITAN", "Clima / TITAN"),
                ("GeoCalor", "GeoCalor"),
            ]
        )
        saude.extend(
            [
                ("Assistência", "Assistência"),
                ("SIVEP", "SIVEP"),
                ("Sentinela SG", "Sentinela SG"),
                ("AdaptaSUS", "AdaptaSUS / Guia MS"),
                ("Eventos", "Eventos em saúde"),
            ]
        )
        analise.extend(
            [
                ("Correlação", "Correlação clima-saúde"),
                ("Inteligência", "Inteligência"),
            ]
        )
    groups: list[tuple[str, list[tuple[str, str]]]] = [
        ("Leitura", leitura),
        ("Clima e ambiente", clima),
        ("Saúde", saude),
        ("Análise", analise),
    ]
    if not publico:
        operacao = [
            ("Alertas", "Alertas"),
            ("Operacional", "Operacional"),
        ]
        if abrir_sala:
            operacao.append(("Sala / Plano", SALA_PLANO_NAV))
        groups.append(("Operação", operacao))
    return groups


NAV_BUTTON_GROUPS = _nav_button_groups(publico=_PAINEL_PUBLICO, abrir_sala=_ABRIR_SALA)
NAV_GROUPS: dict[str, list[str]] = {
    titulo: [key for _lbl, key in itens] for titulo, itens in NAV_BUTTON_GROUPS
}
if _PAINEL_PUBLICO:
    NAV_SECTIONS = [s for s in NAV_SECTIONS if s != "Eventos em saúde"]
_NAV_VALID = {key for _g, itens in NAV_BUTTON_GROUPS for _lbl, key in itens}
_NAV_STATE = "nav_aba_painel"
if st.session_state.get(_NAV_STATE) not in _NAV_VALID:
    _legado = str(
        st.session_state.get("nav_aba_publica")
        or st.session_state.get("nav_aba_completa")
        or ""
    )
    st.session_state[_NAV_STATE] = _legado if _legado in _NAV_VALID else "Guia do leitor"
with st.sidebar:
    st.markdown('<div class="sis-nav-kicker">Navegação</div>', unsafe_allow_html=True)
    for _grupo, _itens in NAV_BUTTON_GROUPS:
        ui_theme.nav_label(_grupo)
        for _lbl, _key in _itens:
            _ativo = st.session_state[_NAV_STATE] == _key
            _nav_key = _key.replace(" / ", "_").replace(" ", "_")
            if st.button(
                _lbl,
                key=f"nav_btn_{_nav_key}",
                use_container_width=True,
                type="primary" if _ativo else "secondary",
            ):
                st.session_state[_NAV_STATE] = _key
                st.rerun()
    if is_admin(current_user()) and not _PAINEL_PUBLICO:
        ui_theme.nav_label("Administração")
        with st.expander("Gestão de cadastros e níveis", expanded=False):
            render_gestao_usuarios()
    SECTION_KEY = st.session_state[_NAV_STATE]

if SECTION_KEY == SALA_PLANO_NAV and not _ABRIR_SALA:
    SECTION_KEY = "Visão executiva"

_mostrar_home = SECTION_KEY == "Visão executiva"

intel_state = state_indicator_summary(_view)
prioridade_state = state_prioridade_summary(_view)

if _mostrar_home:
    ui_theme.status_strip(
        [
            ("Recorte", _rotulo_recorte),
            ("Nível", str(nivel_estado).upper()),
            ("Municípios", str(len(resumo))),
            ("Referência", _data_ref or "rodada atual"),
            ("Base", backend_name()),
        ],
    )
    ui_theme.level_banner(
        nivel_estado,
        str(municipio_sentinel),
        str(motivo_estado),
        orientacao=orientacao_sentinel,
    )

    if municipios_sel and len(municipios_sel) == 1 and _reg_contexto and "regional_saude" in resumo_all.columns:
        _reg_view = resumo_all[resumo_all["regional_saude"].astype(str) == _reg_contexto]
        if not _reg_view.empty:
            _reg_sent = safe_sort(_reg_view, ["score", "risco_cumulativo_3d"], ascending=[False, False]).iloc[0]
            ui_theme.callout(
                f"Filtro municipal ativo. Regional {_reg_contexto}: nível "
                f"{str(normalize_level(_reg_sent.get('nivel'))).upper()} · {len(_reg_view)} municípios · "
                f"sentinela da regional: {_reg_sent.get('municipio', '—')}.",
                "info",
            )

    ui_theme.callout(AVISO_SINAL_VS_ATIVACAO, "warn")

    with st.expander("Por que este nível? (município sentinela / crítico)", expanded=True):
        st.markdown(explicar_nivel_municipio(sentinel))

# Frescor / cobertura (não interpretar ausência como risco zero)
_frescor_home = build_fonte_frescor_home(resumo_all)
_frescor_sum = frescor_resumo(_frescor_home)
_data_proc = (
    str(pd.to_datetime(resumo_all["data_processamento"], errors="coerce").max())
    if "data_processamento" in resumo_all.columns
    else "—"
)
_ameaca = ameaca_dominante_estado(_view)
_n_verm_rox = int(
    _view["nivel"].astype(str).str.lower().isin(["vermelha", "roxa"]).sum()
) if "nivel" in _view.columns else 0
_n_mun_estado = max(len(_view), 1)
_n_subindo = int(intel_state.get("tendencia_subindo", 0) or 0)
_tend_rotulo = tendencia_estado_rotulo(_n_subindo, _n_mun_estado)
_pressao_media_top = (
    float(pd.to_numeric(_view["indice_pressao_saude"], errors="coerce").mean())
    if "indice_pressao_saude" in _view.columns
    and pd.to_numeric(_view["indice_pressao_saude"], errors="coerce").notna().any()
    else (
        float(pd.to_numeric(_view["pressao_calor_pct"], errors="coerce").mean())
        if "pressao_calor_pct" in _view.columns
        else None
    )
)

_sit_cards = [
    ("Nível operacional", str(nivel_estado).upper(), f"sentinela: {municipio_sentinel}"),
    ("Municípios em alerta", f"{_n_verm_rox}/{_n_mun_estado}", "vermelha + roxa"),
    (
        "Principal ameaça",
        _ameaca[:48],
        "o que mais puxou o nível (não é ML)",
    ),
    (
        "Tendência ~7 dias",
        tendencia_card_value(_n_subindo, _n_mun_estado),
        tendencia_card_caption(_n_subindo, _n_mun_estado),
    ),
    (
        "Pressão sobre a saúde",
        pressao_card_value(_pressao_media_top),
        pressao_card_caption(_pressao_media_top),
    ),
]
if _mostrar_home:
    ui_theme.section_title(
        f"Situação · {_rotulo_recorte}",
        "Nível operacional, tendência e pressão no recorte do filtro territorial",
    )
    ui_theme.insight_cards(_sit_cards)
    st.caption(
        "Nível Roxa ≠ pressão hospitalar alta. Tendência usa % do recorte "
        "(agravamento ≥15%). Pressão em escala 0–100 (alta ≥70)."
    )

    metrics = state_summary_with_prediction(_view, pred_v6)
    _semaforo_top = (
        _view["semaforo_pressao"].astype(str).str.lower().value_counts().to_dict()
        if "semaforo_pressao" in _view.columns
        else {}
    )

    ui_theme.section_title(
        f"Situação geral · {_rotulo_recorte}",
        "Atual · predição 7 dias · tendência — recorte do filtro territorial",
    )
    ui_theme.insight_cards(
        [
            (
                "Prioridade global",
                safe_metric_value(prioridade_state.get("media"), "", 0),
                f"alta+ {prioridade_state.get('n_alta_ou_mais', 0)} · ↑{prioridade_state.get('tendencia_aumento', 0)}",
            ),
            (
                "Tensão climática",
                safe_metric_value(intel_state.get("indice_tensao_climatica_media"), "", 0),
                "média estadual 0–100",
            ),
            (
                "Carga em saúde",
                safe_metric_value(intel_state.get("indice_carga_saude_media"), "", 0),
                "média estadual 0–100",
            ),
            (
                "Vigilância integrada",
                safe_metric_value(intel_state.get("indice_vigilancia_integrada_media"), "", 0),
                "prioridade composta",
            ),
                (
                    "Pressão saúde",
                    pressao_card_value(_pressao_media_top),
                    pressao_card_caption(_pressao_media_top)
                    + f" · G {_semaforo_top.get('verde', 0)} · A {_semaforo_top.get('amarela', 0)} · V {_semaforo_top.get('vermelha', 0)}",
                ),
                (
                    "Tendência ↑ em 7d",
                    tendencia_card_value(int(intel_state.get("tendencia_subindo", 0) or 0), max(len(_view), 1)),
                    tendencia_card_caption(int(intel_state.get("tendencia_subindo", 0) or 0), max(len(_view), 1)),
                ),
            ]
        )

    _tend_cli = metrics.get("tendencia_clima", "—")
    r1 = st.columns(8)
    metric_with_pred(
        r1[0],
        "Municípios",
        metrics.get("municipios", 0),
        metrics.get("municipios", 0),
        _tend_cli,
        "",
        0,
    )
    metric_with_pred(r1[1], "Tmax máx.", metrics.get("tmax"), metrics.get("tmax_pred"), metrics.get("tendencia_tmax", _tend_cli), " °C", 1)
    metric_with_pred(r1[2], "UTCI máx.", metrics.get("utci"), metrics.get("utci_pred"), metrics.get("tendencia_utci", _tend_cli), "", 1)
    metric_with_pred(r1[3], "Risco 3d máx.", metrics.get("risco3d"), metrics.get("risco3d_pred"), metrics.get("tendencia_risco3d", _tend_cli), "", 2)
    metric_with_pred(r1[4], "Ocupação média", metrics.get("ocup_media"), pd.NA, _tend_cli, "%", 1)
    metric_with_pred(r1[5], "Pressão média", metrics.get("pressao_media"), pd.NA, _tend_cli, "%", 1)
    metric_with_pred(r1[6], "PM2.5 máx.", metrics.get("pm25_max"), pd.NA, _tend_cli, "", 1)
    metric_with_pred(r1[7], "IQA máx.", metrics.get("iqar_max"), pd.NA, _tend_cli, "", 1)

    ui_theme.section_title(
        "Distribuição por nível (Verde → Roxa)",
        "Atual · predição 7d · tendência do número de municípios em cada cor",
    )
    ui_theme.level_legend()
    _pred_levels = metrics.get("pred_levels") or {}
    dist_cols = st.columns(5)
    for _idx, (_nivel, _label) in enumerate([
        ("verde", "Verde"),
        ("amarela", "Amarela"),
        ("laranja", "Laranja"),
        ("vermelha", "Vermelha"),
        ("roxa", "Roxa"),
    ]):
        _valor = int(metrics.get(_nivel, 0) or 0)
        _pred_n = int(_pred_levels.get(_nivel, 0) or 0)
        _tend_n = metrics.get(f"tendencia_{_nivel}", _trend_from_counts(_valor, _pred_n))
        _icon = _trend_icon(_tend_n)
        _tend_txt = _trend_pt(_tend_n)
        with dist_cols[_idx]:
            st.markdown(
                f"""
                <div class="sis-level-tile sis-level-tile-{_nivel}" style="background:{LEVEL_COLOR_MAP[_nivel]};color:{'#1a1a1a' if _nivel in ('amarela','cinza') else '#fff'};">
                    <div class="lbl">{_label}</div>
                    <div class="val">{_valor}</div>
                    <div class="pred">7d: {_pred_n}</div>
                    <div class="trend">{_icon} {_tend_txt}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    ui_theme.section_title(
        "Mapa de risco cumulativo 3 dias",
        f"Recorte: {_rotulo_recorte} · Tmáx, UTCI e nível no hover",
    )
    _map_risco = map_df if not map_df.empty else map_df_all
    if "risco_cumulativo_3d" in _map_risco.columns:
        choropleth_or_points(
            _map_risco,
            geojson_mun,
            "risco_cumulativo_3d",
            f"Risco cumulativo 3 dias · {_rotulo_recorte}",
            hover_cols=["regional_saude", "nivel", "tmax", "utci_proxy", "score", "municipio"],
            categorical=False,
        )
    else:
        st.info("Indicador risco_cumulativo_3d indisponível neste recorte.")

    if not _PAINEL_PUBLICO:
        ui_theme.section_title(
            "Prioridades de hoje",
            "Até 10 municípios para contato — situação → motivo → tendência → ação",
        )
        st.caption(
            f"Atualização do resumo: {_data_proc} · fontes OK {_frescor_sum['n_ok']}/{_frescor_sum['n_total']} "
            f"({_frescor_sum['pct_ok']:.0f}%) · {_frescor_sum['n_problema']} com defasagem/parcial/indisponível. "
            "Detalhe de fontes → aba **Fontes e qualidade**."
        )
        _prio_hoje = tabela_prioridades_hoje(_view, n=10)
        if _prio_hoje.empty:
            st.info("Sem municípios para priorizar neste recorte.")
        else:
            show_df(_prio_hoje, height=320)
            if "flag_persistencia_roxa" in _view.columns:
                _n_persist = int(pd.to_numeric(_view["flag_persistencia_roxa"], errors="coerce").fillna(0).gt(0).sum())
                if _n_persist:
                    st.caption(
                        f"{_n_persist} município(s) com flag de persistência roxa "
                        f"(EHF/onda ≥ limiar de dias em settings)."
                    )

# Índice de pressão (IndicaSUS · SISREG · SINAN · SIM) — semáforo G/A/V
from sisclima.engines.indice_pressao_saude import (
    build_indice_pressao_municipal,
    catalogo_agravos,
    format_kpi_label,
    state_pressao_summary,
)

_pressao_full = build_indice_pressao_municipal(
    resumo_all,
    sim_mun=sim_obitos_mun if not sim_obitos_mun.empty else None,
    saude_calor_mun=saude_calor_mun if not saude_calor_mun.empty else None,
    pred_7d=pred_v6 if not pred_v6.empty else None,
    sisreg=sisreg_tab if not sisreg_tab.empty else None,
)
_pressao_cols = [
    c
    for c in _pressao_full.columns
    if c.startswith("kpi_")
    or c.startswith("indice_pressao")
    or c.startswith("semaforo_pressao")
    or c.startswith("pred_indice")
    or c.startswith("pred_nivel_clima")
    or c.startswith("tendencia_pressao")
    or c == "pilares_disponiveis"
]
if not _pressao_full.empty and "cod_ibge" in _pressao_full.columns:
    _merge_p = _pressao_full[["cod_ibge"] + [c for c in _pressao_cols if c in _pressao_full.columns]].copy()
    drop_overlap = [c for c in _merge_p.columns if c != "cod_ibge" and c in resumo_all.columns]
    if drop_overlap:
        resumo_all = resumo_all.drop(columns=drop_overlap, errors="ignore")
    resumo_all = resumo_all.merge(_merge_p, on="cod_ibge", how="left")
    resumo = apply_global_filters(resumo_all, regionais_sel, municipios_sel)
    if _niveis_efetivos and "nivel" in resumo.columns:
        resumo = resumo[resumo["nivel"].astype(str).str.lower().isin(_niveis_efetivos)]
    if "cod_ibge" in map_df_all.columns:
        map_base = map_df_all.copy()
        drop_m = [c for c in _merge_p.columns if c != "cod_ibge" and c in map_base.columns]
        if drop_m:
            map_base = map_base.drop(columns=drop_m, errors="ignore")
        map_df_all = map_base.merge(_merge_p, on="cod_ibge", how="left")
        map_df = apply_global_filters(map_df_all, regionais_sel, municipios_sel)
        if _niveis_efetivos and "nivel" in map_df.columns:
            map_df = map_df[map_df["nivel"].astype(str).str.lower().isin(_niveis_efetivos)]
pressao_df = (
    apply_global_filters(_pressao_full, regionais_sel, municipios_sel)
    if not _pressao_full.empty
    else _pressao_full
)
pressao_state = state_pressao_summary(pressao_df)

# Prioridade global (camadas 0–100) — recalcula após pressão IndicaSUS/SISREG/SINAN/SIM
resumo_all = enrich_prioridade_global(resumo_all)
resumo = apply_global_filters(resumo_all, regionais_sel, municipios_sel)
if _niveis_efetivos and "nivel" in resumo.columns:
    resumo = resumo[resumo["nivel"].astype(str).str.lower().isin(_niveis_efetivos)]
if "cod_ibge" in map_df_all.columns and "indice_prioridade_global" in resumo_all.columns:
    _prio_cols = [
        c
        for c in (
            "cod_ibge",
            "indice_prioridade_global",
            "faixa_prioridade_global",
            "completude_prioridade_pct",
            "tendencia_prioridade_7d",
            "orientacao_prioridade",
            "pilares_prioridade",
        )
        if c in resumo_all.columns
    ]
    _prio = resumo_all[_prio_cols].copy()
    drop_m = [c for c in _prio.columns if c != "cod_ibge" and c in map_df_all.columns]
    if drop_m:
        map_df_all = map_df_all.drop(columns=drop_m, errors="ignore")
    map_df_all = map_df_all.merge(_prio, on="cod_ibge", how="left")
    map_df = apply_global_filters(map_df_all, regionais_sel, municipios_sel)
    if _niveis_efetivos and "nivel" in map_df.columns:
        map_df = map_df[map_df["nivel"].astype(str).str.lower().isin(_niveis_efetivos)]
prioridade_state = state_prioridade_summary(resumo)

hydrate_section_tables(SECTION_KEY)

# ---------------------------------------------------------------------
# Seções do painel
# ---------------------------------------------------------------------
if SECTION_KEY == "Guia do leitor":
    ui_theme.section_title("Guia do leitor", "Linguagem simples para quem não é especialista")
    st.markdown(
        "### Como usar o painel"
        if _PAINEL_PUBLICO
        else "### Como usar o painel em 5 passos"
    )
    for line in (HOW_TO_READ_PUBLIC if _PAINEL_PUBLICO else HOW_TO_READ_PANEL):
        st.markdown(f"- {line}")

    st.markdown("### O que cada cor significa")
    for key, meta in LEVEL_GUIDE.items():
        if key == "cinza":
            continue
        color = LEVEL_COLOR_MAP.get(key, "#334155")
        st.markdown(
            f"""
            <div class="sis-card" style="border-left:6px solid {color}">
              <b>{meta['titulo']}</b><br/>
              <span style="color:#5b6f68">{meta['o_que_e']}</span><br/>
              <b>O que fazer:</b> {meta['o_que_fazer']}<br/>
              <i>{meta['analogia']}</i>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### Glossário de indicadores")
    _gloss_keys = GLOSSARIO_PUBLICO if _PAINEL_PUBLICO else list(INDICATOR_GLOSSARY.keys())
    for gkey in _gloss_keys:
        meta = INDICATOR_GLOSSARY.get(gkey)
        if not meta:
            continue
        st.markdown(
            f"**{meta['nome']}** — {meta['leigo']}  \n"
            f"*Como ler:* {meta['como_ler']}"
        )

    if _PAINEL_PUBLICO:
        ui_theme.callout(
            "Este guia é didático. Decisões oficiais seguem protocolos da SES-MT e boletins do INMET/CPTEC.",
            "tip",
        )
    else:
        ui_theme.callout(
            "Este guia é didático. Decisões oficiais seguem protocolos do CIEVS/SES e boletins do INMET/CPTEC.",
            "tip",
        )

elif SECTION_KEY == "Fontes e qualidade":
    ui_theme.section_title(
        "Fontes e qualidade",
        "Ambiente da base, frescor e cobertura — ausência ≠ risco zero",
    )
    ui_theme.insight_cards(
        [
            ("Backend", backend_name(), "motor de dados do painel"),
            ("Fontes OK", f"{_frescor_sum['n_ok']}/{_frescor_sum['n_total']}", f"{_frescor_sum['pct_ok']:.0f}% na janela"),
            ("Com problema", str(_frescor_sum["n_problema"]), "defasagem / parcial / indisponível"),
            ("Referência", _data_ref or "rodada atual", "data do resumo municipal"),
        ]
    )
    if backend_name() != "postgresql":
        ui_theme.callout(
            f"Ambiente atual: {backend_name()} (não PostgreSQL). "
            "Se esperava Docker/Postgres, verifique DATABASE_URL. "
            "Abas incompletas podem refletir esse fallback (ex.: seed Cloud SQLite).",
            "warn",
        )
    else:
        ui_theme.callout(
            "Backend PostgreSQL ativo — preferencial para operação local/VPN SES.",
            "tip",
        )
    st.markdown("#### Frescor e cobertura por fonte")
    ui_theme.callout(
        "Fonte fora da janela esperada deve ser lida com baixa confiabilidade "
        "e não como ‘tudo bem’. Dado ausente não é risco zero.",
        "info",
    )
    if _frescor_home.empty:
        st.info("Sem metadados de frescor nesta base. Rode o enrichment/orquestrador.")
    else:
        show_df(_frescor_home, height=420)
    st.caption(
        f"Atualização do resumo municipal: {_data_proc}. "
        "Para regenerar: `regenerar_sistema_completo.py` (export Cloud ligado por padrão)."
    )

elif SECTION_KEY == "Visão executiva":
    ui_theme.section_title("Visão executiva", "Mapa + priorização — sequência: situação → motivo → ação")
    ui_theme.callout(AVISO_SINAL_VS_ATIVACAO, "warn")
    ui_theme.callout(
        "Cores no mapa = classificação operacional do ARARAS (não ativação formal de emergência). "
        "O alerta integrado une clima/saúde com INMET, Cemaden, solo e hidro (TITAN).",
        "info",
    )

    st.markdown("#### Prioridades no recorte filtrado")
    _prio_filtro = tabela_prioridades_hoje(resumo, n=10)
    if _prio_filtro.empty:
        st.info("Sem municípios no filtro atual.")
    else:
        show_df(_prio_filtro, height=300)
        mun_opts = _prio_filtro["Município"].astype(str).tolist()
        if mun_opts:
            mun_sel = st.selectbox("Detalhar ‘por que este nível’", mun_opts, key="exec_porque_nivel")
            row = resumo[resumo["municipio"].astype(str) == str(mun_sel)]
            if not row.empty:
                st.markdown(explicar_nivel_municipio(row.iloc[0]))

    # Cards alerta integrado
    if not alerta_integrado.empty and "nivel_alerta_integrado" in alerta_integrado.columns:
        ai_f = alerta_integrado.copy()
        if "cod_ibge" in ai_f.columns and "cod_ibge" in resumo.columns:
            ai_f = ai_f[ai_f["cod_ibge"].astype(str).isin(resumo["cod_ibge"].dropna().astype(str))]
        n_int = int((pd.to_numeric(ai_f.get("score_alerta_integrado"), errors="coerce").fillna(0) >= 2).sum())
        ui_theme.insight_cards(
            [
                ("Alerta integrado ≥ laranja", n_int, "ARARAS MT"),
                ("Solo méd.", safe_metric_value(pd.to_numeric(resumo.get("indice_saturacao_solo"), errors="coerce").mean() if "indice_saturacao_solo" in resumo.columns else None, "", 0), "0–100"),
                ("INMET registros", len(inmet_alertas), "oficiais"),
                ("Cemaden registros", len(cemaden_alertas_tab), "oficiais"),
            ]
        )

    choropleth_or_points(
        map_df,
        geojson_mun,
        "risco_cumulativo_3d",
        "Risco cumulativo 3 dias",
        hover_cols=[
            "regional_saude", "nivel", "tmax", "utci_proxy", "score",
            "indice_vigilancia_integrada", "ocupacao_leitos_pct", "motivo",
        ],
        categorical=False,
    )
    choropleth_or_points(
        map_df,
        geojson_mun,
        "nivel",
        "Nível operacional municipal (classificação ARARAS)",
        hover_cols=[
            "regional_saude", "score", "tmax", "utci_proxy", "risco_cumulativo_3d",
            "indice_vigilancia_integrada", "indice_saturacao_solo", "nivel_alerta_integrado",
            "tendencia_7d", "orientacao_leiga",
            "ocupacao_leitos_pct", "pressao_calor_pct", "motivo",
        ],
        categorical=True,
    )

    with st.expander("Tabela analítica completa do recorte", expanded=False):
        cols = [
            c
            for c in [
                "cod_ibge",
                "municipio",
                "regional_saude",
                "nivel",
                "score",
                "indice_prioridade_global",
                "faixa_prioridade_global",
                "tendencia_prioridade_7d",
                "indice_vigilancia_integrada",
                "indice_tensao_climatica",
                "indice_carga_saude",
                "indice_pressao_saude",
                "tendencia_7d",
                "percentil_risco_estadual",
                "completude_prioridade_pct",
                "tmax",
                "utci_proxy",
                "risco_cumulativo_3d",
                "ocupacao_leitos_pct",
                "pressao_calor_pct",
                "orientacao_prioridade",
                "orientacao_leiga",
                "motivo",
            ]
            if c in resumo.columns
        ]
        sort_keys = [
            c
            for c in ["indice_prioridade_global", "indice_vigilancia_integrada", "score", "risco_cumulativo_3d"]
            if c in resumo.columns
        ]
        show_df(
            safe_sort(resumo, sort_keys, ascending=[False] * len(sort_keys)) if sort_keys else resumo,
            cols,
            height=420,
        )


# ---------------------------------------------------------------------
# El Niño / Plano de Contingência
# ---------------------------------------------------------------------
elif SECTION_KEY == "El Niño / Contingência":
    ui_theme.section_title(
        "El Niño — cenário e preparação",
        "Leitura do cenário oficial e do boletim da semana (não substitui boletins INMET/INPE/CPTEC)"
        if _PAINEL_PUBLICO
        else "Instrumento operacional ligado ao CIEVS-MT (não substitui boletins INMET/INPE/CPTEC)",
    )
    ui_theme.callout(AVISO_SINAL_VS_ATIVACAO, "warn")
    ui_theme.callout(
        "Cenário sazonal e status ENSO vêm de fontes oficiais. O ARARAS contribui com nível municipal, "
        "tendência ~7d, capacidade assistencial e prioridades de contato — não com forecast climático sazonal.",
        "info",
    )

    enso = _load_painel_el_nino()
    mt = enso.get("mato_grosso") or {}
    enso_bloco = enso.get("enso") or {}

    c1, c2, c3 = st.columns(3)
    c1.metric("Nível operacional ARARAS", str(nivel_estado).upper())
    c2.metric("Municípios vermelha/roxa", _n_verm_rox)
    c3.metric(
        "Tendência estadual ~7d",
        tendencia_card_value(_n_subindo, _n_mun_estado),
        tendencia_card_caption(_n_subindo, _n_mun_estado),
    )

    st.markdown("#### Cenário oficial (Painel El Niño)")
    if enso:
        e1, e2, e3 = st.columns(3)
        e1.metric("Boletim", f"n.º {enso.get('edicao', '—')} · {enso.get('mes_referencia', '')}")
        e2.metric("Trimestre climático", str(enso.get("trimestre") or "—"))
        e3.metric("ENSO", "El Niño")
        st.caption(str(enso_bloco.get("status") or ""))
        st.markdown(
            f"- **Intensidade:** {enso_bloco.get('intensidade', '—')}\n"
            f"- **Persistência:** {enso_bloco.get('persistencia', '—')}\n"
            f"- **Chuva em MT:** {mt.get('chuva', '—')}\n"
            f"- **Temperatura:** {mt.get('temperatura', '—')}\n"
            f"- **Monitor de Secas:** {mt.get('monitor_secas_jun2026', '—')}\n"
            f"- **Hidro Pantanal:** {mt.get('hidro_pantanal', '—')}\n"
            f"- **Risco de fogo ASO:** {mt.get('risco_fogo', '—')}"
        )
        ui_theme.callout(
            "MT livre de seca no Monitor de junho/2026 não reduz o alerta de queimadas/fumaça no ASO "
            "nem a atenção à bacia do Paraguai. A predição ~7d do ARARAS não substitui este boletim.",
            "warn",
        )
        st.caption(f"Órgãos: {enso.get('orgaos', 'INMET/INPE/ANA/CEMADEN')}. Arquivo operacional: `config/painel_el_nino.yaml`.")
    else:
        st.markdown(
            """
- **Fontes:** Painel El Niño INMET–INPE–ANA–Cemaden (boletim mensal) e notas técnicas conjuntas.
- **Uso no CIEVS:** alinhar ameaças esperadas (calor, seca/estiagem, fumaça, hidrologia) às ações do plano estadual.
- **No ARARAS:** cruzar com Prioridades de hoje e abas Clima / Qualidade do ar / Cemaden–ANA / Assistência.
            """
        )

    st.markdown(
        "#### Relatório da semana" if _PAINEL_PUBLICO else "#### Relatório semanal da sala de situação"
    )
    st.caption(
        "Segue o sumário do Painel El Niño n.º 02 (ASO) e cruza com os dados reais desta rodada no ARARAS."
        if _PAINEL_PUBLICO
        else "Segue o sumário do Painel El Niño n.º 02 (jul/2026). Cenário oficial ASO + nowcast municipal do ARARAS. "
        "Não é forecast sazonal nem ativa COE."
    )
    try:
        _bol_en = build_boletim_semanal(resumo, publico=_PAINEL_PUBLICO)
        _sem = _bol_en.get("semana") or {}
        b1, b2, b3 = st.columns(3)
        b1.metric("Semana", str(_sem.get("rotulo") or "—"))
        b2.metric("Período", str(_sem.get("periodo_pt") or "—"))
        b3.metric("Vermelha/roxa", int((_bol_en.get("snapshot") or {}).get("n_vermelha_roxa") or 0))
        with st.expander(
            "Texto do relatório" if _PAINEL_PUBLICO else "Texto para projetar / ler na reunião",
            expanded=True,
        ):
            st.markdown(_bol_en.get("markdown") or "—")
        st.download_button(
            "Baixar relatório da semana (.md)",
            data=str(_bol_en.get("markdown") or "").encode("utf-8"),
            file_name=str(_bol_en.get("arquivo") or "Boletim_ElNino_semanal.md"),
            mime="text/markdown",
            key="dl_boletim_elnino_semanal",
        )
    except Exception as exc:
        st.caption(f"Boletim semanal indisponível: {exc}")

    if not _PAINEL_PUBLICO:
        try:
            from sisclima.ui.decretos_emergencia import render_decretos_emergencia

            render_decretos_emergencia(allow_refresh=True)
        except Exception as exc:
            st.caption(f"Módulo de decretos indisponível: {exc}")

    if not _PAINEL_PUBLICO:
        st.caption(
            "Eventos de campo (rumor/cluster/impacto climático): aba **Eventos em saúde** "
            "(SMS/CRS notifica · CIEVS tria). Não substitui o SINAN."
        )
        st.markdown("#### Municípios prioritários (sinal ARARAS desta rodada)")
        st.caption(
            "Inclui ocupação, capacidade CNES, resiliência e lacunas de dado — "
            "para cruzar ameaça climática com capacidade assistencial."
        )
        show_df(tabela_prioridades_hoje(resumo, n=10), height=300)

        st.markdown("#### Matriz operacional (esqueleto do plano)")
        st.caption(
            "Preencha Status/Responsável/Prazo com a planilha institucional do plano. "
            "O ARARAS marca a coluna ‘Gatilho ARARAS’ conforme o nível atual — isso **não** executa a ação automaticamente."
        )
        _matriz = pd.DataFrame(
            [
                {
                    "Meta": "Comunicação de risco",
                    "Ação": "Boletim às Regionais e municípios prioritários",
                    "Responsável": "CIEVS / Comunicação SES",
                    "Prazo": "≤2h após sinal laranja+",
                    "Prioridade": "Alta",
                    "Status": "A validar",
                    "Indicador": "Nível ARARAS + tendência 7d",
                    "Gatilho ARARAS": "laranja+" if STAGE_ORDER.get(nivel_estado, -1) >= STAGE_ORDER.get("laranja", 2) else "abaixo",
                },
                {
                    "Meta": "Assistência e regulação",
                    "Ação": "Checar leitos, UTI e filas SISREG nos prioritários",
                    "Responsável": "Regulação / Hospitais",
                    "Prazo": "Mesmo dia",
                    "Prioridade": "Alta",
                    "Status": "A validar",
                    "Indicador": "Ocupação / pressão saúde",
                    "Gatilho ARARAS": "pressão alta ou ocupação ≥75%",
                },
                {
                    "Meta": "Grupos vulneráveis",
                    "Ação": "Busca ativa APS (idosos, crianças, rua)",
                    "Responsável": "APS / Regionais",
                    "Prazo": "24–48h",
                    "Prioridade": "Alta",
                    "Status": "A validar",
                    "Indicador": "Nível + vulnerabilidade",
                    "Gatilho ARARAS": "amarela+",
                },
                {
                    "Meta": "Fumaça / ar",
                    "Ação": "PFF2 conforme IQA; conferir broncodilatadores e corticoides (CBAF) e redistribuir linha respiratória (SAF/SES)",
                    "Responsável": "SAF estadual + farmácia municipal / Visa",
                    "Prazo": "Contínuo na estiagem / IQA amarelo+",
                    "Prioridade": "Alta",
                    "Status": "A validar",
                    "Indicador": "PM2,5 / IQA",
                    "Gatilho ARARAS": "PM2,5 ≥15 (sensíveis); ≥25 PFF2 grupo risco; ≥50 exposição externa; ≥75 toda população",
                },
                {
                    "Meta": "Inundação / água segura",
                    "Ação": "Conferir hipoclorito 2,5%, SRO e comunicação de água segura (Visa municipal; estoque estratégico SES)",
                    "Responsável": "Visa municipal + SAF/Visa estadual",
                    "Prazo": "Antes do pico da cota / alerta hidro",
                    "Prioridade": "Alta",
                    "Status": "A validar",
                    "Indicador": "Hidro ANA / solo saturado",
                    "Gatilho ARARAS": "situação hidro cheia/inundação ou alerta laranja+",
                },
                {
                    "Meta": "Hidrologia / seca",
                    "Ação": "Monitorar Cemaden/ANA e pontos críticos",
                    "Responsável": "Defesa Civil / Vigilância",
                    "Prazo": "Conforme alerta oficial",
                    "Prioridade": "Média",
                    "Status": "A validar",
                    "Indicador": "Alertas oficiais + solo",
                    "Gatilho ARARAS": "alerta oficial ou solo extremo",
                },
                {
                    "Meta": "Avaliação de ativação",
                    "Ação": "Reunião CIEVS: critérios técnicos → decisão documentada",
                    "Responsável": "Autoridade competente SES",
                    "Prazo": "Quando critérios persistirem",
                    "Prioridade": "Crítica",
                    "Status": "Humana",
                    "Indicador": "Critérios técnicos identificados (não ‘COE ativado’)",
                    "Gatilho ARARAS": "sinal analítico / alerta operacional",
                },
            ]
        )
        show_df(_matriz, height=320)

        st.markdown("#### Ligação nível → ação típica")
        for niv in ["amarela", "laranja", "vermelha", "roxa"]:
            recs = recommendations_for_stage(niv)
            with st.expander(f"Nível {niv} — checklist sugerido", expanded=(niv == nivel_estado)):
                for eixo, texto in recs:
                    st.markdown(f"- **{eixo}:** {texto}")

        st.markdown("#### Atenção farmacêutica neste cenário (142 municípios)")
        try:
            from sisclima.engines.atencao_farmaceutica import recomendacoes_pipeline

            for eixo, texto in recomendacoes_pipeline(nivel_estado, resumo):
                st.markdown(f"- **{eixo}:** {texto}")
            farm_cols = [c for c in ["municipio", "pm25_ugm3", "iq_ar_score", "orientacao_mascara_iqa", "acao_farmaceutica_municipal"] if c in resumo.columns]
            if "pm25_ugm3" in resumo.columns and farm_cols:
                top_ar = resumo.sort_values("pm25_ugm3", ascending=False)[farm_cols].head(8)
                st.caption("Municípios com pior PM2,5 — ação municipal sugerida (CBAF/Visa).")
                show_df(top_ar, height=260)
        except Exception as exc:
            st.caption(f"Ações farmacêuticas do cenário indisponíveis: {exc}")

    st.caption(
        "Referências: docs/apresentacoes/REFERENCIAS_ABNT_6023.md · Painel El Niño n.º 02 (jul/2026). "
        "Atualize `config/painel_el_nino.yaml` quando sair o boletim seguinte."
    )


elif SECTION_KEY == "Eventos em saúde":
    from sisclima.ui.eventos_saude import render_eventos_saude

    render_eventos_saude(resumo)

elif SECTION_KEY == "Sala de Situação / Plano El Niño":
    from sisclima.ui.sala_situacao_plano import render_sala_situacao_plano

    render_sala_situacao_plano()

elif SECTION_KEY == "Prontidão climática":
    render_prontidao(resumo)


# ---------------------------------------------------------------------
# Tab 2
# ---------------------------------------------------------------------
elif SECTION_KEY == "Mapas":
    st.subheader("Mapas municipais por shapefile/polígono")
    ui_theme.callout(
        "Se o mapa aparecer ‘vazio’ em PM2,5 ou leitos, a cobertura da fonte é parcial — não significa risco zero.",
        "warn",
    )
    if not _PAINEL_PUBLICO:
        render_interpretacao(
            "mapas",
            GUIDE_MAPAS,
            lambda: narrativa_mapas(resumo),
        )

    st.markdown("#### Painel de mapas temáticos")
    mapas_tematicos = [
        ("Risco cumulativo 3 dias", "risco_cumulativo_3d"),
        ("Vigilância integrada (0–100)", "indice_vigilancia_integrada"),
        ("Tensão climática (0–100)", "indice_tensao_climatica"),
        ("Carga em saúde (0–100)", "indice_carga_saude"),
        ("Ocupação de leitos IndicaSUS", "ocupacao_leitos_pct"),
        ("Pressão assistencial proxy", "pressao_calor_pct"),
        ("Vulnerabilidade ao calor", "indice_vulnerabilidade_calor"),
        ("PM2.5", "pm25_ugm3"),
        ("Índice de qualidade do ar", "iq_ar_score"),
    ]
    for _i, (_titulo, _col) in enumerate(mapas_tematicos):
        with st.expander(_titulo, expanded=(_i == 0)):
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

    st.markdown("#### Rede CNES e territórios vulneráveis")
    st.caption(
        "Unidades de saúde (CNES) e aldeias/quilombos/assentamentos no mesmo recorte. "
        "Distância até APS/hospital é o trajeto viário (OSRM); a linha reta só pré-seleciona candidatos."
    )
    from sisclima.ui.mapa_gestao_territorio import render_mapa_gestao_territorio

    render_mapa_gestao_territorio(resumo, allow_fetch=not _PAINEL_PUBLICO)

    st.markdown("#### Mapa preditivo 7 dias")
    st.caption("Nível operacional previsto para a semana seguinte no recorte filtrado. Não é cenário sazonal.")
    if pred_v6.empty:
        st.info("Predição 7 dias indisponível nesta rodada.")
    else:
        pv = pred_v6.copy()
        if "cod_ibge" in pv.columns and "cod_ibge" in resumo.columns:
            pv["cod_ibge"] = normalize_cod_ibge(pv["cod_ibge"])
            pv = pv[pv["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
        if "nivel_predicao_7d" in pv.columns and "cod_ibge" in map_df.columns:
            map_pred = map_df.merge(
                pv[[
                    c for c in [
                        "cod_ibge", "nivel_predicao_7d", "risco_preditivo_score",
                        "tmax_max_7d", "utci_proxy_max_7d",
                        "risco_cumulativo_3d_max_7d", "dias_onda_calor_prevista_7d",
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
                    c for c in [
                        "regional_saude", "nivel", "nivel_predicao_7d", "risco_preditivo_score",
                        "tmax_max_7d", "utci_proxy_max_7d", "risco_cumulativo_3d_max_7d",
                    ] if c in map_pred.columns
                ],
                categorical=True,
            )
        else:
            st.info("Campo nivel_predicao_7d indisponível para o mapa preditivo.")

    st.markdown("#### SIM — óbitos monitorados por grupo CID")
    if not sim_obitos_serie.empty:
        so = sim_obitos_serie.copy()
        if "mes" in so.columns:
            so["mes"] = pd.to_datetime(so["mes"].astype(str) + "-01", errors="coerce")
            fig = px.line(so, x="mes", y="obitos", color="grupo_obito_calor", title="Óbitos SIM sensíveis ao calor — série estadual")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Série estadual de óbitos SIM ainda não disponível nesta rodada.")

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
                title="Série estadual de agravos sensíveis ao calor por fonte",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Série estadual de agravos sensíveis ao calor ainda não consolidada nesta rodada.")


# ---------------------------------------------------------------------
# Tab 3
# ---------------------------------------------------------------------
elif SECTION_KEY == "Clima / TITAN":
    ui_theme.section_title(
        "Clima / TITAN (incorporado ao ARARAS)",
        "Calor, saturação do solo e alertas oficiais — o ARARAS incorpora a camada TITAN",
    )
    ui_theme.callout(
        "Fontes oficiais e código legível (sem scrapers ofuscados). Solo via Open-Meteo; alertas via INMET/Cemaden/ANA.",
        "tip",
    )
    render_interpretacao(
        "clima_titan",
        GUIDE_CLIMA_TITAN,
        lambda: narrativa_clima_titan(resumo, solo_sat),
    )
    st.markdown("Documento: `docs/INTEGRACAO_TITAN_SOLO_ALERTAS.md`")

    met_f = met.copy()
    if not met_f.empty and "cod_ibge" in met_f.columns and "cod_ibge" in resumo.columns:
        met_f = met_f[met_f["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
    elif not met_f.empty and municipios_sel and "municipio" in met_f.columns:
        met_f = met_f[met_f["municipio"].isin(municipios_sel)]

    # ---- Calor ----
    st.markdown("### Calor e biometeorologia")
    if not met_f.empty:
        met_f = ensure_numeric(met_f, ["tmax", "tmin", "tmedia", "utci_proxy", "risco_cumulativo_3d", "heat_index", "umidade_media", "indice_saturacao_solo"])
        if "data" in met_f.columns:
            met_f["data"] = pd.to_datetime(met_f["data"], errors="coerce")

        intel_cli = state_indicator_summary(resumo)
        sat_media = pd.to_numeric(resumo.get("indice_saturacao_solo"), errors="coerce").mean() if "indice_saturacao_solo" in resumo.columns else None
        ui_theme.insight_cards(
            [
                ("Tensão climática méd.", safe_metric_value(intel_cli.get("indice_tensao_climatica_media"), "", 0), "índice 0–100"),
                ("Tmax máx.", safe_metric_value(pd.to_numeric(resumo.get("tmax"), errors="coerce").max() if "tmax" in resumo.columns else None, " °C", 1), "no recorte"),
                ("Risco 3d máx.", safe_metric_value(pd.to_numeric(resumo.get("risco_cumulativo_3d"), errors="coerce").max() if "risco_cumulativo_3d" in resumo.columns else None, "", 1), "acumulado"),
                ("Saturação solo méd.", safe_metric_value(sat_media, "", 0), "índice 0–100"),
            ]
        )

        col_a, col_b = st.columns(2)
        with col_a:
            make_bar(resumo, "municipio", "risco_cumulativo_3d", "Top risco cumulativo 3 dias")
        with col_b:
            y_col = "indice_tensao_climatica" if "indice_tensao_climatica" in resumo.columns else "utci_proxy"
            make_bar(resumo, "municipio", y_col, "Top tensão climática" if y_col.startswith("indice") else "Top UTCI proxy")

        municipios = sorted(met_f["municipio"].dropna().astype(str).unique()) if "municipio" in met_f.columns else []
        default_muns = municipios[:8]
        selected = st.multiselect("Municípios no gráfico temporal de clima", municipios, default=default_muns)
        plot_met = met_f[met_f["municipio"].isin(selected)] if selected and "municipio" in met_f.columns else met_f
        make_line(
            plot_met,
            "data",
            [c for c in ["tmax", "tmedia", "utci_proxy", "risco_cumulativo_3d", "indice_saturacao_solo"] if c in plot_met.columns],
            "Série temporal climática e biometeorológica",
        )
    else:
        st.info("Tabela met_biometeo não disponível para os filtros selecionados.")

    # ---- Solo ----
    st.markdown("### Saturação do solo")
    solo_f = solo_sat.copy() if isinstance(solo_sat, pd.DataFrame) else pd.DataFrame()
    if solo_f.empty and "indice_saturacao_solo" in resumo.columns:
        solo_f = resumo.copy()
    if not solo_f.empty and "cod_ibge" in solo_f.columns and "cod_ibge" in resumo.columns:
        solo_f = solo_f[solo_f["cod_ibge"].astype(str).isin(resumo["cod_ibge"].dropna().astype(str))]
    if not solo_f.empty and "indice_saturacao_solo" in solo_f.columns:
        n_crit = int(solo_f.get("classe_saturacao_solo", pd.Series(dtype=str)).astype(str).str.lower().isin(["critica", "crítica", "alta"]).sum()) if "classe_saturacao_solo" in solo_f.columns else 0
        c1, c2, c3 = st.columns(3)
        c1.metric("Municípios com solo", int(pd.to_numeric(solo_f["indice_saturacao_solo"], errors="coerce").notna().sum()))
        c2.metric("Índice médio", safe_metric_value(pd.to_numeric(solo_f["indice_saturacao_solo"], errors="coerce").mean(), "", 0))
        c3.metric("Alta/crítica", n_crit)
        make_bar(solo_f, "municipio", "indice_saturacao_solo", "Top saturação do solo")
        show_df(
            safe_sort(solo_f, ["indice_saturacao_solo"], ascending=[False]),
            [c for c in ["cod_ibge", "municipio", "regional_saude", "indice_saturacao_solo", "classe_saturacao_solo", "umidade_solo_media", "precipitacao_mm", "nivel"] if c in solo_f.columns],
            height=280,
        )
    else:
        st.info("Saturação do solo ainda não gerada. Rode completar_sistema_operacional.py com USE_OPENMETEO=true.")

    # ---- Alertas TITAN ----
    st.markdown("### Alertas oficiais (INMET + Cemaden + ANA)")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("INMET", len(inmet_alertas) if not inmet_alertas.empty else 0)
    a2.metric("Cemaden", len(cemaden_alertas_tab) if not cemaden_alertas_tab.empty else 0)
    a3.metric("ANA risco", len(ana_risco_tab) if not ana_risco_tab.empty else 0)
    a4.metric("Hidro risco", len(hidro_risco) if not hidro_risco.empty else 0)

    tab_in, tab_ce, tab_an, tab_hi = st.tabs(["INMET", "Cemaden", "ANA chuva/cota", "Hidro risco"])
    with tab_in:
        if inmet_alertas.empty:
            st.info("Sem alertas INMET nesta rodada (configure INMET_ALERTS_URL ou CSV).")
        else:
            show_df(
                inmet_alertas,
                [c for c in ["data", "data_emissao", "municipio", "cod_ibge", "uf", "nivel_alerta", "severidade", "evento", "descricao", "fonte"] if c in inmet_alertas.columns],
                height=260,
            )
    with tab_ce:
        if cemaden_alertas_tab.empty:
            st.info("Sem alertas Cemaden nesta rodada.")
        else:
            show_df(
                cemaden_alertas_tab,
                [c for c in ["data", "cod_ibge", "municipio", "uf", "tipo_risco", "evento", "nivel_alerta", "nivel_sis", "status", "fonte"] if c in cemaden_alertas_tab.columns],
                height=260,
            )
    with tab_an:
        if ana_risco_tab.empty:
            st.info("Sem ana_risco_municipal nesta rodada.")
        else:
            ana_f = ana_risco_tab.copy()
            if "cod_ibge" in ana_f.columns and "cod_ibge" in resumo.columns:
                ana_f = ana_f[ana_f["cod_ibge"].astype(str).isin(resumo["cod_ibge"].dropna().astype(str))]
            show_df(
                ana_f,
                [c for c in ["data", "cod_ibge", "municipio", "chuva_mm", "cota_cm", "vazao_m3s", "nivel_chuva", "fonte"] if c in ana_f.columns],
                height=260,
            )
    with tab_hi:
        if hidro_risco.empty:
            st.info("Sem hidro_risco_municipal (série ANA curta ou ausente). Ative ANA_FETCH_SERIES=true.")
        else:
            hi_f = hidro_risco.copy()
            if "cod_ibge" in hi_f.columns and "cod_ibge" in resumo.columns:
                hi_f = hi_f[hi_f["cod_ibge"].astype(str).isin(resumo["cod_ibge"].dropna().astype(str))]
            if "situacao_hidro" in hi_f.columns:
                sit = hi_f["situacao_hidro"].astype(str).str.lower()
                m1, m2, m3 = st.columns(3)
                m1.metric("Seca (rio baixo)", int(sit.eq("seca_baixa").sum()))
                m2.metric("Cheia / inundação", int(sit.eq("inundacao_alta").sum()))
                m3.metric(
                    "Com cota",
                    int(pd.to_numeric(hi_f["cota_cm"], errors="coerce").notna().sum())
                    if "cota_cm" in hi_f.columns
                    else 0,
                )
            show_df(
                safe_sort(hi_f, ["score_hidro_max"] if "score_hidro_max" in hi_f.columns else [], ascending=[False]),
                [
                    c
                    for c in [
                        "cod_ibge",
                        "municipio",
                        "situacao_hidro",
                        "risco_predominante",
                        "nivel_alerta_hidro",
                        "cota_cm",
                        "score_hidro_max",
                        "score_cheia_max",
                        "score_estiagem_max",
                        "motivo_resumo",
                        "data_mais_recente",
                    ]
                    if c in hi_f.columns
                ],
                height=260,
            )
            color_hi = (
                "situacao_hidro"
                if "situacao_hidro" in hi_f.columns
                else ("risco_predominante" if "risco_predominante" in hi_f.columns else None)
            )
            if color_hi:
                map_df, geojson, status = prepare_map_dataframe(hi_f)
                st.caption(status)
                fig = make_choropleth_or_points(
                    map_df,
                    geojson,
                    color_col=color_hi,
                    title="Hidro ANA — seca vs cheia",
                    categorical=True,
                    hover_cols=[c for c in ["cota_cm", "nivel_alerta_hidro", "motivo_resumo"] if c in map_df.columns],
                )
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)

    show_df(
        safe_sort(resumo, [c for c in ["indice_tensao_climatica", "risco_cumulativo_3d", "indice_saturacao_solo"] if c in resumo.columns], ascending=[False] * min(3, len([c for c in ["indice_tensao_climatica", "risco_cumulativo_3d", "indice_saturacao_solo"] if c in resumo.columns]))),
        [
            c for c in [
                "cod_ibge", "municipio", "regional_saude", "nivel", "score",
                "indice_tensao_climatica", "faixa_tensao_climatica",
                "tmax", "tmedia", "umidade_media", "utci_proxy", "risco_cumulativo_3d",
                "indice_saturacao_solo", "classe_saturacao_solo",
                "situacao_hidro", "nivel_alerta_hidro", "cota_cm",
                "onda_calor_p95_2d", "tendencia_7d", "orientacao_leiga", "motivo",
            ]
            if c in resumo.columns
        ],
    )
    ui_theme.glossary_expander([
        "tmax", "utci_proxy", "risco_cumulativo_3d", "indice_tensao_climatica",
        "indice_saturacao_solo", "indice_resiliencia", "indice_capacidade_cnes", "tendencia_7d",
    ])


# ---------------------------------------------------------------------
# Tab 4
# ---------------------------------------------------------------------
elif SECTION_KEY == "Assistência":
    ui_theme.section_title(
        "Assistência e índice de pressão",
        "IndicaSUS · SISREG · SINAN · SIM — cenário atual, tendência e previsão ~7 dias (semáforo G/A/V)",
    )
    ui_theme.callout(
        "Semáforo de pressão (verde / amarela / vermelha) resume a carga assistencial-epidemiológica. "
        "É distinto do nível operacional de 5 cores (Verde→Roxa). SISREG entra quando a tabela "
        "`ops_sisreg_municipio` estiver disponível; até lá o índice renormaliza os demais pilares.",
        "warn",
    )
    render_interpretacao(
        "assistencia",
        GUIDE_ASSISTENCIA,
        lambda: narrativa_assistencia(resumo, pressao_state),
    )

    # --- Índice de pressão: KPIs estaduais ---
    n_v = pressao_state.get("n_verde", 0)
    n_a = pressao_state.get("n_amarela", 0)
    n_r = pressao_state.get("n_vermelha", 0)
    n_up = pressao_state.get("n_subindo", 0)
    n_dn = pressao_state.get("n_descendo", 0)
    n_st = pressao_state.get("n_estavel", 0)
    idx_med = pressao_state.get("indice_media")
    sisreg_cov = pressao_state.get("sisreg_cobertura", 0)

    ui_theme.insight_cards(
        [
            (
                "Índice pressão méd.",
                safe_metric_value(idx_med, "", 1) if idx_med is not None else "—",
                "0–100 · IndicaSUS+SINAN+SIM(+SISREG)",
            ),
            ("🟢 Verde", n_v, "municípios"),
            ("🟡 Amarela", n_a, "municípios"),
            ("🔴 Vermelha", n_r, "municípios"),
        ]
    )
    ui_theme.insight_cards(
        [
            ("↑ Tendência alta", n_up, "previsão 7d piora"),
            ("→ Estável", n_st, "previsão 7d"),
            ("↓ Tendência queda", n_dn, "previsão 7d melhora"),
            ("SISREG no recorte", f"{sisreg_cov}/{len(resumo)}", "com fila/regulação"),
        ]
    )

    st.markdown("#### KPIs por pilar — atual × previsão 7d × tendência")
    if not pressao_df.empty and "cod_ibge" in pressao_df.columns:
        def _pillar_state(sem_col: str, tend_col: str, valor_col: str | None = None) -> str:
            if sem_col not in pressao_df.columns:
                return "—"
            # moda do semáforo no recorte (pior caso se empate: vermelha > amarela > verde)
            order = {"vermelha": 3, "amarela": 2, "verde": 1, "—": 0}
            s = pressao_df[sem_col].astype(str).str.lower()
            if s.replace("—", pd.NA).dropna().empty and (s == "—").all():
                return "⚪ Sem dados"
            # usa o pior município do recorte para o cartão-resumo do pilar
            worst = s.map(order).fillna(0).idxmax() if len(s) else None
            sem = str(pressao_df.loc[worst, sem_col]).lower() if worst is not None else "—"
            tend = (
                str(pressao_df.loc[worst, tend_col]).lower()
                if tend_col in pressao_df.columns and worst is not None
                else "—"
            )
            extra = ""
            if valor_col and valor_col in pressao_df.columns and worst is not None:
                try:
                    vv = pd.to_numeric(pressao_df.loc[worst, valor_col], errors="coerce")
                    if pd.notna(vv):
                        extra = f" · ref. {vv:.0f}" if abs(vv) >= 10 else f" · ref. {vv:.1f}"
                except Exception:
                    pass
            return f"{format_kpi_label(sem, tend)}{extra}"

        pcols = st.columns(4)
        with pcols[0]:
            st.markdown("**IndicaSUS** (ocupação)")
            st.markdown(_pillar_state("kpi_indicasus_semaforo", "kpi_indicasus_tendencia", "kpi_indicasus_valor"))
            med_o = pd.to_numeric(pressao_df.get("kpi_indicasus_valor"), errors="coerce").mean()
            st.caption(f"Ocupação méd.: {med_o:.1f}%" if pd.notna(med_o) else "Ocupação: sem dado")
        with pcols[1]:
            st.markdown("**SISREG** (regulação)")
            if sisreg_cov and sisreg_cov > 0:
                st.markdown(_pillar_state("kpi_sisreg_semaforo", "kpi_sisreg_tendencia", "kpi_sisreg_fila_h"))
            else:
                st.markdown("⚪ Pendente — integrar `ops_sisreg_municipio`")
            st.caption("Fila / solicitações abertas")
        with pcols[2]:
            st.markdown("**SINAN** (agravos clima)")
            st.markdown(_pillar_state("kpi_sinan_semaforo", "kpi_sinan_tendencia", "kpi_sinan_casos_7d"))
            med_c = pd.to_numeric(pressao_df.get("kpi_sinan_casos_7d"), errors="coerce").mean()
            st.caption(f"Arbovírus 7d méd.: {med_c:.0f}" if pd.notna(med_c) else "Arbovírus/SRAG: parcial")
        with pcols[3]:
            st.markdown("**SIM** (óbitos calor)")
            st.markdown(_pillar_state("kpi_sim_semaforo", "kpi_sim_tendencia", "kpi_sim_obitos"))
            med_ob = pd.to_numeric(pressao_df.get("kpi_sim_obitos"), errors="coerce").sum()
            st.caption(f"Óbitos no recorte: {med_ob:.0f}" if pd.notna(med_ob) else "SIM: sem dado")

        st.markdown("#### Mapa — índice de pressão (0–100)")
        if "indice_pressao_saude" in map_df.columns and pd.to_numeric(map_df["indice_pressao_saude"], errors="coerce").notna().any():
            choropleth_or_points(
                map_df,
                geojson_mun,
                "indice_pressao_saude",
                "Índice de pressão em saúde",
                hover_cols=[
                    "regional_saude",
                    "semaforo_pressao",
                    "tendencia_pressao_7d",
                    "pred_indice_pressao_7d",
                    "ocupacao_leitos_pct",
                    "casos_arbovirus_7d",
                ],
            )
        else:
            st.info("Índice de pressão ainda sem valores mapeáveis no recorte.")

        st.markdown("#### Tabela municipal — pressão, semáforo, previsão e tendência")
        show_df(
            safe_sort(
                pressao_df if not pressao_df.empty else resumo,
                ["indice_pressao_saude", "pred_indice_pressao_7d"],
                ascending=[False, False],
            ),
            [
                "cod_ibge",
                "municipio",
                "regional_saude",
                "semaforo_pressao",
                "indice_pressao_saude",
                "pred_indice_pressao_7d",
                "semaforo_pressao_pred_7d",
                "tendencia_pressao_7d",
                "kpi_indicasus_valor",
                "kpi_indicasus_semaforo",
                "kpi_indicasus_tendencia",
                "kpi_sisreg_semaforo",
                "kpi_sisreg_tendencia",
                "kpi_sinan_casos_7d",
                "kpi_sinan_semaforo",
                "kpi_sinan_tendencia",
                "kpi_sim_obitos",
                "kpi_sim_semaforo",
                "kpi_sim_tendencia",
                "pilares_disponiveis",
            ],
            height=420,
        )
    else:
        st.warning("Não foi possível calcular o índice de pressão neste recorte.")

    with st.expander("Catálogo de agravos com correlação climática (bases SINAN/SIM/IndicaSUS/SISREG)"):
        cat = catalogo_agravos()
        if not cat.empty:
            show_df(cat, ["id", "nome", "base", "evidencias", "indicadores", "status"], height=280)
        else:
            st.caption("Catálogo em `config/indice_pressao_semaforo.yaml`.")

    st.divider()
    ui_theme.section_title("Detalhe assistencial", "Leitos IndicaSUS + proxy clima–saúde quando a ocupação falha")

    tem_ocup = "ocupacao_leitos_pct" in resumo.columns and pd.to_numeric(resumo["ocupacao_leitos_pct"], errors="coerce").notna().any()
    tem_press = "pressao_calor_pct" in resumo.columns and pd.to_numeric(resumo["pressao_calor_pct"], errors="coerce").notna().any()
    total_recorte = int(len(resumo))
    ocup_validos = int(pd.to_numeric(resumo.get("ocupacao_leitos_pct"), errors="coerce").notna().sum()) if "ocupacao_leitos_pct" in resumo.columns else 0
    fonte_ocup = resumo.get("fonte_ocupacao", pd.Series(dtype=str)).fillna("").astype(str) if "fonte_ocupacao" in resumo.columns else pd.Series(dtype=str)
    real_mask = fonte_ocup.str.contains("INDICASUS_TEMPO_REAL", case=False, na=False) & ~fonte_ocup.str.contains("FALLBACK|CACHE", case=False, na=False)
    fallback_mask = fonte_ocup.str.contains("FALLBACK|CACHE", case=False, na=False)
    ocup_real = int(real_mask.sum()) if not fonte_ocup.empty else 0
    ocup_fallback = int(fallback_mask.sum()) if not fonte_ocup.empty else 0
    cov_pct = (100.0 * ocup_real / total_recorte) if total_recorte else 0.0
    fonte_press = ""
    if "fonte_pressao" in resumo.columns:
        fonte_press = str(resumo["fonte_pressao"].dropna().astype(str).mode().iloc[0]) if resumo["fonte_pressao"].notna().any() else ""

    if not tem_ocup:
        st.warning("Ocupação de leitos indisponível no recorte filtrado.")
    elif ocup_real < total_recorte:
        st.warning(
            f"Cobertura municipal de ocupação real: {ocup_real}/{total_recorte} ({cov_pct:.1f}%). "
            f"Demais municípios usam fallback/proxy ({ocup_fallback})."
        )
    else:
        st.success(f"Cobertura municipal de ocupação real: {ocup_real}/{total_recorte} municípios.")
    if tem_press and "PROXY" in fonte_press.upper():
        st.info(
            f"Pressão assistencial = **proxy clima+saúde** (`{fonte_press}`). "
            "Não substitui censo hospitalar / IndicaSUS."
        )

    ui_theme.insight_cards(
        [
            ("Pressão méd.", safe_metric_value(pd.to_numeric(resumo.get("pressao_calor_pct"), errors="coerce").mean() if tem_press else None, "%", 1), "proxy ou real"),
            ("Ocupação méd.", safe_metric_value(pd.to_numeric(resumo.get("ocupacao_leitos_pct"), errors="coerce").mean() if tem_ocup else None, "%", 1), "IndicaSUS"),
            ("Carga saúde méd.", safe_metric_value(pd.to_numeric(resumo.get("indice_carga_saude"), errors="coerce").mean() if "indice_carga_saude" in resumo.columns else None, "", 0), "índice 0–100"),
            ("Cobertura ocupação real", f"{ocup_real}/{total_recorte}", "municípios no recorte"),
        ]
    )
    if "regional_saude" in resumo.columns and "fonte_ocupacao" in resumo.columns:
        reg_cov = resumo.copy()
        reg_cov["ocup_real"] = real_mask.astype(int)
        reg_cov["ocup_fallback"] = fallback_mask.astype(int)
        reg_cov = (
            reg_cov.groupby("regional_saude", as_index=False)
            .agg(
                municipios=("cod_ibge", "nunique"),
                ocup_real=("ocup_real", "sum"),
                ocup_fallback=("ocup_fallback", "sum"),
            )
        )
        reg_cov["cobertura_real_pct"] = (
            100.0 * reg_cov["ocup_real"] / reg_cov["municipios"].replace({0: pd.NA})
        ).round(1)
        st.markdown("#### Cobertura de ocupação por regional")
        show_df(
            reg_cov.sort_values(["cobertura_real_pct", "ocup_real"], ascending=[False, False]),
            ["regional_saude", "municipios", "ocup_real", "ocup_fallback", "cobertura_real_pct"],
            height=260,
        )

    col_a, col_b = st.columns(2)
    with col_a:
        make_bar(resumo, "municipio", "pressao_calor_pct", "Pressão assistencial proxy - Top")
    with col_b:
        if tem_ocup:
            make_bar(resumo, "municipio", "ocupacao_leitos_pct", "Ocupação de leitos IndicaSUS - Top")
        else:
            y = "indice_carga_saude" if "indice_carga_saude" in resumo.columns else "indice_vigilancia_integrada"
            make_bar(resumo, "municipio", y, "Carga em saúde (substituto visual)")

    st.markdown("#### Mapa da ocupação de leitos")
    if tem_ocup:
        choropleth_or_points(
            map_df,
            geojson_mun,
            "ocupacao_leitos_pct",
            "Ocupação de leitos IndicaSUS",
            hover_cols=["regional_saude", "nivel", "score", "leitos_total", "leitos_ocupados", "pressao_calor_pct"],
        )
    else:
        st.info("Sem coluna/valores de ocupação para mapear.")

    st.markdown("#### Mapa da pressão assistencial")
    if tem_press:
        choropleth_or_points(
            map_df,
            geojson_mun,
            "pressao_calor_pct",
            "Pressão assistencial proxy",
            hover_cols=["regional_saude", "nivel", "score", "ocupacao_leitos_pct", "risco_cumulativo_3d", "utci_proxy", "indice_carga_saude"],
        )
    else:
        st.info("Sem pressão assistencial calculada para mapear.")
    ui_theme.glossary_expander(["pressao_calor_pct", "ocupacao_leitos_pct", "indice_carga_saude"])

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
        st.info(
            "Ainda não foi consolidada série estadual de SINAN/SIM/GAL/SIVEP para agravos sensíveis ao calor. "
            "Rode `atualizar_monitoramento_saude_calor.py` (ou o enriquecimento operacional)."
        )

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
        st.warning(
            "Base consolidada `saude_calor_municipio` ainda vazia. "
            "Rode `atualizar_monitoramento_saude_calor.py`. "
            "O app usa SINAN, SIM, GAL/LACEN e SIVEP quando as tabelas estiverem na base operacional."
        )


    st.markdown("#### Tabela municipal assistencial")
    show_df(
        safe_sort(resumo, ["ocupacao_leitos_pct", "pressao_calor_pct", "score"], ascending=[False, False, False]),
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
elif SECTION_KEY == "Qualidade do ar":
    ui_theme.section_title("Qualidade do ar", "PM2,5, IQA e focos de queimadas")
    if not _PAINEL_PUBLICO:
        ui_theme.callout(
            "PM2,5 alto preocupa asma, idosos e crianças — comum com queimadas na seca. "
            "Focos INPE mostram fogo mesmo quando PM2,5 municipal ainda não chegou.",
            "warn",
        )
        render_interpretacao(
            "qualidade_ar",
            GUIDE_AR,
            lambda: narrativa_ar(resumo, aq),
        )

    pols = ["pm25_ugm3", "pm10_ugm3", "o3_ugm3", "no2_ugm3", "co_mgm3", "so2_ugm3", "iq_ar_score"]
    pm_nn = int(pd.to_numeric(resumo.get("pm25_ugm3"), errors="coerce").notna().sum()) if "pm25_ugm3" in resumo.columns else 0
    focos7 = pd.to_numeric(resumo.get("focos_queimadas_7d"), errors="coerce") if "focos_queimadas_7d" in resumo.columns else pd.Series(dtype=float)
    focos_mun = int((focos7.fillna(0) > 0).sum()) if len(focos7) else 0
    if pm_nn == 0 and aq.empty:
        if _PAINEL_PUBLICO:
            ui_theme.callout("Sem dados de qualidade do ar neste recorte.", "warn")
        else:
            _copernicus = str(os.getenv("USE_COPERNICUS", "")).strip().lower() in {"1", "true", "yes", "sim"}
            if not _copernicus:
                ui_theme.callout(
                    "PM2,5/IQA vazios: a rotina usa Open-Meteo (USE_OPENMETEO_AQ=true). "
                    "Opcional: CAMS com `USE_COPERNICUS=true` e chave no `.env`.",
                    "warn",
                )
            else:
                ui_theme.callout(
                    "USE_COPERNICUS está ligado, mas `qualidade_ar_municipal` veio vazia neste ambiente. "
                    "Rode o enrichment/orquestrador e atualize `sis_cloud_seed.db` se estiver no Cloud.",
                    "warn",
                )
    ui_theme.insight_cards(
        [
            ("Mun. com PM2,5", pm_nn, "no recorte filtrado"),
            ("PM2,5 máx.", safe_metric_value(pd.to_numeric(resumo.get("pm25_ugm3"), errors="coerce").max() if "pm25_ugm3" in resumo.columns else None, "", 1), "µg/m³"),
            ("Mun. com focos 7d", focos_mun, "INPE BDQueimadas"),
            (
                "Focos 7d (máx.)",
                safe_metric_value(focos7.max() if len(focos7) else None, "", 0),
                "por município",
            ),
        ]
    )

    st.markdown("#### Queimadas INPE — ranking municipal (7 dias)")
    if "focos_queimadas_7d" in resumo.columns and focos_mun > 0:
        qrank = resumo.copy()
        qrank["focos_queimadas_7d"] = pd.to_numeric(qrank["focos_queimadas_7d"], errors="coerce").fillna(0)
        qrank = qrank[qrank["focos_queimadas_7d"] > 0].sort_values("focos_queimadas_7d", ascending=False)
        cols_q = [
            c
            for c in (
                "municipio",
                "regional_saude",
                "focos_queimadas_24h",
                "focos_queimadas_7d",
                "nivel_queimadas",
                "pm25_ugm3",
                "risco_ar_queimadas",
                "nivel",
            )
            if c in qrank.columns
        ]
        show_df(qrank[cols_q].head(40), height=320)
        map_q = first_col(map_df, ["focos_queimadas_7d", "risco_ar_queimadas", "pm25_ugm3"])
        if map_q:
            choropleth_or_points(
                map_df,
                geojson_mun,
                map_q,
                f"Queimadas / ar — {map_q}",
                hover_cols=[c for c in ["nivel_queimadas", "focos_queimadas_24h", "pm25_ugm3"] if c in map_df.columns],
            )
    else:
        st.info(
            "Sem focos de queimadas neste recorte."
            if _PAINEL_PUBLICO
            else (
                "Sem focos INPE no recorte. Confira `USE_INPE_QUEIMADAS=true` e rode "
                "`regenerar_sistema_completo.py` ou o enrichment operacional."
            )
        )

    st.markdown("#### Série histórica estadual — média dos municípios")
    estado = aq_estado_serie.copy() if not aq_estado_serie.empty else pd.DataFrame()
    if estado.empty and not aq.empty:
        estado = aq.copy()
        _data_col = next((c for c in ["data", "data_referencia", "time"] if c in estado.columns), None)
        if _data_col:
            estado["data"] = pd.to_datetime(estado[_data_col], errors="coerce")
            for c in pols:
                if c in estado.columns:
                    estado[c] = pd.to_numeric(estado[c], errors="coerce")
            present = [c for c in pols if c in estado.columns]
            estado = estado.dropna(subset=["data"]).groupby("data", as_index=False)[present].mean(numeric_only=True) if present else pd.DataFrame()

    if not estado.empty:
        if "data" not in estado.columns:
            _data_col = next((c for c in ["data_referencia", "time"] if c in estado.columns), None)
            if _data_col:
                estado["data"] = pd.to_datetime(estado[_data_col], errors="coerce")
        if "data" in estado.columns:
            estado["data"] = pd.to_datetime(estado["data"], errors="coerce")
            present = [c for c in pols if c in estado.columns]
            long_estado = estado.melt(id_vars=["data"], value_vars=present, var_name="poluente", value_name="valor").dropna(subset=["data", "valor"])
            if long_estado.empty:
                st.info("A série estadual existe, mas sem valores numéricos válidos para PM2.5/IQA.")
            else:
                fig = px.line(long_estado, x="data", y="valor", color="poluente", title="Média estadual diária da qualidade do ar")
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(
                "Série estadual de qualidade do ar ainda não disponível."
                if _PAINEL_PUBLICO
                else (
                    "Série estadual de qualidade do ar ainda não criada. "
                    "Rode `regenerar_sistema_completo.py` (gera `qualidade_ar_estado_serie_v6` no enrichment)."
                )
            )
    else:
        st.info(
            "Série estadual de qualidade do ar ainda não disponível."
            if _PAINEL_PUBLICO
            else (
                "Série estadual de qualidade do ar ainda não criada. "
                "Rode `regenerar_sistema_completo.py` (gera `qualidade_ar_estado_serie_v6` no enrichment)."
            )
        )

    st.markdown("#### Série municipal filtrável")
    aq_f = aq.copy()
    if not aq_f.empty and "cod_ibge" in aq_f.columns and "cod_ibge" in resumo.columns:
        aq_f["cod_ibge"] = normalize_cod_ibge(aq_f["cod_ibge"])
        aq_f = aq_f[aq_f["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
    elif not aq_f.empty and municipios_sel and "municipio" in aq_f.columns:
        aq_f = aq_f[aq_f["municipio"].isin(municipios_sel)]

    if aq_f.empty:
        st.info(
            "Sem série municipal de qualidade do ar neste recorte."
            if _PAINEL_PUBLICO
            else (
                "Tabela `qualidade_ar_municipal` indisponível para o recorte. "
                "Confira `USE_COPERNICUS` / CSV e o seed Cloud após o orquestrador."
            )
        )
    else:
        aq_plot = aq_f.copy()
        _data_col = next((c for c in ["data", "data_referencia", "time"] if c in aq_plot.columns), None)
        if _data_col:
            aq_plot["data"] = pd.to_datetime(aq_plot[_data_col], errors="coerce")
        for c in pols:
            if c in aq_plot.columns:
                aq_plot[c] = pd.to_numeric(aq_plot[c], errors="coerce")
        if "municipio" in aq_plot.columns:
            _muns = sorted(aq_plot["municipio"].dropna().astype(str).unique().tolist())
            _padrao = [m for m in (municipios_sel or []) if m in _muns] or _muns[: min(6, len(_muns))]
            if len(_muns) > 6:
                _escolhidos = st.multiselect(
                    "Municípios na série",
                    _muns,
                    default=_padrao[:6],
                    key="aq_serie_munis",
                )
                if _escolhidos:
                    aq_plot = aq_plot[aq_plot["municipio"].astype(str).isin(_escolhidos)]
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
        elif _data_col is None:
            st.info("Há medição municipal, mas sem coluna de data para montar a série.")

        map_col = first_col(map_df, ["iq_ar_score", "pm25_ugm3", "pm10_ugm3", "o3_ugm3"])
        if map_col:
            choropleth_or_points(map_df, geojson_mun, map_col, f"Qualidade do ar - {map_col}", hover_cols=["qualidade_ar_nivel", "poluente_dominante", "indice_carga_saude"])
        show_df(aq_plot, height=450)
    if not _PAINEL_PUBLICO:
        ui_theme.glossary_expander(
            ["pm25_ugm3", "focos_queimadas_7d", "focos_queimadas_24h", "nivel_queimadas", "indice_carga_saude"]
        )

# ---------------------------------------------------------------------
# Tab 6
# ---------------------------------------------------------------------
elif SECTION_KEY == "Operacional":
    st.subheader("Operacional: estoque, infraestrutura e resiliência")
    render_interpretacao(
        "operacional",
        GUIDE_OPERACIONAL,
        lambda: narrativa_operacional(resumo, ops_cnes if not ops_cnes.empty else ops_proxy),
    )

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
elif SECTION_KEY == "Geografia":
    st.subheader("Geografia, base territorial e shapefile")
    if not _PAINEL_PUBLICO:
        render_interpretacao(
            "geografia",
            GUIDE_GEO,
            lambda: narrativa_geo(resumo, str(shapefile_status or "")),
        )

    st.info(shapefile_status)

    st.markdown("#### Rede CNES e territórios vulneráveis")
    st.caption(
        "Estabelecimentos CNES e aldeias/quilombos/assentamentos. "
        "km operacional = trajeto viário (OSRM); centroide municipal não entra no cálculo."
    )
    from sisclima.ui.mapa_gestao_territorio import render_mapa_gestao_territorio

    render_mapa_gestao_territorio(resumo, allow_fetch=not _PAINEL_PUBLICO)

    st.markdown("#### Mapa de vulnerabilidade territorial ao calor")
    if "indice_vulnerabilidade_calor" in map_df.columns:
        choropleth_or_points(
            map_df,
            geojson_mun,
            "indice_vulnerabilidade_calor",
            "Vulnerabilidade territorial ao calor (IBGE)",
            hover_cols=[
                c for c in [
                    "municipio", "regional_saude", "populacao", "idosos_pct",
                    "criancas_0_4_pct", "rural_pct", "pop_vulneravel_exposta",
                ]
                if c in map_df.columns
            ],
        )
    else:
        st.warning("Campo indice_vulnerabilidade_calor não encontrado no resumo municipal.")

    if "indice_exposicao_vulneravel" in map_df.columns:
        st.markdown("#### Mapa exposição climática × vulnerabilidade demográfica")
        choropleth_or_points(
            map_df,
            geojson_mun,
            "indice_exposicao_vulneravel",
            "Exposição × vulnerabilidade",
            hover_cols=[
                c for c in [
                    "municipio", "risco_calor_vulneravel", "pop_vulneravel_exposta",
                    "idosos_pct", "indice_tensao_climatica",
                ]
                if c in map_df.columns
            ],
        )

    st.markdown("#### Tabela geográfica deduplicada")
    geo_cols = [
        c for c in [
            "cod_ibge", "municipio", "regional_saude", "macroregiao_saude",
            "populacao", "populacao_2025", "lat", "lon",
            "indice_vulnerabilidade_calor", "idosos_pct", "criancas_0_4_pct",
            "rural_pct", "densidade", "indice_exposicao_vulneravel", "pop_vulneravel_exposta",
        ]
        if c in map_df.columns
    ]
    geo_table = map_df.drop_duplicates("cod_ibge") if "cod_ibge" in map_df.columns else map_df
    show_df(geo_table.sort_values("municipio") if "municipio" in geo_table.columns else geo_table, geo_cols, height=520)


# ---------------------------------------------------------------------
# Tab 8
# ---------------------------------------------------------------------
elif SECTION_KEY == "Cálculos":
    ui_theme.section_title(
        "Cálculos e indicadores",
        "Como os números deste painel são compostos" if _PAINEL_PUBLICO else "Transparência metodológica para a sala de situação",
    )
    if not _PAINEL_PUBLICO:
        ui_theme.callout(
            "Os índices compostos (tensão, carga, vigilância) usam pesos em config/settings.yaml → indicadores_painel. Ajuste com o CIEVS sem mudar código.",
            "tip",
        )
        render_interpretacao(
            "calculos",
            GUIDE_CALC,
            lambda: narrativa_calculos(),
        )

    from sisclima.engines.panel_indicators import get_indicator_config

    cfg_ind = get_indicator_config()
    if _PAINEL_PUBLICO:
        st.markdown("### Indicadores compostos (como se combinam)")
        _p1, _p2, _p3 = st.columns(3)
        with _p1:
            st.markdown("**Tensão climática**")
            st.markdown(
                f"- Risco 3 dias: {cfg_ind['tensao_climatica'].get('risco_cumulativo', 0):.0%}\n"
                f"- Sensação térmica (UTCI): {cfg_ind['tensao_climatica'].get('utci', 0):.0%}\n"
                f"- Temperatura máxima: {cfg_ind['tensao_climatica'].get('tmax', 0):.0%}\n"
                f"- Estiagem: {cfg_ind['tensao_climatica'].get('umidade_seca', 0):.0%}"
            )
        with _p2:
            st.markdown("**Carga em saúde**")
            st.markdown(
                f"- SRAG: {cfg_ind['carga_saude'].get('srag', 0):.0%}\n"
                f"- Arboviroses: {cfg_ind['carga_saude'].get('arbovirus', 0):.0%}\n"
                f"- PM2,5: {cfg_ind['carga_saude'].get('pm25', 0):.0%}\n"
                f"- Queimadas: {cfg_ind['carga_saude'].get('queimadas', 0):.0%}\n"
                f"- Pressão assistencial: {cfg_ind['carga_saude'].get('pressao', 0):.0%}"
            )
        with _p3:
            st.markdown("**Vigilância integrada**")
            st.markdown(
                f"- Tensão climática: {cfg_ind['vigilancia_integrada'].get('tensao', 0):.0%}\n"
                f"- Carga em saúde: {cfg_ind['vigilancia_integrada'].get('carga', 0):.0%}\n"
                f"- Pressão: {cfg_ind['vigilancia_integrada'].get('pressao', 0):.0%}\n"
                f"- Nível operacional: {cfg_ind['vigilancia_integrada'].get('nivel_operacional', 0):.0%}"
            )
        _fx = cfg_ind.get("faixas") or {}
        st.caption(
            f"Faixas 0–100: baixa até {_fx.get('baixa_max', 30)} · "
            f"moderada até {_fx.get('moderada_max', 60)} · "
            f"alta até {_fx.get('alta_max', 80)} · acima disso, muito alta."
        )
    else:
        st.markdown("### Indicadores compostos do painel (pesos atuais)")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Tensão climática**")
            st.json(cfg_ind["tensao_climatica"])
        with c2:
            st.markdown("**Carga em saúde**")
            st.json(cfg_ind["carga_saude"])
        with c3:
            st.markdown("**Vigilância integrada**")
            st.json(cfg_ind["vigilancia_integrada"])
        st.markdown("**Faixas (0–100)**")
        st.json(cfg_ind["faixas"])
        if cfg_ind.get("notas_calibracao"):
            st.info(cfg_ind["notas_calibracao"])
    if not _PAINEL_PUBLICO:
        st.caption("Override via .env: PANEL_W_TENSAO_RISCO, PANEL_W_CARGA_SRAG, PANEL_W_VIG_TENSAO, etc.")

    if _PAINEL_PUBLICO:
        st.markdown(
            """
### 1. Nível operacional municipal

Síntese colorida (Verde → Roxa) do recorte. Quanto mais alto o nível, maior a prioridade de atenção.

| Nível | Leitura |
|---|---|
| Verde | situação sob controle |
| Amarela | atenção |
| Laranja | alerta |
| Vermelha | resposta intensificada |
| Roxa | situação excepcional |

### 2. Risco cumulativo de calor em 3 dias

O `risco_cumulativo_3d` resume o calor que se acumula em três dias — um dia quente é diferente de três seguidos.

### 3. UTCI proxy

O `utci_proxy` estima como o corpo sente o calor (temperatura + umidade + vento), não só o termômetro.

### 4. Tensão climática, carga em saúde e vigilância integrada

Notas 0–100 publicadas nos cards da Visão: calor acumulado, sinais de saúde e a combinação para priorizar o recorte.

### 5. Prioridade global e tendência 7 dias

A prioridade global (0–100) ordena municípios. A tendência ~7 dias compara o nível atual com a predição da semana seguinte — não é cenário sazonal.

### 6. Qualidade do ar e vulnerabilidade

PM2,5 e IQA descrevem fumaça/poluição. A vulnerabilidade ao calor junta idosos, crianças e exposição territorial. Populações vulneráveis no mapa de Território usam aldeias, quilombos e assentamentos com coordenada.

### 7. Qualidade do ar (aba dedicada)

A aba **Qualidade do ar** publica PM2,5, IQA, série diária e focos de queimadas (24 h e 7 dias). Focos mostram fogo ativo mesmo quando o PM2,5 municipal ainda não chegou. Município sem medição não significa ar limpo.

### 8. Arboviroses

Casos de dengue, zika e chikungunya nos últimos 7 dias, incidência por 100 mil e o mapa municipal. A janela de 7 dias mostra a pressão recente — não projeta a temporada inteira.

### 9. Cemaden / ANA

Alertas oficiais de desastre (Cemaden) e nível de rio/chuva (ANA). A cobertura de estações é desigual no território: ausência de dado não é risco zero.

### 10. Sazonalidade e Odds Ratio

O índice sazonal compara cada mês com a média histórica (acima de 1 = mês mais crítico). O heatmap mostra o padrão semana epidemiológica × ano. O OR ecológico compara municípios mais expostos vs menos expostos — ajuda a priorizar hipóteses, não prova causalidade individual.
            """
        )
    else:
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

### 8. Índices compostos (novos)

- `indice_tensao_climatica` (0–100): risco 3d + UTCI + Tmax + estiagem relativa  
- `indice_carga_saude` (0–100): SRAG + arbovírus + PM2,5 + pressão  
- `indice_vigilancia_integrada` (0–100): combinação dos anteriores para priorização  
- `tendencia_7d`: compara nível atual × predição 7 dias  
Persistidos em `resumo_municipal_atual` e `indicadores_painel_municipal`.

### 9. Índice de pressão (semáforo G/A/V)

`indice_pressao_saude` (0–100) combina **IndicaSUS** (ocupação), **SISREG** (fila/regulação, quando `ops_sisreg_municipio` existir), **SINAN** (arbovírus/SRAG/agravos calor) e **SIM** (óbitos sensíveis ao calor).  
Cada pilar traz cenário atual, `*_pred_7d` e tendência (↑ alta / → estável / ↓ queda).  
Cores: **verde** (baixa), **amarela** (atenção), **vermelha** (alta) — distinto do nível operacional de 5 cores.  
Catálogo e limiares: `config/indice_pressao_semaforo.yaml`.

### 10. Pendências de integração plena

- estoque e autonomia de insumos por município;
- infraestrutura crítica das unidades;
- **SISREG** (fila, tempo de espera, solicitações) → popular `ops_sisreg_municipio`;
- credenciais IndicaSUS válidas para ocupação real em todos os municípios;
- boletim operacional automatizado.
        """
    )



# ---------------------------------------------------------------------
# Tab 9 - Inteligência, predição e análise estatística
# ---------------------------------------------------------------------
elif SECTION_KEY == "Inteligência":
    ui_theme.section_title("Inteligência operacional", "Predição ~7 dias + alerta inteligente + análise clima–saúde")
    ui_theme.callout(
        "A predição numérica cobre cerca de 7 dias — útil para a semana seguinte, não para ‘projetar setembro’. Associações estatísticas são exploratórias.",
        "warn",
    )
    render_interpretacao(
        "inteligencia",
        GUIDE_INTEL,
        lambda: narrativa_inteligencia(resumo, pred_v6),
    )

    st.markdown(
        """
        Esta aba combina três camadas: **alerta inteligente municipal**, **predição operacional de 7 dias**
        e **análise estatística ecológica clima-saúde**. As associações estatísticas são exploratórias e devem
        ser interpretadas como apoio à priorização, não como inferência causal individual.
        """
    )

    # ---------------------------------------------------------------
    # Indicadores inteligentes AdaptaSUS (derivados)
    # ---------------------------------------------------------------
    st.markdown("### Indicadores inteligentes (AdaptaSUS)")
    ui_theme.callout(
        "Derivados com dados já disponíveis no resumo: calor vulnerável, ar/queimadas, vetorial climático e pressão da rede. "
        "Detalhe completo na aba AdaptaSUS / Guia MS.",
        "tip",
    )
    smart_cols = [
        c for c in [
            "indice_adaptacao_climatica", "risco_calor_vulneravel", "risco_ar_queimadas",
            "risco_vetorial_climatico", "pressao_rede_climatica", "risco_precipitacao",
            "indice_exposicao_vulneravel", "pop_vulneravel_exposta",
        ]
        if c in resumo.columns
    ]
    if smart_cols:
        pop_exp = pd.to_numeric(resumo.get("pop_vulneravel_exposta"), errors="coerce") if "pop_vulneravel_exposta" in resumo.columns else pd.Series(dtype=float)
        ui_theme.insight_cards(
            [
                (
                    "Adaptação méd.",
                    safe_metric_value(pd.to_numeric(resumo.get("indice_adaptacao_climatica"), errors="coerce").mean(), "", 0),
                    "0–100",
                ),
                (
                    "Calor vulnerável máx.",
                    safe_metric_value(pd.to_numeric(resumo.get("risco_calor_vulneravel"), errors="coerce").max(), "", 0),
                    "índice",
                ),
                (
                    "Pop. vulnerável exposta",
                    safe_metric_value(pop_exp.sum() if pop_exp.notna().any() else None, "", 0),
                    "idosos+crianças sob calor/fumaça",
                ),
                (
                    "Exposição×vuln. máx.",
                    safe_metric_value(pd.to_numeric(resumo.get("indice_exposicao_vulneravel"), errors="coerce").max() if "indice_exposicao_vulneravel" in resumo.columns else None, "", 0),
                    "0–100",
                ),
            ]
        )
        sc1, sc2 = st.columns(2)
        with sc1:
            y = "risco_calor_vulneravel" if "risco_calor_vulneravel" in resumo.columns else smart_cols[0]
            make_bar(resumo, "municipio", y, "Top calor × vulnerabilidade")
        with sc2:
            y2 = (
                "indice_exposicao_vulneravel"
                if "indice_exposicao_vulneravel" in resumo.columns
                else ("pressao_rede_climatica" if "pressao_rede_climatica" in resumo.columns else smart_cols[-1])
            )
            make_bar(resumo, "municipio", y2, "Top exposição × vulnerabilidade")
        if "risco_adaptasus_dominante_nome" in resumo.columns:
            show_df(
                safe_sort(resumo, ["indice_adaptacao_climatica"], ascending=[False]),
                [
                    c for c in [
                        "cod_ibge", "municipio", "regional_saude", "nivel",
                        "indice_adaptacao_climatica", "risco_adaptasus_dominante_nome",
                        "orientacao_adaptasus", "risco_calor_vulneravel",
                        "indice_exposicao_vulneravel", "pop_vulneravel_exposta", "idosos_pct",
                        "risco_ar_queimadas", "risco_vetorial_climatico", "pressao_rede_climatica",
                    ]
                    if c in resumo.columns
                ],
                height=320,
            )
        ui_theme.glossary_expander(
            [
                "indice_adaptacao_climatica", "risco_calor_vulneravel",
                "pop_vulneravel_exposta", "indice_exposicao_vulneravel",
                "risco_ar_queimadas", "risco_vetorial_climatico", "pressao_rede_climatica",
            ]
        )
    else:
        st.info("Indicadores AdaptaSUS ainda não calculados. Rode completar_sistema_operacional.py.")

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
            fig = px.bar(
                dist_pred,
                x="nível",
                y="municípios",
                color="nível",
                color_discrete_map={
                    "verde": LEVEL_COLOR_MAP["verde"],
                    "amarela": LEVEL_COLOR_MAP["amarela"],
                    "laranja": LEVEL_COLOR_MAP["laranja"],
                    "vermelha": LEVEL_COLOR_MAP["vermelha"],
                    "roxa": LEVEL_COLOR_MAP["roxa"],
                },
                title="Distribuição da predição 7 dias",
            )
            fig.update_layout(showlegend=False)
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
                "p_laranja_plus", "p_vermelha_plus", "ml_nivel_sugerido", "ml_confianca",
                "ocupacao_leitos_pct", "pressao_calor_pct", "fonte_predicao",
            ],
            height=420,
        )

    st.markdown("#### Skill da predição 7d + ML auxiliar")
    ui_theme.callout(
        "O nível SES (`nivel_predicao_7d`) continua pela regra. "
        "Skill mede acerto histórico; ML só sugere probabilidade ao lado.",
        "info",
    )
    if pred_skill_resumo is not None and not pred_skill_resumo.empty:
        sk = pred_skill_resumo.copy()
        for _, row in sk.iterrows():
            metodo = str(row.get("metodo", "—"))
            n = int(row.get("n_pares") or 0)
            hit = row.get("hit_rate_exato")
            hit1 = row.get("hit_rate_tol1")
            mae_t = row.get("mae_tmax")
            mae_u = row.get("mae_utci")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric(f"{metodo} · pares", n)
            c2.metric("Acerto exato", f"{100 * float(hit):.0f}%" if pd.notna(hit) else "—")
            c3.metric("Acerto ±1 nível", f"{100 * float(hit1):.0f}%" if pd.notna(hit1) else "—")
            c4.metric(
                "MAE Tmáx / UTCI",
                f"{float(mae_t):.1f} / {float(mae_u):.1f}" if pd.notna(mae_t) and pd.notna(mae_u) else "—",
            )
        show_df(sk, height=180)
    else:
        st.info(
            "Skill ainda sem pares suficientes. Rode o enrichment (`regenerar_sistema_completo.py --skip-pipeline`) "
            "com `met_biometeo` cobrindo ≥14 dias; emissões passam a ser arquivadas a cada rodada."
        )

    ml_view = pred_v6.copy() if not pred_v6.empty else pd.DataFrame()
    if (pred_ml_aux is not None) and (not pred_ml_aux.empty) and (not ml_view.empty) and "cod_ibge" in ml_view.columns:
        aux = pred_ml_aux.copy()
        aux["cod_ibge"] = normalize_cod_ibge(aux["cod_ibge"])
        drop_overlap = [c for c in aux.columns if c != "cod_ibge" and c in ml_view.columns]
        if drop_overlap:
            ml_view = ml_view.drop(columns=drop_overlap, errors="ignore")
        ml_view = ml_view.merge(aux, on="cod_ibge", how="left")
    if not ml_view.empty and any(c.startswith("p_") or c.startswith("ml_") for c in ml_view.columns):
        metodo_ml = (
            str(ml_view["ml_metodo"].dropna().astype(str).iloc[0])
            if "ml_metodo" in ml_view.columns and ml_view["ml_metodo"].notna().any()
            else "—"
        )
        st.caption(f"Método ML auxiliar: **{metodo_ml}** (não altera boletim SES).")
        cols_ml = [
            c
            for c in (
                "municipio",
                "regional_saude",
                "nivel_predicao_7d",
                "ml_nivel_sugerido",
                "ml_confianca",
                "p_laranja_plus",
                "p_vermelha_plus",
                "p_verde",
                "p_amarela",
                "p_laranja",
                "p_vermelha",
                "p_roxa",
            )
            if c in ml_view.columns
        ]
        show_df(
            ml_view.sort_values("p_laranja_plus", ascending=False) if "p_laranja_plus" in ml_view.columns else ml_view,
            cols_ml,
            height=320,
        )
    elif pred_v6.empty:
        pass
    else:
        st.caption("Probabilidades auxiliares ainda não geradas nesta base.")

    st.markdown("#### Nowcast epidemiológico auxiliar (SRAG / arbovírus)")
    ui_theme.callout(
        "Tendência de curto prazo e P(aumento) são auxiliares. "
        "Não alteram o nível SES nem substituem boletim epidemiológico oficial.",
        "info",
    )
    if epi_nowcast_skill is not None and not epi_nowcast_skill.empty:
        sk = epi_nowcast_skill.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Municípios", int(sk.get("n_municipios") or 0))
        pct = sk.get("pct_atencao_aumento")
        c2.metric("Atenção aumento", f"{100 * float(pct):.0f}%" if pd.notna(pct) else "—")
        c3.metric("SRAG ↑", int(sk.get("n_srag_aumento") or 0))
        c4.metric("Arbovírus ↑", int(sk.get("n_arbo_aumento") or 0))
    epi_view = epi_nowcast.copy() if epi_nowcast is not None and not epi_nowcast.empty else pd.DataFrame()
    if epi_view.empty and not resumo.empty and "nowcast_alerta" in resumo.columns:
        epi_view = resumo[
            [
                c
                for c in (
                    "municipio",
                    "regional_saude",
                    "casos_srag",
                    "srag_p_aumento",
                    "srag_tendencia",
                    "casos_arbovirus_7d",
                    "arbo_p_aumento",
                    "arbo_tendencia",
                    "nowcast_alerta",
                )
                if c in resumo.columns
            ]
        ].copy()
    if not epi_view.empty:
        if "cod_ibge" in epi_view.columns and "cod_ibge" in resumo.columns:
            epi_view["cod_ibge"] = normalize_cod_ibge(epi_view["cod_ibge"])
            epi_view = epi_view[epi_view["cod_ibge"].isin(resumo["cod_ibge"].dropna().astype(str))]
        show_df(
            epi_view.sort_values("srag_p_aumento", ascending=False)
            if "srag_p_aumento" in epi_view.columns
            else epi_view,
            [
                "municipio",
                "regional_saude",
                "srag_casos_7d",
                "srag_tendencia",
                "srag_p_aumento",
                "arbo_casos_7d",
                "arbo_tendencia",
                "arbo_p_aumento",
                "nowcast_alerta",
                "casos_srag",
                "casos_arbovirus_7d",
            ],
            height=320,
        )
    else:
        st.info(
            "Nowcast epi ainda sem dados. Rode o enrichment com SIVEP/arboviroses populados "
            "(`regenerar_sistema_completo.py`) ou use o resumo após VPN/DW."
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
# Alertas + seções epidemiológicas/hidrológicas integradas
# ---------------------------------------------------------------------
elif SECTION_KEY == "Alertas":
    ui_theme.section_title(
        "Boletins CIEVS · padrão SES-MT",
        "Prévia no mesmo formato do Telegram/e-mail: resumo → KPI com status → ações → prioritários",
    )
    ui_theme.callout(AVISO_SINAL_VS_ATIVACAO, "warn")
    ui_theme.callout(
        "Os boletins **não buscam APIs ao vivo**: leem `resumo_municipal_atual` / "
        "`alerta_integrado_sis_titan` já gravados. No Cloud isso é o snapshot "
        "`sis_cloud_seed.db` até rodar pipeline + `exportar_snapshot_cloud.py` e publicar. "
        "`gerado_em` = hora da montagem do texto; use **Dados do sistema** como frescor real.",
        "warn",
    )
    _ref_resumo = None
    if isinstance(resumo_all, pd.DataFrame) and not resumo_all.empty:
        for _c in ("data_processamento", "data_referencia", "data"):
            if _c in resumo_all.columns:
                _s = pd.to_datetime(resumo_all[_c], errors="coerce")
                if _s.notna().any():
                    _ref_resumo = pd.Timestamp(_s.max()).strftime("%Y-%m-%d %H:%M")
                    break
    _ref_ai = None
    if isinstance(alerta_integrado, pd.DataFrame) and not alerta_integrado.empty and "data_processamento" in alerta_integrado.columns:
        _s = pd.to_datetime(alerta_integrado["data_processamento"], errors="coerce")
        if _s.notna().any():
            _ref_ai = pd.Timestamp(_s.max()).strftime("%Y-%m-%d %H:%M")
    ui_theme.insight_cards(
        [
            ("Base ativa", backend_name(), "SQLite seed / Postgres"),
            ("Resumo (máx.)", _ref_resumo or "—", "data no resumo municipal"),
            ("Alerta integrado", _ref_ai or "—", "data_processamento"),
            ("Municípios no resumo", str(len(resumo_all) if isinstance(resumo_all, pd.DataFrame) else 0), "estadual usa resumo completo"),
        ]
    )
    ui_theme.callout(
        "Tema alinhado ao portal oficial SES-MT (azul institucional). "
        "Envio externo desligado por padrão (SEND_ALERT_ON_LEVEL_CHANGE=false). "
        "Valide a prévia abaixo antes de armar canais.",
        "warn",
    )
    render_interpretacao(
        "alertas",
        GUIDE_ALERTAS,
        lambda: narrativa_alertas(alerta_integrado, resumo),
    )

    status = alert_channel_status()
    ui_theme.insight_cards(
        [
            ("Envio externo", "LIGADO" if status["envio_ligado"] else "DESLIGADO", f"flag={status['flag']}"),
            ("Canal central", "só SES" if status.get("central_only_ses", True) else "todas", str(status["email_to"])),
            ("Telegram central", "ativo" if status["telegram"] else "inativo", "somente estadual"),
            (
                "Fan-out territorial",
                "ATIVO" if status.get("fanout_enabled") else "adiado",
                (
                    f"{status.get('contacts_n', 0)} contato(s)"
                    if status.get("contacts_available")
                    else "sem planilha"
                ),
            ),
        ]
    )
    ui_theme.callout(
        "Roteamento SES-MT: canal central (e-mail/Telegram CIEVS) recebe somente o estadual. "
        "Regionais, municipais e Cuiabá são gerados; envio territorial só com planilha + ALERT_FANOUT_ENABLED.",
        "tip",
    )

    route = routing_status_summary()
    st.markdown("### Roteamento (central × territorial)")
    ui_theme.callout(
        "Canal central (CIEVS / notifica) recebe só o alerta **estadual**. "
        "Fan-out regional/municipal exige `ALERT_FANOUT_ENABLED=true` + planilha de contatos.",
        "tip",
    )
    ui_theme.insight_cards(
        [
            (
                "Fan-out territorial",
                "LIGADO" if route.get("fanout_enabled") else "DESLIGADO",
                "ALERT_FANOUT_ENABLED",
            ),
            (
                "Planilha contatos",
                "ok" if route.get("contacts_disponivel") else "ausente",
                f"{route.get('contacts_n', 0)} ativos",
            ),
            ("Caminho", str(route.get("contacts_path") or "—")[:40], "ALERT_CONTACTS_CSV"),
            ("Modelo", "exemplo CSV", str(route.get("exemplo_csv") or "")),
        ]
    )
    if not route.get("contacts_disponivel"):
        st.caption(
            "Copie `config/contatos_alertas.exemplo.csv` → `data/input/contatos_alertas.csv` "
            "e preencha e-mails/Telegram reais (fora do git)."
        )
    elif route.get("contacts_por_tipo"):
        st.caption("Contatos ativos por tipo: " + ", ".join(f"{k}={v}" for k, v in route["contacts_por_tipo"].items()))

    st.markdown("### Critérios de escalonamento (técnico → decisão humana)")
    ui_theme.callout(AVISO_SINAL_VS_ATIVACAO, "warn")
    show_df(pd.DataFrame(CRITERIOS_ESCALONAMENTO), height=260)

    # ------------------------------------------------------------------
    # Boletins multinível no padrão SES legível
    # ------------------------------------------------------------------
    st.markdown("### Validação dos boletins (padrão SES legível)")
    try:
        from sisclima.engines.alertas_multinivel import (
            build_alertas_multinivel,
            payloads_to_dataframe,
            persist_payloads,
        )

        min_lvl = st.selectbox(
            "Nível mínimo para gerar boletim municipal",
            ["amarela", "laranja", "vermelha", "roxa"],
            index=1,
            key="alerta_min_nivel_multi",
        )
        # Estadual e regionais usam o recorte completo; municipais respeitam o filtro da UI.
        _resumo_alertas = resumo_all if isinstance(resumo_all, pd.DataFrame) and not resumo_all.empty else resumo
        if (
            isinstance(resumo, pd.DataFrame)
            and isinstance(resumo_all, pd.DataFrame)
            and len(resumo) < len(resumo_all)
        ):
            st.caption(
                f"Filtro ativo: {len(resumo)}/{len(resumo_all)} municípios na UI — "
                "o boletim estadual/regionais usa o estado completo; a lista municipal abaixo segue o filtro."
            )
        payloads = build_alertas_multinivel(
            _resumo_alertas,
            alerta_integrado=alerta_integrado if isinstance(alerta_integrado, pd.DataFrame) else None,
            predicao_7d=pred_v6 if isinstance(pred_v6, pd.DataFrame) else None,
            min_level=min_lvl,
        )
        # Se houver filtro, regenerar só a fatia municipal a partir do resumo filtrado
        if (
            isinstance(resumo, pd.DataFrame)
            and isinstance(resumo_all, pd.DataFrame)
            and 0 < len(resumo) < len(resumo_all)
        ):
            payloads_filtro = build_alertas_multinivel(
                resumo,
                alerta_integrado=alerta_integrado if isinstance(alerta_integrado, pd.DataFrame) else None,
                predicao_7d=pred_v6 if isinstance(pred_v6, pd.DataFrame) else None,
                min_level=min_lvl,
            )
            payloads = [p for p in payloads if p.get("escopo") != "municipal"] + [
                p for p in payloads_filtro if p.get("escopo") == "municipal"
            ]
        tab_est, tab_reg, tab_mun, tab_cba = st.tabs(
            ["① Estadual (SES)", "② Regionais", "③ Municipais", "④ Cuiabá Vigidesastre"]
        )
        by_scope = {
            k: [p for p in payloads if p.get("escopo") == k]
            for k in ("estadual", "regional", "municipal", "cuiaba")
        }

        def _render_scope(scope_payloads: list, tab, *, expand_preview: bool = False) -> None:
            with tab:
                if not scope_payloads:
                    st.info("Nenhum boletim neste escopo para o recorte/nível atuais.")
                    return
                labels = [
                    f"{p.get('icone', '')} {p.get('alvo_nome')} · {p.get('nivel')}" for p in scope_payloads
                ]
                idx = 0
                if len(labels) > 1:
                    idx = st.selectbox(
                        "Selecione o boletim",
                        list(range(len(labels))),
                        format_func=lambda i: labels[i],
                        key=f"sel_alerta_{scope_payloads[0].get('escopo')}",
                    )
                p = scope_payloads[int(idx)]
                esc = str(p.get("escopo") or "")
                st.markdown(f"#### {p.get('titulo')}")
                c_a, c_b, c_c = st.columns(3)
                c_a.metric("Nível", f"{p.get('icone')} {p.get('nivel')}")
                c_b.metric("Municípios no escopo", p.get("n_municipios", 0))
                pred = p.get("predicao") or {}
                c_c.metric(
                    "Predição 7d",
                    f"{pred.get('icone_predicao', '')} {pred.get('nivel_predicao_7d', '—')}",
                )
                ui_theme.callout(boletim_destinatario_resumo(esc, status), "info")

                txt = format_boletim_painel(p)
                st.markdown("##### Prévia operacional (igual ao envio Telegram/e-mail)")
                st.code(txt, language=None)
                st.download_button(
                    "Baixar boletim (.txt)",
                    data=txt,
                    file_name=f"alerta_{esc}_{p.get('alvo_id')}.txt",
                    mime="text/plain",
                    key=f"dl_alerta_txt_{esc}_{p.get('alvo_id')}",
                )
                st.caption(f"{len(txt)} caracteres · padrão: resumo → KPI+status → ações → prioritários/rodapé")

                with st.expander("Indicadores brutos (consulta técnica)", expanded=False):
                    ind_df = pd.DataFrame(p.get("indicadores") or [])
                    if ind_df.empty:
                        st.caption("Sem indicadores preenchidos neste boletim.")
                    else:
                        view = ind_df.rename(columns={"rotulo": "Indicador", "valor": "Valor"})
                        cols = [c for c in ["Indicador", "Valor", "escala", "limiar"] if c in view.columns]
                        show_df(view, cols, height=260)

        _render_scope(by_scope["estadual"], tab_est, expand_preview=True)
        _render_scope(by_scope["regional"], tab_reg)
        _render_scope(by_scope["municipal"], tab_mun)
        _render_scope(by_scope["cuiaba"], tab_cba)

        resumo_multi = payloads_to_dataframe(payloads)
        st.markdown("#### Painel consolidado dos 4 níveis")
        show_df(
            resumo_multi,
            [
                c
                for c in [
                    "icone",
                    "escopo",
                    "alvo_nome",
                    "nivel",
                    "n_municipios",
                    "nivel_predicao_7d",
                    "n_indicadores",
                    "gerado_em",
                ]
                if c in resumo_multi.columns
            ],
            height=280,
        )
        if st.button("Persistir pacotes multinível na base (`alertas_multinivel_v1`)", key="btn_persist_multi"):
            n = persist_payloads(payloads)
            st.success(f"{n} boletim(ns) gravado(s) em alertas_multinivel_v1.")
    except Exception as exc:
        st.error(f"Falha ao montar alertas multinível: {exc}")

    st.markdown("### Alerta integrado municipal ARARAS MT — apoio à leitura")
    ai = alerta_integrado.copy() if isinstance(alerta_integrado, pd.DataFrame) else pd.DataFrame()
    if not ai.empty and "cod_ibge" in ai.columns and "cod_ibge" in resumo.columns:
        ai = ai[ai["cod_ibge"].astype(str).isin(resumo["cod_ibge"].dropna().astype(str))]
    if ai.empty:
        st.info("Tabela alerta_integrado_sis_titan ainda não gerada. Rode completar_sistema_operacional.py.")
    else:
        n_laranja = int((pd.to_numeric(ai.get("score_alerta_integrado"), errors="coerce").fillna(0) >= 2).sum())
        ui_theme.insight_cards(
            [
                ("Integrado ≥ laranja", n_laranja, "municípios"),
                ("INMET", len(inmet_alertas), "registros"),
                ("Cemaden", len(cemaden_alertas_tab), "registros"),
                ("Hidro ANA", len(hidro_risco), "municípios"),
            ]
        )
        if "nivel_alerta_integrado" in ai.columns:
            map_ai, _, _ = prepare_map_dataframe(
                ai.rename(columns={"nivel_alerta_integrado": "nivel"}) if "nivel" not in ai.columns else ai
            )
            if "nivel" not in map_ai.columns and "nivel_alerta_integrado" in ai.columns:
                map_ai = ai.copy()
                map_ai["nivel"] = map_ai["nivel_alerta_integrado"]
                map_ai, _, _ = prepare_map_dataframe(map_ai)
            map_plot = map_ai if "nivel" in map_ai.columns else ai.rename(columns={"nivel_alerta_integrado": "nivel"})
            choropleth_or_points(
                map_plot,
                geojson_mun,
                "nivel",
                "Alerta integrado ARARAS",
                hover_cols=[
                    c
                    for c in [
                        "componente_dominante",
                        "motivo_integrado",
                        "acao_recomendada",
                        "utci_proxy",
                        "indice_saturacao_solo",
                    ]
                    if c in ai.columns
                ],
                categorical=True,
            )
        show_df(
            safe_sort(
                ai,
                ["score_alerta_integrado"] if "score_alerta_integrado" in ai.columns else [],
                ascending=[False],
            ),
            [
                c
                for c in [
                    "cod_ibge",
                    "municipio",
                    "regional_saude",
                    "nivel_sis",
                    "nivel_alerta_integrado",
                    "score_alerta_integrado",
                    "componente_dominante",
                    "motivo_integrado",
                    "acao_recomendada",
                ]
                if c in ai.columns
            ],
            height=340,
        )

    st.markdown("### SOP — passo a passo (CIEVS)")
    for step in ALERT_SOP_STEPS:
        st.markdown(f"**{step['passo']}** — {step['texto']}")

    with st.expander("Checklist antes de armar o envio", expanded=True):
        chk_state: dict[str, bool] = {}
        for item in ALERT_CHECKLIST:
            key = f"chk_alerta_{abs(hash(item)) % 100000}"
            chk_state[item] = st.checkbox(item, value=False, key=key)
        col_u, col_d = st.columns(2)
        usuario_val = col_u.text_input("Quem valida (iniciais/nome)", value="cievs", key="val_humana_user")
        decisao_val = col_d.selectbox(
            "Decisão",
            ["validado_pronto_envio", "validado_manter_bloqueio", "precisa_revisao", "falso_alarme"],
            key="val_humana_decisao",
        )
        obs_val = st.text_area("Observação (opcional)", key="val_humana_obs", height=80)
        if st.button("Registrar validação humana", key="btn_val_humana"):
            try:
                persist_checklist_validation(
                    data_referencia=str(sentinel.get("data", sentinel.get("data_referencia", ""))),
                    nivel=str(nivel_estado),
                    usuario=usuario_val,
                    decisao=decisao_val,
                    checklist_items=chk_state,
                    observacao=obs_val or "",
                )
                st.success("Validação gravada em `alertas_validacao_humana` (não envia alerta).")
            except Exception as exc:
                st.error(f"Falha ao gravar validação: {exc}")

    st.markdown("### Boletim executivo SES (prévia legível)")
    ui_theme.callout(
        "Prévia no padrão SES (resumo → KPI → ações → IA → prioritários) — não dispara Telegram/e-mail. "
        "Use para sala de situação antes de armar o envio.",
        "info",
    )
    if st.button("Gerar prévia do boletim SES", key="btn_boletim_ses"):
        bol = preview_boletim_executivo_ses(
            resumo_all if isinstance(resumo_all, pd.DataFrame) and not resumo_all.empty else resumo,
            alerta_integrado=alerta_integrado if isinstance(alerta_integrado, pd.DataFrame) else None,
            predicao_7d=pred_v6 if isinstance(pred_v6, pd.DataFrame) else None,
        )
        st.session_state["boletim_ses_preview"] = bol
    bol = st.session_state.get("boletim_ses_preview")
    if isinstance(bol, dict) and bol.get("ok"):
        _payload = bol.get("payload") or {}
        st.caption(
            f"{bol.get('titulo')} · nível {bol.get('nivel')} · "
            f"{bol.get('n_municipios')} municípios · "
            f"dados {_payload.get('data_referencia') or '—'} · "
            f"montado {_payload.get('gerado_em') or '—'}"
        )
        st.code(bol.get("texto") or "")
        st.download_button(
            "Baixar boletim SES (.txt)",
            data=str(bol.get("texto") or ""),
            file_name="boletim_ses_preview.txt",
            mime="text/plain",
            key="dl_boletim_ses",
        )
    elif isinstance(bol, dict) and bol.get("ok") is False:
        st.warning(bol.get("texto") or "Sem boletim.")

    st.markdown("### Histórico de mudança de nível (legado)")
    preview = preview_state_alert(
        str(sentinel.get("data", sentinel.get("data_referencia", ""))),
        str(nivel_estado),
        str(motivo_estado).split("; "),
    )
    c1, c2 = st.columns(2)
    c1.metric("Nível persistido", preview["nivel_anterior"])
    c2.metric("Nível desta rodada", preview["nivel_novo"])
    ui_theme.callout(preview["acao"], "tip" if status["envio_ligado"] else "info")
    with st.expander("Mensagem clássica de mudança de nível", expanded=False):
        st.code(preview["subject"] + "\n\n" + preview["message"])

    st.markdown("### Candidatos municipais (plantão — sem envio automático ao CIEVS)")
    cand = municipal_alert_candidates(resumo)
    if cand.empty:
        st.info("Nenhum município no critério laranja+/↑7d/vigilância alta neste recorte.")
    else:
        st.caption(f"{len(cand)} município(s) na fila — priorize regionais e motive a comunicação.")
        show_df(cand.head(25), height=360)

    st.markdown("### Histórico de nível (`nivel_historico`)")
    hist_nivel = recent_nivel_historico(40)
    if hist_nivel.empty:
        st.caption("Sem leituras ainda — rode o pipeline para anexar cada atualização de `nivel_atual`.")
    else:
        show_df(
            hist_nivel,
            [
                c
                for c in ["created_at", "data_referencia", "nivel_anterior", "nivel", "score", "motivo"]
                if c in hist_nivel.columns
            ],
            height=260,
        )

    st.markdown("### Validações humanas")
    hist_val = recent_validacoes_humanas(20)
    if hist_val.empty:
        st.caption("Nenhuma validação registrada ainda.")
    else:
        show_df(
            hist_val,
            [
                c
                for c in ["created_at", "data_referencia", "nivel", "usuario", "decisao", "observacao"]
                if c in hist_val.columns
            ],
            height=220,
        )

    st.markdown("### Histórico `alertas_enviados`")
    hist_alertas = recent_alert_log(30)
    if hist_alertas.empty:
        st.caption("Nenhum registro de envio/bloqueio ainda.")
    else:
        show_df(
            hist_alertas,
            [c for c in ["created_at", "nivel_anterior", "nivel_novo", "titulo", "status", "canais"] if c in hist_alertas.columns],
            height=280,
        )

    st.markdown("### Auditoria de tabelas")
    tables = [
        "resumo_municipal_atual",
        "alerta_integrado_sis_titan",
        "indicadores_painel_municipal",
        "met_biometeo",
        "solo_saturacao_municipal",
        "qualidade_ar_municipal",
        "hospital_ocupacao_municipio",
        "epi_pressao_assistencial",
        "alerta_inteligente_municipal_v6",
        "predicao_calor_7d_municipal_v6",
        "analise_clima_saude_odds_ratio_v1",
        "alertas_enviados",
        "nivel_historico",
        "alertas_validacao_humana",
        "alertas_multinivel_v1",
        "inmet_alertas",
        "cemaden_alertas",
        "ana_risco_municipal",
        "hidro_risco_municipal",
        "ops_resumo_operacional_cnes",
    ]
    audit = pd.DataFrame([{"tabela": t, "linhas": table_count_ui(t)} for t in tables])
    st.dataframe(audit, use_container_width=True)

    st.markdown("#### Alertas Cemaden (MT)")
    cemaden = cemaden_alertas_tab if not cemaden_alertas_tab.empty else load_table("cemaden_alertas")
    if cemaden.empty:
        st.info("Sem alertas Cemaden carregados. Ative USE_CEMADEN=true e rode o pipeline.")
    else:
        st.caption(f"Registros: {len(cemaden)}")
        show_df(
            cemaden,
            [c for c in ["data", "cod_ibge", "municipio", "uf", "tipo_risco", "evento", "nivel_alerta", "nivel_sis", "status", "fonte"] if c in cemaden.columns],
            height=280,
        )

    st.markdown("#### Municípios em maior nível operacional")
    _sk = [c for c in ["score_alerta_integrado", "score", "indice_vigilancia_integrada", "risco_cumulativo_3d"] if c in resumo.columns]
    show_df(
        safe_sort(resumo, _sk, ascending=[False] * len(_sk)) if _sk else resumo,
        [c for c in ["cod_ibge", "municipio", "regional_saude", "nivel", "nivel_alerta_integrado", "score", "score_alerta_integrado", "componente_dominante", "utci_proxy", "indice_saturacao_solo", "motivo_integrado", "motivo"] if c in resumo.columns],
        height=320,
    )

elif SECTION_KEY == "Arboviroses":
    _recorte_cod = None
    if _PAINEL_PUBLICO and "cod_ibge" in resumo.columns:
        _recorte_cod = set(resumo["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False).dropna())
    _call_view(render_arboviroses, publico=_PAINEL_PUBLICO, recorte_codigos=_recorte_cod)

elif SECTION_KEY == "SIVEP":
    render_sivep()

elif SECTION_KEY == "Sentinela SG":
    render_sentinela_sg()

elif SECTION_KEY == "GeoCalor":
    render_geocalor()

elif SECTION_KEY == "AdaptaSUS / Guia MS":
    render_adaptasus(resumo)

elif SECTION_KEY == "Cemaden / ANA":
    _recorte_cod = None
    if _PAINEL_PUBLICO and "cod_ibge" in resumo.columns:
        _recorte_cod = set(resumo["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False).dropna())
    _call_view(render_hidrologia, publico=_PAINEL_PUBLICO, recorte_codigos=_recorte_cod)

elif SECTION_KEY == "Sazonalidade / OR":
    ui_theme.section_title(
        "Sazonalidade e Odds Ratio",
        "Padrão histórico e chance relativa clima–agravos",
    )
    ui_theme.callout(
        "Esta aba descreve padrão histórico e chance relativa entre grupos de municípios. "
        "Não prova que o clima causou o caso individual.",
        "info",
    )
    st.markdown(
        """
**Como ler estes dados**

1. **Índice sazonal mensal** — acima de 1 o mês é historicamente mais crítico do que a média do período. A linha tracejada marca a média (1,0).
2. **Heatmap semana × ano** — cores mais quentes indicam semanas em que o indicador costuma subir. Compare a semana atual com o mesmo período de anos anteriores.
3. **Odds Ratio (OR)** — compara municípios mais expostos vs menos expostos. OR &gt; 1 sugere maior chance do desfecho no grupo exposto; olhe também o intervalo de confiança e se o resultado é significativo (p &lt; 0,05).
4. **Lags (0–14 dias)** — mostra com quantos dias de defasagem o clima se associa ao desfecho. É exploratório: gera hipótese, não decisão clínica.
        """
    )
    if not _PAINEL_PUBLICO:
        ui_theme.callout(
            "Odds Ratio e correlações temporais são análises ecológicas exploratórias: ajudam na priorização, não comprovam causalidade individual.",
            "warn",
        )
        render_interpretacao(
            "sazonal_or",
            GUIDE_SAZONAL_OR,
            lambda: narrativa_sazonal_or(analise_or_v1, sazon_mensal_v1),
        )
        st.markdown(
            "- Análise ecológica de sazonalidade e odds ratio clima–agravos do ARARAS "
            "(calor, arboviroses, SRAG, ocupação).  \n"
            "- Documento local: `docs/ANALISE_OR_SAZONALIDADE.md`."
        )

    if sazon_picos_v1.empty and sazon_mensal_v1.empty and analise_or_v1.empty:
        st.info(
            "Sazonalidade e odds ratio ainda não disponíveis neste recorte."
            if _PAINEL_PUBLICO
            else "Tabelas de sazonalidade/OR ainda não geradas. Rode completar_sistema_operacional.py."
        )
    else:
        c1, c2, c3 = st.columns(3)
        if not sazon_mensal_v1.empty:
            top = sazon_mensal_v1.sort_values("indice_sazonal", ascending=False).head(1)
            c1.metric("Mês de pico sazonal", str(top["mes_rotulo"].iloc[0]) if not top.empty else "—")
        else:
            c1.metric("Mês de pico sazonal", "—")

        if not sazon_picos_v1.empty:
            se = sazon_picos_v1[sazon_picos_v1["tipo"] == "se_atual_vs_media"].head(1)
            if not se.empty and pd.notna(se.get("valor_atual").iloc[0]) and pd.notna(se.get("valor_medio_historico").iloc[0]):
                atual = float(se["valor_atual"].iloc[0])
                media = float(se["valor_medio_historico"].iloc[0])
                c2.metric("SE atual vs média", f"{atual:.2f}", delta=f"{(atual - media):+.2f}")
            else:
                c2.metric("SE atual vs média", "—")
        else:
            c2.metric("SE atual vs média", "—")

        if not analise_or_v1.empty and "significativo_005" in analise_or_v1.columns:
            c3.metric("OR significativos (p<0.05)", int(pd.to_numeric(analise_or_v1["significativo_005"], errors="coerce").fillna(0).astype(int).sum()))
        else:
            c3.metric("OR significativos (p<0.05)", 0)

        st.markdown("#### Índice sazonal mensal")
        if not sazon_mensal_v1.empty:
            sm = sazon_mensal_v1.copy()
            sm["indice_sazonal"] = pd.to_numeric(sm["indice_sazonal"], errors="coerce")
            fig = px.bar(
                sm.sort_values("mes"),
                x="mes_rotulo",
                y="indice_sazonal",
                color="acima_media" if "acima_media" in sm.columns else None,
                color_discrete_map={True: LEVEL_COLOR_MAP["laranja"], False: LEVEL_COLOR_MAP["verde"]},
                title="Índice sazonal mensal (acima de 1 = acima da média histórica)",
            )
            fig.add_hline(y=1.0, line_dash="dash")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem série mensal para índice sazonal.")

        st.markdown("#### Heatmap semana epidemiológica × ano")
        if not sazon_heat_v1.empty:
            h = sazon_heat_v1.copy()
            h["valor"] = pd.to_numeric(h["valor"], errors="coerce")
            mat = h.pivot_table(index="ano_epi", columns="semana_epi", values="valor", aggfunc="mean")
            if not mat.empty:
                fig_h = px.imshow(
                    mat,
                    aspect="auto",
                    color_continuous_scale="YlOrRd",
                    title="Heatmap sazonal (SE × ano)",
                    labels={"x": "Semana epidemiológica", "y": "Ano epidemiológico", "color": "valor"},
                )
                st.plotly_chart(fig_h, use_container_width=True)
            else:
                st.info("Heatmap vazio nesta rodada.")
        else:
            st.info("Sem dados para heatmap sazonal.")

        st.markdown("#### Odds Ratio clima–agravos/ocupação")
        if not analise_or_v1.empty:
            or_df = analise_or_v1.copy()
            show_df(
                or_df,
                [c for c in ["exposicao", "desfecho", "n_analisado", "limiar_exposicao", "limiar_desfecho", "or", "ic95_inferior", "ic95_superior", "p_value", "significativo_005", "interpretacao"] if c in or_df.columns],
                height=340,
            )
        else:
            st.info("Sem OR calculado nesta rodada.")

        st.markdown("#### Lags clima–desfecho (0–14 dias)")
        if not lags_v1.empty:
            lg = lags_v1.copy().head(150)
            lg["lag_dias"] = pd.to_numeric(lg["lag_dias"], errors="coerce")
            lg["abs_spearman"] = pd.to_numeric(lg["abs_spearman"], errors="coerce")
            fig_l = px.scatter(
                lg,
                x="lag_dias",
                y="abs_spearman",
                color="desfecho",
                symbol="exposicao",
                title="Força da correlação temporal por lag (|Spearman|)",
                hover_data=[c for c in ["exposicao", "desfecho", "spearman", "pearson", "n_dias_validos"] if c in lg.columns],
            )
            st.plotly_chart(fig_l, use_container_width=True)
            show_df(
                lg.sort_values(["abs_spearman", "n_dias_validos"], ascending=[False, False]),
                [c for c in ["exposicao", "desfecho", "lag_dias", "spearman", "pearson", "abs_spearman", "n_dias_validos"] if c in lg.columns],
                height=300,
            )
        else:
            st.info("Sem tabela de lags nesta rodada.")
        if not _PAINEL_PUBLICO:
            ui_theme.glossary_expander(["indice_sazonal", "odds_ratio", "ocupacao_leitos_pct", "pressao_calor_pct"])

elif SECTION_KEY == "Correlação clima-saúde":
    ui_theme.section_title(
        "Correlação clima–saúde",
        "Associações ecológicas exploratórias (Spearman) — não implicam causalidade individual",
    )
    st.markdown(
        """
        Esta seção cruza **exposições climáticas/ambientais** com **desfechos de saúde** no corte municipal.
        Use para priorizar hipóteses e vigilância; valide antes de decisão clínica ou operacional.
        """
    )

    corr_persistida = analise_corr_v8.copy() if not analise_corr_v8.empty else pd.DataFrame()
    corr_live = compute_spearman_pairs(resumo, min_n=12)

    opcoes_fonte = []
    if not corr_persistida.empty:
        opcoes_fonte.append("Tabela persistida (pipeline)")
    opcoes_fonte.append("Cálculo ao vivo (resumo atual)")
    fonte = st.radio("Fonte das correlações", opcoes_fonte, horizontal=True, key="corr_fonte")
    corr = corr_persistida if fonte.startswith("Tabela") and not corr_persistida.empty else corr_live
    if corr.empty and not corr_live.empty:
        corr = corr_live

    render_interpretacao(
        "correlacao",
        GUIDE_CORR,
        lambda: narrativa_correlacao(corr),
    )

    cmeta1, cmeta2, cmeta3 = st.columns(3)
    cmeta1.metric("Pares persistidos", len(corr_persistida))
    cmeta2.metric("Pares ao vivo", len(corr_live))
    cmeta3.metric(
        "Base analítica",
        "OK" if not analise_base_v8.empty else "—",
    )

    if corr.empty:
        st.info("Sem pares suficientes (mín. 12 municípios com dados válidos em exposição e desfecho).")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Pares calculados", len(corr))
        c2.metric("|rho| máx.", f"{float(corr['abs_rho'].max()):.2f}" if "abs_rho" in corr.columns else "—")
        top = corr.iloc[0]
        c3.metric("Par mais forte", f"{top.get('exposicao')} → {top.get('desfecho')}")

        plot = corr.head(25).copy()
        plot["par"] = plot["exposicao"].astype(str) + " → " + plot["desfecho"].astype(str)
        fig = px.bar(
            plot.sort_values("abs_rho", ascending=True),
            x="abs_rho",
            y="par",
            orientation="h",
            title="Maiores |rho Spearman| clima–saúde",
            hover_data=[c for c in ["rho", "p_valor", "p_valor_approx", "n_municipios"] if c in plot.columns],
        )
        st.plotly_chart(fig, use_container_width=True)

        # Scatter do par selecionado
        pares = (corr["exposicao"].astype(str) + " → " + corr["desfecho"].astype(str)).tolist()
        escolhido = st.selectbox("Explorar par no scatter", pares, index=0)
        exp_sel, des_sel = [p.strip() for p in escolhido.split("→", 1)]
        if exp_sel in resumo.columns and des_sel in resumo.columns:
            sc = resumo[[c for c in ["municipio", "regional_saude", "nivel", exp_sel, des_sel] if c in resumo.columns]].copy()
            sc[exp_sel] = pd.to_numeric(sc[exp_sel], errors="coerce")
            sc[des_sel] = pd.to_numeric(sc[des_sel], errors="coerce")
            sc = sc.dropna(subset=[exp_sel, des_sel])
            if not sc.empty:
                fig2 = px.scatter(
                    sc,
                    x=exp_sel,
                    y=des_sel,
                    color="nivel" if "nivel" in sc.columns else None,
                    hover_name="municipio" if "municipio" in sc.columns else None,
                    title=f"Dispersão municipal — {escolhido}",
                )
                st.plotly_chart(fig2, use_container_width=True)

        show_df(
            corr,
            [c for c in ["exposicao", "desfecho", "metodo", "rho", "abs_rho", "p_valor", "p_valor_approx", "n_municipios", "nota"] if c in corr.columns],
            height=420,
        )

    if not analise_alertas_v8.empty:
        st.markdown("##### Alertas estatísticos associados")
        show_df(analise_alertas_v8, height=280)

# Rodapé institucional SES-MT
ui_theme.ses_footer()
