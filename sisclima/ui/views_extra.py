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

def render_arboviroses() -> None:
    section_title(
        "Arboviroses",
        f"Dengue, Zika, Chikungunya e correlatas · base {backend_name()}",
    )
    callout(
        "Casos em 7 dias mostram a pressão recente. Cruze com calor/chuva na Visão executiva — não projete a temporada só com este recorte.",
        "info",
    )
    arbo = read_table("epi_arboviroses")
    arbo_mun = read_table("epi_arboviroses_municipal")
    resumo = read_table("resumo_municipal_atual")

    if arbo.empty and arbo_mun.empty:
        st.error("Tabelas de arboviroses ainda não geradas. Rode o pipeline.")
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
        rank = rank.sort_values("casos_arbovirus_7d", ascending=False)
        st.dataframe(rank, use_container_width=True, height=320)
        st.plotly_chart(
            px.bar(
                rank.head(20),
                x="municipio",
                y="casos_arbovirus_7d",
                color="agravo_dominante" if "agravo_dominante" in rank.columns else None,
                title="Top municípios — arboviroses 7d",
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

    if daily.empty and weekly.empty:
        st.error("Tabelas SIVEP/MS ainda não geradas. Rode o pipeline.")
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
        st.dataframe(
            w.sort_values(["ano_epi", "semana_epi"], ascending=False) if "ano_epi" in w.columns else w,
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


def render_hidrologia() -> None:
    section_title("Riscos hidrológicos", f"Cemaden + ANA + precipitação · base {backend_name()}")
    callout(
        "Cemaden traz alertas oficiais; ANA traz telemetria de chuva/nível. Cobertura de estações é desigual — cruze com o nível operacional.",
        "info",
    )
    cemaden = read_table("cemaden_alertas")
    met = read_table("met_biometeo")
    resumo = read_table("resumo_municipal_atual")

    c1, c2, c3 = st.columns(3)
    c1.metric("Alertas Cemaden", len(cemaden))
    c2.metric("Municípios com alerta", int(cemaden["municipio"].nunique()) if not cemaden.empty and "municipio" in cemaden.columns else 0)
    if not met.empty and "precipitacao_mm" in met.columns:
        precip = pd.to_numeric(met["precipitacao_mm"], errors="coerce")
        c3.metric("Precipitação máx. (mm)", f"{float(precip.max()):.1f}" if precip.notna().any() else "—")
    else:
        c3.metric("Precipitação máx. (mm)", "—")

    ana_risco = read_table("ana_risco_municipal")
    ana_tel = read_table("ana_telemetria")
    ana_est = read_table("ana_estacoes")
    st.markdown("##### Telemetria ANA")
    if ana_risco.empty and ana_tel.empty:
        st.info("Sem dados ANA. Ative `USE_ANA=true` ou use CSV em `data/input/ana_*.csv`.")
    else:
        a1, a2, a3 = st.columns(3)
        a1.metric("Estações", len(ana_est) if not ana_est.empty else 0)
        a2.metric("Leituras", len(ana_tel) if not ana_tel.empty else 0)
        a3.metric("Municípios risco chuva", int(ana_risco["municipio"].nunique()) if not ana_risco.empty and "municipio" in ana_risco.columns else 0)
        if not ana_risco.empty:
            st.dataframe(ana_risco, use_container_width=True, height=240)
            map_df, geojson, status = prepare_map_dataframe(ana_risco)
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
        st.info("Sem `cemaden_alertas`. Ative `USE_CEMADEN=true` e rode o pipeline.")
    else:
        st.dataframe(cemaden, use_container_width=True, height=280)
        map_df, geojson, status = prepare_map_dataframe(cemaden)
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

    st.markdown("##### Precipitação (Open-Meteo)")
    if met.empty or "precipitacao_mm" not in met.columns:
        st.info("Sem coluna `precipitacao_mm`.")
    else:
        m = met.copy()
        m["data"] = pd.to_datetime(m["data"], errors="coerce")
        m["precipitacao_mm"] = pd.to_numeric(m["precipitacao_mm"], errors="coerce")
        latest = m.sort_values("data").groupby("municipio" if "municipio" in m.columns else "cod_ibge", as_index=False).tail(1)
        map_df, geojson, status = prepare_map_dataframe(latest)
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
        hits = resumo[resumo["motivo"].astype(str).str.contains("Cemaden|chuva|precip", case=False, na=False)]
        if not hits.empty:
            st.markdown("##### Motivos operacionais com menção a chuva/Cemaden")
            st.dataframe(
                hits[[c for c in ["cod_ibge", "municipio", "nivel", "score", "precipitacao_mm", "motivo"] if c in hits.columns]],
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

    if not status_df.empty:
        with st.expander("Status da modelagem", expanded=False):
            st.dataframe(status_df, use_container_width=True)

    if df.empty:
        st.warning("Tabela GeoCalor ainda não gerada na base operacional.")
        return
    if df.empty:
        st.warning("Tabela GeoCalor vazia.")
        return

    municipios = sorted([x for x in df["municipio"].dropna().astype(str).unique() if x])
    default_idx = municipios.index("Cuiabá") if "Cuiabá" in municipios else 0
    municipio = st.selectbox("Município", municipios, index=default_idx if municipios else 0)

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
        "Lacunas (WASH/SAN/frio) aparecem de forma explícita — não interprete ausência como risco zero.",
        "info",
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
                + ". Aguardando fonte SES-MT/DW (Fase 2).",
                "warn",
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
