# -*- coding: utf-8 -*-
"""Seções epidemiológicas e hidrológicas para o painel unificado (sem set_page_config)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from sisclima.core.db import backend_name, read_table
from sisclima.engines.geospatial import make_choropleth_or_points, prepare_map_dataframe
from sisclima.engines.sentinela_sg_ms import catalog_as_dataframe as catalog_sentinela
from sisclima.engines.sivep_ms_indicators import catalog_as_dataframe as catalog_sivep
from sisclima.ui.theme import callout, section_title
from sisclima.ui.interpretacoes import (
    GUIDE_ADAPTASUS,
    GUIDE_ARBO,
    GUIDE_GEOCALOR,
    GUIDE_HIDRO,
    GUIDE_SENTINELA,
    GUIDE_SIVEP,
    narrativa_adaptasus,
    narrativa_arbo,
    narrativa_geocalor,
    narrativa_hidro,
    narrativa_sentinela,
    narrativa_sivep,
    render_interpretacao,
)


def _filter_recorte(df: pd.DataFrame, recorte_codigos: set[str] | None) -> pd.DataFrame:
    if df is None or df.empty or not recorte_codigos:
        return df if df is not None else pd.DataFrame()
    if "cod_ibge" not in df.columns:
        return df
    cod = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    return df[cod.isin(recorte_codigos)].copy()


def render_arboviroses(*, publico: bool = False, recorte_codigos: set[str] | None = None) -> None:
    section_title(
        "Arboviroses",
        "Dengue, Zika, Chikungunya e correlatas"
        if publico
        else f"Dengue, Zika, Chikungunya e correlatas · base {backend_name()}",
    )
    if not publico:
        callout(
            "Casos em 7 dias mostram a pressão recente. Cruze com calor/chuva na Visão executiva — não projete a temporada só com este recorte.",
            "info",
        )
    arbo = _filter_recorte(read_table("epi_arboviroses"), recorte_codigos)
    arbo_mun = _filter_recorte(read_table("epi_arboviroses_municipal"), recorte_codigos)
    resumo = _filter_recorte(read_table("resumo_municipal_atual"), recorte_codigos)
    if not publico:
        render_interpretacao(
            "arboviroses",
            GUIDE_ARBO,
            lambda: narrativa_arbo(arbo_mun),
        )

    if arbo.empty and arbo_mun.empty:
        st.info(
            "Sem dados de arboviroses neste recorte."
            if publico
            else "Tabelas de arboviroses ainda não geradas. Rode o pipeline."
        )
        return

    c1, c2, c3, c4, c5 = st.columns(5)
    if not arbo_mun.empty:
        c1.metric("Municípios", int(arbo_mun["cod_ibge"].nunique()) if "cod_ibge" in arbo_mun.columns else len(arbo_mun))
        c2.metric("Casos 7d", int(pd.to_numeric(arbo_mun.get("casos_arbovirus_7d"), errors="coerce").fillna(0).sum()))
        c3.metric("Dengue 7d", int(pd.to_numeric(arbo_mun.get("casos_dengue_7d"), errors="coerce").fillna(0).sum()))
        c4.metric("Zika 7d", int(pd.to_numeric(arbo_mun.get("casos_zika_7d"), errors="coerce").fillna(0).sum()))
        c5.metric("Chikungunya 7d", int(pd.to_numeric(arbo_mun.get("casos_chikungunya_7d"), errors="coerce").fillna(0).sum()))
    else:
        c1.metric("Registros diários", len(arbo))
        c2.metric("Agravos", arbo["agravo"].nunique() if "agravo" in arbo.columns else 0)


    st.markdown("##### Ranking municipal (7 dias)")
    if not arbo_mun.empty:
        rank = arbo_mun.copy()
        for col in [
            "casos_arbovirus_7d", "casos_dengue_7d", "casos_zika_7d",
            "casos_chikungunya_7d", "casos_outras_arbovirus_7d",
            "zscore_arbovirus", "incidencia_arbovirus_100k",
        ]:
            if col in rank.columns:
                rank[col] = pd.to_numeric(rank[col], errors="coerce")
        rank = rank.sort_values("casos_arbovirus_7d", ascending=False) if "casos_arbovirus_7d" in rank.columns else rank
        try:
            st.dataframe(rank, width="stretch", height=320)
        except TypeError:
            st.dataframe(rank, use_container_width=True, height=320)
        y_col = next((c for c in ["casos_arbovirus_7d", "incidencia_arbovirus_100k", "zscore_arbovirus"] if c in rank.columns), None)
        if y_col and "municipio" in rank.columns:
            st.plotly_chart(
                px.bar(
                    rank.head(20),
                    x="municipio",
                    y=y_col,
                    color="agravo_dominante" if "agravo_dominante" in rank.columns else None,
                    title=f"Top municípios — arboviroses ({y_col})",
                ),
                use_container_width=True,
            )
    else:
        st.info("Snapshot municipal ainda não disponível.")

    if not arbo.empty and "data" in arbo.columns:
        serie = arbo.copy()
        serie["data"] = pd.to_datetime(serie["data"], errors="coerce")
        serie["notificacoes"] = pd.to_numeric(serie.get("notificacoes"), errors="coerce").fillna(0)
        estado = (
            serie.groupby(["data", "agravo"], as_index=False)["notificacoes"].sum()
            if "agravo" in serie.columns
            else serie.groupby("data", as_index=False)["notificacoes"].sum()
        )
        st.plotly_chart(
            px.line(
                estado,
                x="data",
                y="notificacoes",
                color="agravo" if "agravo" in estado.columns else None,
                title="Notificações diárias — série estadual",
            ),
            use_container_width=True,
        )

    if not arbo_mun.empty and "cod_ibge" in arbo_mun.columns:
        map_src = arbo_mun.copy()
        if "municipio" not in map_src.columns and not resumo.empty:
            r = resumo.copy()
            r["cod_ibge"] = r["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            map_src["cod_ibge"] = map_src["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
            map_src = map_src.merge(
                r[[c for c in ["cod_ibge", "municipio"] if c in r.columns]].drop_duplicates("cod_ibge"),
                on="cod_ibge",
                how="left",
            )
        for col in ["casos_arbovirus_7d", "incidencia_arbovirus_100k", "zscore_arbovirus"]:
            if col in map_src.columns:
                map_src[col] = pd.to_numeric(map_src[col], errors="coerce")
        map_df, geojson_mun, shp_status = prepare_map_dataframe(map_src)
        if not publico:
            st.caption(shp_status)
        color_col = next(
            (c for c in ["casos_arbovirus_7d", "incidencia_arbovirus_100k", "zscore_arbovirus"] if c in map_df.columns),
            None,
        )
        if color_col:
            fig_map = make_choropleth_or_points(
                map_df,
                geojson_mun,
                color_col=color_col,
                title=f"Arboviroses — {color_col}",
                hover_cols=[
                    c for c in [
                        "casos_dengue_7d", "casos_zika_7d", "casos_chikungunya_7d",
                        "agravo_dominante", "incidencia_arbovirus_100k", "zscore_arbovirus",
                    ]
                    if c in map_df.columns
                ],
            )
            if fig_map is not None:
                st.plotly_chart(fig_map, use_container_width=True)


def render_sivep() -> None:
    section_title("SIVEP-Gripe", f"Indicadores MS/SVSA · base {backend_name()}")
    callout(
        "SRAG = internações respiratórias graves. Picos podem acompanhar vírus, fumaça ou ambos — compare com Qualidade do ar e Clima.",
        "tip",
    )
    dic = read_table("dicionario_indicadores_ms_sivep")
    if dic.empty:
        dic = catalog_sivep()
    daily = read_table("epi_sivep_srag")
    weekly = read_table("epi_sivep_se_municipal")
    virus = read_table("epi_sivep_virus_se")
    qualidade = read_table("epi_sivep_qualidade_ms")
    painel = read_table("epi_sivep_indicadores_ms")
    render_interpretacao(
        "sivep",
        GUIDE_SIVEP,
        lambda: narrativa_sivep(daily),
    )

    # Fallback leve: indicadores de SRAG já no resumo municipal (quando a série SIVEP não veio na rodada).
    resumo = read_table("resumo_municipal_atual")
    srag_resumo_cols = [
        c
        for c in (
            "casos_srag",
            "casos_srag_7d",
            "incidencia_srag_100k",
            "obitos_srag",
            "srag_tendencia",
            "prop_uti_pct",
        )
        if c in resumo.columns
    ]
    tem_serie = not (daily.empty and weekly.empty)
    tem_resumo = bool(srag_resumo_cols) and not resumo.empty and any(
        pd.to_numeric(resumo[c], errors="coerce").fillna(0).sum() > 0
        if c != "srag_tendencia"
        else resumo[c].astype(str).str.strip().ne("").any()
        for c in srag_resumo_cols
    )

    if not tem_serie and not tem_resumo:
        callout(
            "SIVEP/SRAG não entrou com série nesta rodada da ETL (tabelas vazias ou fonte local/DW indisponível). "
            "A aba permanece disponível; rode o pipeline com `USE_SIVEP_LOCAL=true` ou a carga DW quando a rede SES estiver ok. "
            "Não interpretar ausência como zero de SRAG no estado.",
            "warn",
        )
        with st.expander("Catálogo oficial MS (referência)", expanded=False):
            st.dataframe(dic, use_container_width=True, height=240)
        return

    if not tem_serie and tem_resumo:
        callout(
            "Série SIVEP completa não disponível nesta rodada. Exibindo sinais de SRAG já consolidados no resumo municipal "
            "(fallback operacional). Não substitui o boletim SIVEP-Gripe oficial.",
            "warn",
        )
        c1, c2, c3 = st.columns(3)
        if "casos_srag_7d" in resumo.columns:
            c1.metric("Casos SRAG 7d (soma mun.)", int(pd.to_numeric(resumo["casos_srag_7d"], errors="coerce").fillna(0).sum()))
        elif "casos_srag" in resumo.columns:
            c1.metric("Casos SRAG (resumo)", int(pd.to_numeric(resumo["casos_srag"], errors="coerce").fillna(0).sum()))
        else:
            c1.metric("Casos SRAG", "—")
        if "incidencia_srag_100k" in resumo.columns:
            c2.metric(
                "Incidência máx. /100 mil",
                f"{float(pd.to_numeric(resumo['incidencia_srag_100k'], errors='coerce').max()):.1f}",
            )
        else:
            c2.metric("Incidência", "—")
        if "srag_tendencia" in resumo.columns:
            top_t = resumo["srag_tendencia"].astype(str).value_counts().head(1)
            c3.metric("Tendência modal", str(top_t.index[0]) if not top_t.empty else "—")
        else:
            c3.metric("Tendência", "—")
        show = resumo[
            [c for c in ["cod_ibge", "municipio", "regional_saude", "nivel"] + srag_resumo_cols if c in resumo.columns]
        ].copy()
        st.dataframe(show, use_container_width=True, height=320)
        with st.expander("Catálogo oficial MS (referência)", expanded=False):
            st.dataframe(dic, use_container_width=True, height=240)
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos (série diária)", int(pd.to_numeric(daily.get("casos_srag"), errors="coerce").fillna(0).sum()) if not daily.empty else 0)
    c2.metric("Óbitos", int(pd.to_numeric(daily.get("obitos"), errors="coerce").fillna(0).sum()) if not daily.empty else 0)
    c3.metric("Municípios", int(daily["municipio"].nunique()) if not daily.empty and "municipio" in daily.columns else 0)
    if not qualidade.empty and "cobertura_lab_pct" in qualidade.columns:
        c4.metric("Cobertura lab. média %", f"{float(pd.to_numeric(qualidade['cobertura_lab_pct'], errors='coerce').mean()):.1f}")
    else:
        c4.metric("Cobertura lab. média %", "—")

    with st.expander("Catálogo oficial MS", expanded=False):
        st.dataframe(dic, use_container_width=True, height=240)

    if not weekly.empty:
        w = weekly.copy()
        w["casos_srag"] = pd.to_numeric(w.get("casos_srag"), errors="coerce")
        estado = w.groupby("se_label", as_index=False)["casos_srag"].sum() if "se_label" in w.columns else pd.DataFrame()
        if not estado.empty:
            st.plotly_chart(
                px.bar(estado, x="se_label", y="casos_srag", title="Casos de SRAG por SE — estadual"),
                use_container_width=True,
            )
        sort_cols = [c for c in ["ano_epi", "semana_epi"] if c in w.columns]
        st.dataframe(
            w.sort_values(sort_cols, ascending=False) if sort_cols else w,
            use_container_width=True,
            height=280,
        )

    if not daily.empty and "incidencia_srag_100k" in daily.columns:
        last = daily.sort_values("data").groupby("cod_ibge", as_index=False).tail(1) if "cod_ibge" in daily.columns else daily.copy()
        map_df, geojson, status = prepare_map_dataframe(last)
        st.caption(status)
        fig = make_choropleth_or_points(
            map_df,
            geojson,
            color_col="incidencia_srag_100k",
            title="Incidência SRAG por 100 mil",
            hover_cols=[c for c in ["casos_srag", "letalidade_pct", "prop_uti_pct", "zscore_srag", "virus_dominante"] if c in map_df.columns],
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    if not virus.empty:
        v = virus.copy()
        v["casos"] = pd.to_numeric(v.get("casos"), errors="coerce")
        if "se_label" in v.columns and "virus" in v.columns:
            estado_v = v.groupby(["se_label", "virus"], as_index=False)["casos"].sum()
            st.plotly_chart(
                px.area(estado_v, x="se_label", y="casos", color="virus", title="Circulação viral por SE"),
                use_container_width=True,
            )

    if not qualidade.empty:
        st.dataframe(qualidade, use_container_width=True, height=240)
    if not painel.empty:
        with st.expander("Painel longo de indicadores MS"):
            st.dataframe(painel, use_container_width=True, height=300)


def render_sentinela_sg() -> None:
    section_title("Sentinela SG", f"Indicadores MS 1–13 · base {backend_name()}")
    callout(
        "Unidades sentinela medem qualidade da vigilância de gripe. Sem dado aqui não significa ausência de síndrome gripal no município.",
        "info",
    )
    dic = read_table("dicionario_indicadores_ms_sentinela_sg")
    if dic.empty:
        dic = catalog_sentinela()
    ind = read_table("epi_sentinela_sg_indicadores")
    sem = read_table("epi_sentinela_sg_semanal")
    virus = read_table("epi_sentinela_sg_virus_se")
    faixa = read_table("epi_sentinela_sg_faixa_etaria")
    render_interpretacao(
        "sentinela_sg",
        GUIDE_SENTINELA,
        lambda: narrativa_sentinela(ind if not ind.empty else sem),
    )

    if ind.empty and sem.empty:
        st.error(
            "Sem dados sentinela SG. Coloque CSVs em `data/input/` e rode o pipeline."
        )
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Indicadores", len(ind))
    c2.metric("US com série", int(sem["unidade_sentinela"].nunique()) if not sem.empty and "unidade_sentinela" in sem.columns else 0)
    c3.metric(
        "Meta atingida",
        int((ind["classificacao"] == "meta_atingida").sum()) if not ind.empty and "classificacao" in ind.columns else 0,
    )

    with st.expander("Catálogo MS (SG-01 … SG-13)", expanded=False):
        st.dataframe(dic, use_container_width=True, height=240)

    if not ind.empty:
        st.dataframe(ind, use_container_width=True, height=300)
        if {"indicador_id", "valor", "unidade_sentinela"}.issubset(ind.columns):
            plot = ind[ind["indicador_id"].isin(["SG-01", "SG-02", "SG-05", "SG-07", "SG-10", "SG-11"])].copy()
            if not plot.empty:
                st.plotly_chart(
                    px.bar(
                        plot,
                        x="indicador_id",
                        y="valor",
                        color="unidade_sentinela",
                        barmode="group",
                        title="Indicadores-chave por US (%)",
                    ),
                    use_container_width=True,
                )

    if not sem.empty:
        st.dataframe(sem, use_container_width=True, height=260)
        if {"se_label", "prop_sg_atendimentos_pct"}.issubset(sem.columns):
            st.plotly_chart(
                px.line(
                    sem,
                    x="se_label",
                    y="prop_sg_atendimentos_pct",
                    color="unidade_sentinela" if "unidade_sentinela" in sem.columns else None,
                    markers=True,
                    title="Proporção SG / atendimentos por SE",
                ),
                use_container_width=True,
            )

    c1, c2 = st.columns(2)
    with c1:
        if not virus.empty:
            st.dataframe(virus, use_container_width=True, height=220)
            if {"se_label", "casos", "virus"}.issubset(virus.columns):
                st.plotly_chart(px.bar(virus, x="se_label", y="casos", color="virus", title="Vírus por SE"), use_container_width=True)
    with c2:
        if not faixa.empty:
            st.dataframe(faixa, use_container_width=True, height=220)
            if {"faixa_etaria", "casos", "virus"}.issubset(faixa.columns):
                st.plotly_chart(px.bar(faixa, x="faixa_etaria", y="casos", color="virus", title="Vírus por faixa etária"), use_container_width=True)


def render_hidrologia(*, publico: bool = False, recorte_codigos: set[str] | None = None) -> None:
    section_title(
        "Cemaden / ANA",
        "Alertas de desastre, nível de rio e chuva"
        if publico
        else f"Cemaden + ANA + precipitação · base {backend_name()}",
    )
    if not publico:
        callout(
            "Cemaden traz alertas oficiais; ANA traz telemetria de chuva e nível de rio (seca/cheia). Cobertura de estações é desigual — cruze com o nível operacional.",
            "info",
        )
    cemaden = _filter_recorte(read_table("cemaden_alertas"), recorte_codigos)
    met = _filter_recorte(read_table("met_biometeo"), recorte_codigos)
    ana_risco = _filter_recorte(read_table("ana_risco_municipal"), recorte_codigos)
    hidro = _filter_recorte(read_table("hidro_risco_municipal"), recorte_codigos)
    resumo = _filter_recorte(read_table("resumo_municipal_atual"), recorte_codigos)
    if not publico:
        render_interpretacao(
            "cemaden_ana",
            GUIDE_HIDRO,
            lambda: narrativa_hidro(cemaden, ana_risco),
        )

    c1, c2, c3 = st.columns(3)
    c1.metric("Alertas Cemaden", len(cemaden))
    c2.metric("Municípios com alerta", int(cemaden["municipio"].nunique()) if not cemaden.empty and "municipio" in cemaden.columns else 0)
    if not met.empty and "precipitacao_mm" in met.columns:
        precip = pd.to_numeric(met["precipitacao_mm"], errors="coerce")
        c3.metric("Precipitação máx. (mm)", f"{float(precip.max()):.1f}" if precip.notna().any() else "—")
    else:
        c3.metric("Precipitação máx. (mm)", "—")

    ana_tel = _filter_recorte(read_table("ana_telemetria"), recorte_codigos)
    ana_est = _filter_recorte(read_table("ana_estacoes"), recorte_codigos)
    st.markdown("##### Nível de rio ANA (seca × cheia)")
    if hidro.empty and ana_risco.empty and ana_tel.empty:
        st.info(
            "Sem dados hidrológicos da ANA neste recorte."
            if publico
            else "Sem dados ANA. Ative `USE_ANA=true` / `ANA_FETCH_SERIES=true` ou use CSV em `data/input/ana_*.csv`."
        )
    else:
        n_seca = n_cheia = n_normal = 0
        if not hidro.empty and "situacao_hidro" in hidro.columns:
            sit = hidro["situacao_hidro"].astype(str).str.lower()
            n_seca = int(sit.eq("seca_baixa").sum())
            n_cheia = int(sit.eq("inundacao_alta").sum())
            n_normal = int(sit.eq("normal").sum())
        elif not hidro.empty and "risco_predominante" in hidro.columns:
            rp = hidro["risco_predominante"].astype(str).str.lower()
            n_seca = int(rp.eq("estiagem_rio_baixo").sum())
            n_cheia = int(rp.eq("cheia_subida_rio").sum())
            n_normal = int(rp.isin(["misto_ou_neutro", "sem_gatilho"]).sum())
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("Municípios em seca", n_seca)
        h2.metric("Em risco de cheia", n_cheia)
        h3.metric("Situação normal", n_normal)
        h4.metric(
            "Com cota (cm)",
            int(pd.to_numeric(hidro["cota_cm"], errors="coerce").notna().sum())
            if not hidro.empty and "cota_cm" in hidro.columns
            else 0,
        )
        if not hidro.empty:
            show_cols = [
                c
                for c in [
                    "cod_ibge",
                    "municipio",
                    "situacao_hidro",
                    "risco_predominante",
                    "nivel_alerta_hidro",
                    "cota_cm",
                    "score_estiagem_max",
                    "score_cheia_max",
                    "motivo_resumo",
                    "data_mais_recente",
                ]
                if c in hidro.columns
            ]
            st.dataframe(hidro[show_cols] if show_cols else hidro, use_container_width=True, height=240)
            map_src = hidro.copy()
            color = (
                "situacao_hidro"
                if "situacao_hidro" in map_src.columns
                else ("risco_predominante" if "risco_predominante" in map_src.columns else "nivel_alerta_hidro")
            )
            map_df, geojson, status = prepare_map_dataframe(map_src)
            if not publico:
                st.caption(status)
            if color and color in map_df.columns:
                fig = make_choropleth_or_points(
                    map_df,
                    geojson,
                    color_col=color,
                    title="Situação hidrológica ANA (seca / cheia)",
                    categorical=True,
                    hover_cols=[
                        c
                        for c in ["cota_cm", "nivel_alerta_hidro", "risco_predominante", "situacao_hidro", "motivo_resumo"]
                        if c in map_df.columns
                    ],
                )
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Telemetria ANA (chuva)")
    if ana_risco.empty and ana_tel.empty:
        st.info("Sem telemetria/risco de chuva ANA nesta rodada.")
    else:
        a1, a2, a3 = st.columns(3)
        a1.metric("Estações", len(ana_est) if not ana_est.empty else 0)
        a2.metric("Leituras", len(ana_tel) if not ana_tel.empty else 0)
        a3.metric("Municípios risco chuva", int(ana_risco["municipio"].nunique()) if not ana_risco.empty and "municipio" in ana_risco.columns else 0)
        if not ana_risco.empty:
            st.dataframe(ana_risco, use_container_width=True, height=240)
            map_df, geojson, status = prepare_map_dataframe(ana_risco)
            if not publico:
                st.caption(status)
            color = "chuva_mm" if "chuva_mm" in map_df.columns else ("nivel_chuva" if "nivel_chuva" in map_df.columns else None)
            if color:
                fig = make_choropleth_or_points(
                    map_df, geojson, color_col=color,
                    title="Chuva ANA por município",
                    categorical=color == "nivel_chuva",
                    hover_cols=[c for c in ["cota_cm", "vazao_m3s", "nivel_chuva"] if c in map_df.columns],
                )
                if fig is not None:
                    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Alertas Cemaden")
    if cemaden.empty:
        st.info(
            "Sem alertas do Cemaden neste recorte."
            if publico
            else "Sem `cemaden_alertas`. Ative `USE_CEMADEN=true` e rode o pipeline."
        )
    else:
        st.dataframe(cemaden, use_container_width=True, height=280)
        map_df, geojson, status = prepare_map_dataframe(cemaden)
        if not publico:
            st.caption(status)
        color_col = "nivel_sis" if "nivel_sis" in map_df.columns else ("nivel_alerta" if "nivel_alerta" in map_df.columns else None)
        if color_col:
            fig = make_choropleth_or_points(
                map_df, geojson, color_col=color_col,
                title="Cemaden — nível por município",
                hover_cols=[c for c in ["evento", "tipo_risco", "nivel_alerta"] if c in map_df.columns],
                categorical=color_col == "nivel_sis",
            )
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Precipitação")
    if met.empty or "precipitacao_mm" not in met.columns:
        st.info("Sem precipitação neste recorte." if publico else "Sem coluna `precipitacao_mm`.")
    else:
        m = met.copy()
        m["data"] = pd.to_datetime(m["data"], errors="coerce")
        m["precipitacao_mm"] = pd.to_numeric(m["precipitacao_mm"], errors="coerce")
        latest = m.sort_values("data").groupby("municipio" if "municipio" in m.columns else "cod_ibge", as_index=False).tail(1)
        map_df, geojson, status = prepare_map_dataframe(latest)
        if not publico:
            st.caption(status)
        fig = make_choropleth_or_points(
            map_df, geojson, color_col="precipitacao_mm",
            title="Precipitação diária (mm)",
            hover_cols=[c for c in ["chuva_mm", "tmax", "umidade_media"] if c in map_df.columns],
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        serie = m.groupby("data", as_index=False)["precipitacao_mm"].mean() if "data" in m.columns else pd.DataFrame()
        if not serie.empty:
            st.plotly_chart(
                px.line(serie, x="data", y="precipitacao_mm", title="Precipitação média estadual (mm/dia)"),
                use_container_width=True,
            )

    if not resumo.empty and "motivo" in resumo.columns:
        hits = resumo[
            resumo["motivo"].astype(str).str.contains(
                "Cemaden|chuva|precip|Cota ANA|hidro|estiagem|cheia", case=False, na=False
            )
        ]
        if not hits.empty:
            st.markdown("##### Motivos operacionais com menção a chuva/Cemaden/rio")
            st.dataframe(
                hits[
                    [
                        c
                        for c in [
                            "cod_ibge",
                            "municipio",
                            "nivel",
                            "score",
                            "situacao_hidro",
                            "cota_cm",
                            "precipitacao_mm",
                            "motivo",
                        ]
                        if c in hits.columns
                    ]
                ],
                use_container_width=True,
                height=240,
            )


def render_geocalor() -> None:
    section_title("GeoCalor cardiorrespiratório", "Ondas de calor × internações e óbitos — lags 0–7")
    callout(
        "RR (risco relativo) > 1 sugere mais eventos após o calor, com defasagem em dias. É modelo exploratório — não é laudo individual.",
        "warn",
    )
    status_df = read_table("geocalor_status_modelagem_v11_12")
    df = read_table("geocalor_cardioresp_rr_municipal_v11_12")

    # Fallback para SQLite local quando a tabela ainda não estiver na base operacional.
    db = Path("data/output/sis_integrado.db")
    if (status_df.empty or df.empty) and db.exists():
        con = sqlite3.connect(db)
        try:
            if status_df.empty:
                status_df = pd.read_sql(
                    "SELECT * FROM geocalor_status_modelagem_v11_12",
                    con,
                )
        except Exception:
            pass
        try:
            if df.empty:
                df = pd.read_sql(
                    "SELECT * FROM geocalor_cardioresp_rr_municipal_v11_12",
                    con,
                )
        except Exception:
            pass
        con.close()

    _status_txt = None
    if not status_df.empty:
        for col in ("status_modelagem", "status", "geocalor_status"):
            if col in status_df.columns and status_df[col].notna().any():
                _status_txt = str(status_df[col].dropna().astype(str).iloc[0])
                break
    render_interpretacao(
        "geocalor",
        GUIDE_GEOCALOR,
        lambda: narrativa_geocalor(df, _status_txt),
    )

    if not status_df.empty:
        with st.expander("Status da modelagem", expanded=False):
            st.dataframe(status_df, use_container_width=True)

    if df.empty:
        st.warning(
            "Tabela GeoCalor ainda não gerada na base operacional. "
            "Rode `atualizar_monitoramento_saude_calor.py` (status) ou "
            "`calcular_geocalor_cardioresp_v11_12.py` com série diária; "
            "esta aba permanece disponível sem interromper o painel."
        )
        return

    if "status_modelagem" in df.columns:
        st_mod = df["status_modelagem"].astype(str)
        if st_mod.str.contains("insuficiente", case=False, na=False).all():
            st.info(
                "GeoCalor registrado na base, mas ainda sem série diária completa "
                "(ondas de calor × internações/óbitos). O status da modelagem está disponível acima. "
                "RR numérico exige `geocalor_model_input_diario`."
            )

    if "municipio" not in df.columns:
        st.warning("Tabela GeoCalor sem coluna município — verifique a modelagem.")
        st.dataframe(df.head(50), use_container_width=True)
        return

    municipios = sorted([x for x in df["municipio"].dropna().astype(str).unique() if x])
    if not municipios:
        st.info("Sem municípios na tabela GeoCalor nesta rodada.")
        return
    default_idx = municipios.index("Cuiabá") if "Cuiabá" in municipios else 0
    municipio = st.selectbox("Município", municipios, index=default_idx)

    if "rr" in df.columns and "cod_ibge" in df.columns and df["rr"].notna().any():
        map_src = df.copy()
        map_src["rr"] = pd.to_numeric(map_src["rr"], errors="coerce")
        if "lag" in map_src.columns:
            map_src = map_src.sort_values("lag").groupby("cod_ibge", as_index=False).tail(1)
        else:
            map_src = map_src.dropna(subset=["rr"]).drop_duplicates("cod_ibge", keep="first")
        map_df, geojson_mun, shp_status = prepare_map_dataframe(map_src)
        st.caption(shp_status)
        fig_map = make_choropleth_or_points(
            map_df, geojson_mun, color_col="rr",
            title="RR cardiorrespiratório por município",
            hover_cols=[c for c in ["municipio", "desfecho_label", "lag", "status_modelagem"] if c in map_df.columns],
        )
        if fig_map is not None:
            st.plotly_chart(fig_map, use_container_width=True)

    dm = df[df["municipio"].astype(str).eq(municipio)].copy()
    c1, c2, c3 = st.columns(3)
    c1.metric("Município", municipio)
    c2.metric("Desfechos", dm["desfecho_label"].nunique() if "desfecho_label" in dm.columns else 0)
    c3.metric("Lags", dm["lag"].nunique() if "lag" in dm.columns else 0)

    st.dataframe(dm, use_container_width=True)
    if "rr" in dm.columns and dm["rr"].notna().any():
        plot_df = dm.dropna(subset=["rr"]).copy()
        fig = px.line(plot_df, x="lag", y="rr", color="desfecho_label", markers=True, title=f"RR por defasagem — {municipio}")
        fig.add_hline(y=1.0, line_dash="dash")
        st.plotly_chart(fig, use_container_width=True)


def render_adaptasus(resumo_filtrado: pd.DataFrame | None = None) -> None:
    """Aba AdaptaSUS / Guia MS — alinhamento operacional CIEVS-MT."""
    section_title(
        "AdaptaSUS / Guia MS",
        "Seis riscos prioritários do Plano Setorial de Saúde + orientações do Guia de Mudanças Climáticas",
    )
    callout(
        "Esta aba operacionaliza o AdaptaSUS no CIEVS-MT. Não redefine metas federais. "
        "WASH usa Censo IBGE 2022 (estrutural). SAN permanece lacuna explícita — ausência ≠ risco zero.",
        "info",
    )
    base_resumo = resumo_filtrado if resumo_filtrado is not None and not resumo_filtrado.empty else read_table("resumo_municipal_atual")
    render_interpretacao(
        "adaptasus",
        GUIDE_ADAPTASUS,
        lambda: narrativa_adaptasus(base_resumo),
    )
    st.markdown(
        "- [Plano AdaptaSUS (PDF)](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/svsa/vigilancia-ambiental/plano-setorial-de-saude-adaptasus.pdf)  \n"
        "- [Guia de Mudanças Climáticas e Saúde](https://guiadoclima.saude.gov.br/)  \n"
        "- Matriz local: `docs/ALINHAMENTO_ADAPTASUS_MS.md` · `config/adaptasus_riscos.yaml`"
    )

    estado = read_table("adaptasus_risco_estado")
    mun = read_table("adaptasus_risco_municipal")
    resumo = resumo_filtrado if resumo_filtrado is not None else read_table("resumo_municipal_atual")

    if mun.empty and not resumo.empty and "indice_adaptacao_climatica" in resumo.columns:
        mun = resumo.copy()
    if estado.empty:
        st.warning("Tabela adaptasus_risco_estado ainda não gerada. Rode o enriquecimento operacional.")

    if not estado.empty:
        st.markdown("#### Cobertura dos 6 riscos prioritários (MT)")
        ccols = st.columns(min(3, len(estado)))
        for i, row in estado.iterrows():
            with ccols[int(i) % len(ccols)]:
                cov = row.get("cobertura_pct")
                media = row.get("score_medio")
                st.metric(
                    str(row.get("risco_nome") or row.get("risco_id")),
                    f"{float(media):.0f}" if pd.notna(media) else "—",
                    delta=f"cobertura {float(cov):.0f}%" if pd.notna(cov) else str(row.get("status_cobertura") or ""),
                )
        st.dataframe(
            estado[
                [c for c in [
                    "risco_id", "risco_nome", "status_cobertura", "cobertura_pct",
                    "municipios_com_dado", "score_medio", "score_max",
                ] if c in estado.columns]
            ],
            use_container_width=True,
            height=260,
        )
        lacunas = estado[estado["cobertura_pct"].fillna(0) < 5] if "cobertura_pct" in estado.columns else pd.DataFrame()
        if not lacunas.empty:
            callout(
                "Lacunas explícitas: "
                + ", ".join(lacunas["risco_nome"].astype(str).tolist())
                + ". SAN/SISVAN e demais fontes SES-MT ainda em Fase 2.",
                "warn",
            )

    # Bloco WASH estrutural
    wash_cols = [
        c for c in [
            "indice_deficit_wash", "risco_wash", "cobertura_rede_agua_pct",
            "deficit_rede_agua_pct", "cobertura_esgoto_rede_pct", "deficit_esgoto_inadequado_pct",
        ]
        if c in (resumo.columns if resumo is not None and not resumo.empty else [])
    ]
    if wash_cols:
        st.markdown("#### WASH — déficit estrutural (Censo IBGE 2022)")
        w1, w2, w3, w4 = st.columns(4)
        w1.metric(
            "Déficit WASH méd.",
            f"{pd.to_numeric(resumo['indice_deficit_wash'], errors='coerce').mean():.0f}"
            if "indice_deficit_wash" in resumo.columns else "—",
        )
        w2.metric(
            "Risco WASH máx.",
            f"{pd.to_numeric(resumo['risco_wash'], errors='coerce').max():.0f}"
            if "risco_wash" in resumo.columns else "—",
        )
        w3.metric(
            "Rede água méd. %",
            f"{pd.to_numeric(resumo['cobertura_rede_agua_pct'], errors='coerce').mean():.0f}"
            if "cobertura_rede_agua_pct" in resumo.columns else "—",
        )
        w4.metric(
            "Esgoto inadequado méd. %",
            f"{pd.to_numeric(resumo['deficit_esgoto_inadequado_pct'], errors='coerce').mean():.0f}"
            if "deficit_esgoto_inadequado_pct" in resumo.columns else "—",
        )
        top_wash = resumo.copy()
        sort_c = "risco_wash" if "risco_wash" in top_wash.columns else "indice_deficit_wash"
        if sort_c in top_wash.columns:
            top_wash = top_wash.sort_values(sort_c, ascending=False)
            st.dataframe(
                top_wash[
                    [c for c in [
                        "cod_ibge", "municipio", "regional_saude", sort_c,
                        "cobertura_rede_agua_pct", "deficit_rede_agua_pct",
                        "cobertura_esgoto_rede_pct", "deficit_esgoto_inadequado_pct",
                    ] if c in top_wash.columns]
                ].head(25),
                use_container_width=True,
                height=320,
            )

    if mun.empty:
        st.info("Sem scores municipais AdaptaSUS nesta rodada.")
        return

    view = mun.copy()
    if resumo_filtrado is not None and not resumo_filtrado.empty and "cod_ibge" in view.columns:
        ibges = set(resumo_filtrado["cod_ibge"].dropna().astype(str))
        view["cod_ibge"] = view["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        view = view[view["cod_ibge"].isin(ibges)]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Municípios", len(view))
    c2.metric(
        "Adaptação média",
        f"{float(pd.to_numeric(view.get('indice_adaptacao_climatica'), errors='coerce').mean()):.1f}"
        if "indice_adaptacao_climatica" in view.columns and pd.to_numeric(view["indice_adaptacao_climatica"], errors="coerce").notna().any()
        else "—",
    )
    c3.metric(
        "Adaptação máx.",
        f"{float(pd.to_numeric(view.get('indice_adaptacao_climatica'), errors='coerce').max()):.1f}"
        if "indice_adaptacao_climatica" in view.columns and pd.to_numeric(view["indice_adaptacao_climatica"], errors="coerce").notna().any()
        else "—",
    )
    if "risco_adaptasus_dominante_nome" in view.columns:
        top_dom = view["risco_adaptasus_dominante_nome"].astype(str).mode()
        c4.metric("Risco dominante modal", top_dom.iloc[0] if not top_dom.empty else "—")
    else:
        c4.metric("Risco dominante modal", "—")

    st.markdown("#### Mapa — índice de adaptação climática")
    map_src = view.copy()
    if "indice_adaptacao_climatica" in map_src.columns:
        map_src["indice_adaptacao_climatica"] = pd.to_numeric(map_src["indice_adaptacao_climatica"], errors="coerce")
        map_df, geojson_mun, shp_status = prepare_map_dataframe(map_src)
        st.caption(shp_status)
        fig_map = make_choropleth_or_points(
            map_df,
            geojson_mun,
            color_col="indice_adaptacao_climatica",
            title="Índice de adaptação climática (0–100)",
            hover_cols=[
                c for c in [
                    "risco_adaptasus_dominante_nome", "score_risco_dominante",
                    "orientacao_adaptasus", "completude_riscos_adaptasus_pct",
                ]
                if c in map_df.columns
            ],
        )
        if fig_map is not None:
            st.plotly_chart(fig_map, use_container_width=True)

    if "risco_adaptasus_dominante_nome" in view.columns:
        st.markdown("#### Mapa — risco AdaptaSUS dominante")
        map_dom = view.copy()
        map_df2, geojson2, _ = prepare_map_dataframe(map_dom)
        fig2 = make_choropleth_or_points(
            map_df2,
            geojson2,
            color_col="risco_adaptasus_dominante_nome",
            title="Risco prioritário dominante",
            hover_cols=[c for c in ["score_risco_dominante", "indice_adaptacao_climatica", "orientacao_adaptasus"] if c in map_df2.columns],
            categorical=True,
        )
        if fig2 is not None:
            st.plotly_chart(fig2, use_container_width=True)

    st.markdown("#### Ranking municipal (adaptação climática)")
    rank = view.sort_values("indice_adaptacao_climatica", ascending=False) if "indice_adaptacao_climatica" in view.columns else view
    st.dataframe(
        rank[
            [c for c in [
                "cod_ibge", "municipio", "regional_saude", "nivel",
                "indice_adaptacao_climatica", "risco_adaptasus_dominante_nome",
                "score_risco_dominante", "orientacao_adaptasus", "checklist_adaptasus",
                "risco_calor_vulneravel", "risco_ar_queimadas", "risco_vetorial_climatico",
                "pressao_rede_climatica",
            ] if c in rank.columns]
        ],
        use_container_width=True,
        height=420,
    )
