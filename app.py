from __future__ import annotations
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
from sisclima.core.db import read_table
from sisclima.pipeline import run_pipeline

st.set_page_config(page_title='SIS Integrado Clima-Saúde MT', page_icon='🌡️', layout='wide')

STAGE_COLORS = {'verde':'#2E7D32','amarela':'#F9A825','laranja':'#EF6C00','vermelha':'#C62828','roxa':'#6A1B9A'}


def load(name):
    try:
        return read_table(name)
    except Exception:
        return pd.DataFrame()


def metric_card(label, value, delta=None):
    st.metric(label, value if value is not None else '—', delta=delta)

st.title('🌡️ SIS Integrado Clima-Saúde MT')
st.caption('Monitoramento municipalizado: TITAN + SENTINELA + AESOP + SIVEP + LACEN + IndicaSUS + Copernicus/CAMS + INMET + Vigidesastres')

with st.sidebar:
    st.header('Operação')
    if st.button('▶ Rodar pipeline agora', use_container_width=True):
        with st.spinner('Executando ingestão em tempo real, cálculos e classificação municipal...'):
            res = run_pipeline(send_alerts=True)
        st.success(f'Pipeline executado. Nível estadual: {str(res["nivel"]).upper()}')
    st.divider()
    st.write('As tabelas são lidas do banco SQLite local. Para produção, configure `.env`, SQL Server, Copernicus/CAMS e shapefiles.')

resumo = load('resumo_situacao_atual')
municipal = load('resumo_municipal_atual')
if resumo.empty:
    st.warning('Nenhum resultado encontrado. Rode `python criar_dados_exemplo.py` e `python main_pipeline.py`.')
    st.stop()

row = resumo.tail(1).iloc[0].to_dict()
nivel = str(row.get('nivel','verde')).lower()
color = STAGE_COLORS.get(nivel, '#777')
municipio_critico = row.get('municipio', '—')

st.markdown(f"""
<div style="padding:18px;border-radius:14px;background:{color};color:white;margin-bottom:18px">
<h2 style="margin:0">NÍVEL OPERACIONAL ESTADUAL: {nivel.upper()}</h2>
<p style="margin:4px 0 0 0"><b>Município sentinela/mais crítico:</b> {municipio_critico}</p>
<p style="margin:4px 0 0 0">{row.get('motivo','Sem motivo registrado')}</p>
</div>
""", unsafe_allow_html=True)

c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: metric_card('Municípios monitorados', int(row.get('municipios_monitorados', len(municipal))) if not municipal.empty else '—')
with c2: metric_card('Municípios ≥ laranja', int(row.get('municipios_laranja_ou_mais', (municipal.get('score', pd.Series(dtype=float))>=2).sum() if not municipal.empty else 0)))
with c3: metric_card('Tmax', f"{row.get('tmax', np.nan):.1f} °C" if pd.notna(row.get('tmax')) else '—')
with c4: metric_card('UTCI proxy', f"{row.get('utci_proxy', np.nan):.1f}" if pd.notna(row.get('utci_proxy')) else '—')
with c5: metric_card('Pressão assistencial', f"{row.get('pressao_calor_pct', np.nan):.1f}%" if pd.notna(row.get('pressao_calor_pct')) else '—')
with c6: metric_card('Qualidade do ar', str(row.get('qualidade_ar_nivel','—')).upper() if pd.notna(row.get('qualidade_ar_nivel')) else '—')

abas = st.tabs(['Visão executiva','Municípios','Calor/TITAN','Qualidade do ar/Copernicus','Assistência/IndicaSUS/AESOP','SIVEP/LACEN/SINAN/SIM','SENTINELA','Operacional','Geografia','Alertas e auditoria'])

with abas[0]:
    st.subheader('Resumo estadual e municipal')
    st.dataframe(resumo.tail(5), use_container_width=True)
    if not municipal.empty:
        cols = [c for c in ['cod_ibge','municipio','nivel','score','tmax','utci_proxy','pressao_calor_pct','ocupacao_leitos_pct','qualidade_ar_nivel','pm25_ugm3','pm10_ugm3','o3_ugm3','autonomia_min_dias','falhas_infra_pct','indice_resiliencia','motivo'] if c in municipal.columns]
        st.dataframe(municipal[cols].sort_values(['score','municipio'], ascending=[False, True]), use_container_width=True)
    recs = load('recomendacoes_operacionais')
    if not recs.empty:
        st.subheader('Recomendações operacionais')
        st.dataframe(recs.tail(20), use_container_width=True)

with abas[1]:
    st.subheader('Painel municipalizado')
    if municipal.empty:
        st.info('Sem resumo municipal.')
    else:
        levels = ['verde','amarela','laranja','vermelha','roxa']
        cont = municipal['nivel'].value_counts().reindex(levels).fillna(0).reset_index()
        cont.columns = ['nivel','municipios']
        st.plotly_chart(px.bar(cont, x='nivel', y='municipios', title='Municípios por nível operacional'), use_container_width=True)
        cols = [c for c in ['municipio','nivel','score','tmax','utci_proxy','iq_ar_score','qualidade_ar_nivel','pressao_calor_pct','ocupacao_leitos_pct','autonomia_min_dias','falhas_infra_pct','indice_resiliencia'] if c in municipal.columns]
        st.dataframe(municipal[cols].sort_values(['score','municipio'], ascending=[False, True]), use_container_width=True)

with abas[2]:
    met = load('met_biometeo')
    if not met.empty:
        met['data'] = pd.to_datetime(met['data'], errors='coerce')
        municipios = sorted(met['municipio'].dropna().unique().tolist()) if 'municipio' in met.columns else []
        sel = st.multiselect('Municípios', municipios, default=municipios[:5]) if municipios else []
        plot = met[met['municipio'].isin(sel)] if sel and 'municipio' in met.columns else met
        fig = px.line(plot, x='data', y=[c for c in ['tmax','heat_index','utci_proxy'] if c in plot.columns], color='municipio' if 'municipio' in plot.columns else None, title='Série meteorológica e biometeorológica por município')
        st.plotly_chart(fig, use_container_width=True)
        if 'risco_cumulativo_3d' in plot.columns:
            st.plotly_chart(px.line(plot, x='data', y='risco_cumulativo_3d', color='municipio' if 'municipio' in plot.columns else None, title='Risco cumulativo de calor - 3 dias'), use_container_width=True)
        st.dataframe(plot.tail(100), use_container_width=True)
    else:
        st.info('Sem dados meteorológicos.')

with abas[3]:
    aq = load('qualidade_ar_municipal')
    if not aq.empty:
        aq['data'] = pd.to_datetime(aq['data'], errors='coerce')
        municipios = sorted(aq['municipio'].dropna().unique().tolist()) if 'municipio' in aq.columns else []
        sel = st.multiselect('Municípios - qualidade do ar', municipios, default=municipios[:5], key='aq_muns') if municipios else []
        plot = aq[aq['municipio'].isin(sel)] if sel and 'municipio' in aq.columns else aq
        pols = [c for c in ['pm25_ugm3','pm10_ugm3','o3_ugm3','no2_ugm3','co_mgm3','so2_ugm3'] if c in plot.columns]
        if pols:
            # Plotly Express falha em wide-form quando as colunas têm tipos diferentes.
            # Solução: converter poluentes para numérico e usar formato long.
            plot_long = plot.copy()
            for _c in pols:
                if _c in plot_long.columns:
                    plot_long[_c] = pd.to_numeric(plot_long[_c], errors='coerce')
            plot_long['data'] = pd.to_datetime(plot_long['data'], errors='coerce')
            id_vars = ['data']
            if 'municipio' in plot_long.columns:
                id_vars.append('municipio')
            plot_long = plot_long.melt(
                id_vars=id_vars,
                value_vars=[c for c in pols if c in plot_long.columns],
                var_name='poluente',
                value_name='valor'
            ).dropna(subset=['data', 'valor'])
            if plot_long.empty:
                st.info('Qualidade do ar disponível, mas sem valores numéricos válidos para plotagem.')
            else:
                if 'municipio' in plot_long.columns:
                    plot_long['serie'] = plot_long['municipio'].astype(str) + ' - ' + plot_long['poluente'].astype(str)
                    st.plotly_chart(
                        px.line(
                            plot_long,
                            x='data',
                            y='valor',
                            color='serie',
                            title='Qualidade do ar - Copernicus/CAMS ou CSV local'
                        ),
                        use_container_width=True
                    )
                else:
                    st.plotly_chart(
                        px.line(
                            plot_long,
                            x='data',
                            y='valor',
                            color='poluente',
                            title='Qualidade do ar - Copernicus/CAMS ou CSV local'
                        ),
                        use_container_width=True
                    )
        if {'lat','lon','iq_ar_score'}.issubset(aq.columns):
            last = aq.sort_values('data').groupby('municipio', as_index=False).tail(1)
            st.plotly_chart(px.scatter_mapbox(last, lat='lat', lon='lon', size='indice_qualidade_ar_operacional', color='qualidade_ar_nivel', hover_name='municipio', zoom=4.3, height=500, title='Último nível de qualidade do ar por município'), use_container_width=True)
        st.dataframe(plot.tail(200), use_container_width=True)
    else:
        st.info('Sem dados de qualidade do ar. Configure Copernicus/CAMS ou `data/input/qualidade_ar_copernicus.csv`.')

with abas[4]:
    press = load('epi_pressao_assistencial')
    cap = load('hospital_capacidade_agregada')
    c1,c2 = st.columns(2)
    with c1:
        if not press.empty:
            press['data'] = pd.to_datetime(press['data'], errors='coerce')
            st.plotly_chart(px.line(press, x='data', y='pressao_calor_pct', color='municipio' if 'municipio' in press.columns else None, title='Pressão assistencial por calor'), use_container_width=True)
            st.dataframe(press.tail(100), use_container_width=True)
    with c2:
        if not cap.empty:
            cap['data'] = pd.to_datetime(cap['data'], errors='coerce')
            st.plotly_chart(px.line(cap, x='data', y='ocupacao_pct', color='municipio' if 'municipio' in cap.columns else 'tipo_leito', line_dash='tipo_leito' if 'tipo_leito' in cap.columns and 'municipio' in cap.columns else None, title='Ocupação de leitos - IndicaSUS'), use_container_width=True)
            st.dataframe(cap.tail(100), use_container_width=True)

with abas[5]:
    s1,s2 = st.columns(2)
    with s1:
        sivep = load('epi_sivep_srag')
        if not sivep.empty:
            sivep['data'] = pd.to_datetime(sivep['data'], errors='coerce')
            st.plotly_chart(px.bar(sivep.tail(200), x='data', y='casos_srag', color='municipio' if 'municipio' in sivep.columns else None, title='SIVEP/SRAG - casos'), use_container_width=True)
            st.dataframe(sivep.tail(100), use_container_width=True)
        lacen = load('lab_lacen_gal')
        if not lacen.empty:
            lacen['data'] = pd.to_datetime(lacen['data'], errors='coerce')
            st.plotly_chart(px.line(lacen, x='data', y='positividade_pct', color='municipio' if 'municipio' in lacen.columns else None, title='LACEN/GAL - positividade'), use_container_width=True)
    with s2:
        sinan = load('epi_sinan_agravos')
        if not sinan.empty:
            st.dataframe(sinan.tail(100), use_container_width=True)
        sim = load('epi_sim_obitos_calor')
        if not sim.empty:
            sim['data'] = pd.to_datetime(sim['data'], errors='coerce')
            st.plotly_chart(px.bar(sim, x='data', y='obitos_calor_suspeitos', color='municipio' if 'municipio' in sim.columns else None, title='SIM - óbitos suspeitos por calor'), use_container_width=True)

with abas[6]:
    rum = load('sentinela_rumores_score')
    if not rum.empty:
        rum['data'] = pd.to_datetime(rum['data'], errors='coerce')
        st.plotly_chart(px.line(rum, x='data', y='score_sentinela', color='municipio' if 'municipio' in rum.columns else None, title='SENTINELA - sinais e rumores'), use_container_width=True)
        st.dataframe(rum.tail(100), use_container_width=True)
    else:
        st.info('Sem rumores/sinais captados.')

with abas[7]:
    stock = load('ops_estoque_autonomia')
    infra = load('ops_infraestrutura_resumo')
    busca = load('ops_busca_ativa')
    c1,c2,c3 = st.columns(3)
    with c1:
        st.subheader('Estoque')
        if not stock.empty: st.dataframe(stock.tail(100), use_container_width=True)
    with c2:
        st.subheader('Infraestrutura')
        if not infra.empty: st.dataframe(infra.tail(100), use_container_width=True)
    with c3:
        st.subheader('Busca ativa')
        if not busca.empty: st.dataframe(busca.tail(100), use_container_width=True)

with abas[8]:
    geo = load('geo_vulnerabilidade_municipal')
    if not geo.empty:
        st.subheader('Vulnerabilidade municipal/tabular')
        st.dataframe(geo, use_container_width=True)
        if {'lat','lon','indice_vulnerabilidade_calor'}.issubset(geo.columns):
            # Correção robusta do mapa de vulnerabilidade: após merges podem existir municipio_x/municipio_y.
            geo_plot = geo.copy()
            if 'municipio' not in geo_plot.columns:
                for _col_mun in ['municipio_x', 'municipio_y', 'municipio_base', 'municipio_indicasus']:
                    if _col_mun in geo_plot.columns:
                        geo_plot['municipio'] = geo_plot[_col_mun].astype(str)
                        break
            if 'municipio' not in geo_plot.columns:
                if 'cod_ibge' in geo_plot.columns:
                    geo_plot['municipio'] = geo_plot['cod_ibge'].astype(str)
                else:
                    geo_plot['municipio'] = 'Município não identificado'
            if 'indice_vulnerabilidade_calor' in geo_plot.columns:
                geo_plot['indice_vulnerabilidade_calor'] = pd.to_numeric(geo_plot['indice_vulnerabilidade_calor'], errors='coerce').fillna(0)
                geo_plot['tamanho_mapa_vulnerabilidade'] = geo_plot['indice_vulnerabilidade_calor'].clip(lower=0.1)
            else:
                geo_plot['indice_vulnerabilidade_calor'] = 0
                geo_plot['tamanho_mapa_vulnerabilidade'] = 1
            try:
                fig_vuln = px.scatter_map(
                    geo_plot,
                    lat='lat',
                    lon='lon',
                    size='tamanho_mapa_vulnerabilidade',
                    color='indice_vulnerabilidade_calor',
                    hover_name='municipio',
                    zoom=4.3,
                    height=500,
                    title='Vulnerabilidade ao calor'
                )
            except Exception:
                fig_vuln = px.scatter_mapbox(
                    geo_plot,
                    lat='lat',
                    lon='lon',
                    size='tamanho_mapa_vulnerabilidade',
                    color='indice_vulnerabilidade_calor',
                    hover_name='municipio',
                    zoom=4.3,
                    height=500,
                    title='Vulnerabilidade ao calor'
                )
            st.plotly_chart(fig_vuln, use_container_width=True)
    else:
        st.info('Sem base geográfica tabular. Para mapa municipal completo, configure SHAPEFILE_MT e cod_ibge.')

with abas[9]:
    alerts = load('alertas_enviados')
    audit = load('auditoria_indicadores')
    runs = load('pipeline_runs')
    st.subheader('Alertas enviados')
    st.dataframe(alerts.tail(20), use_container_width=True)
    st.subheader('Auditoria de indicadores')
    st.dataframe(audit.tail(100), use_container_width=True)
    st.subheader('Execuções do pipeline')
    st.dataframe(runs.tail(20), use_container_width=True)
