# -*- coding: utf-8 -*-
import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="GeoCalor Cardiorrespiratório", layout="wide")

DB = Path("data/output/sis_integrado.db")

st.title("GeoCalor Cardiorrespiratório")
st.caption("Ondas de calor × internações e óbitos cardiovasculares/respiratórios — lags 0–7")

st.markdown("""
Esta página incorpora ao SIS Clima-Saúde MT uma camada metodológica inspirada no Projeto GeoCalor.
Quando houver série diária histórica válida, apresenta estimativas de RR por defasagem.
Quando os dados diários não estiverem disponíveis, apresenta status de insuficiência e mantém a nota metodológica.
""")

if not DB.exists():
    st.error(f"Banco não encontrado: {DB}")
    st.stop()

con = sqlite3.connect(DB)

def table_exists(name):
    q = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table' AND name=?", con, params=(name,))
    return not q.empty

if table_exists("geocalor_status_modelagem_v11_12"):
    st.subheader("Status da modelagem")
    st.dataframe(pd.read_sql("SELECT * FROM geocalor_status_modelagem_v11_12", con), use_container_width=True)

if not table_exists("geocalor_cardioresp_rr_municipal_v11_12"):
    st.warning("Tabela geocalor_cardioresp_rr_municipal_v11_12 ainda não foi gerada. Rode calcular_geocalor_cardioresp_v11_12.py.")
    st.stop()

df = pd.read_sql("SELECT * FROM geocalor_cardioresp_rr_municipal_v11_12", con)
con.close()

if df.empty:
    st.warning("Tabela GeoCalor cardiorrespiratória vazia.")
    st.stop()

municipios = sorted([x for x in df["municipio"].dropna().astype(str).unique() if x])
default_idx = municipios.index("Cuiabá") if "Cuiabá" in municipios else 0
municipio = st.selectbox("Município", municipios, index=default_idx if municipios else None)

dm = df[df["municipio"].astype(str).eq(municipio)].copy()

c1, c2, c3 = st.columns(3)
c1.metric("Município", municipio)
c2.metric("Desfechos", dm["desfecho_label"].nunique() if "desfecho_label" in dm.columns else 0)
c3.metric("Lags", dm["lag"].nunique() if "lag" in dm.columns else 0)

if "status_modelagem" in dm.columns and dm["status_modelagem"].astype(str).str.contains("insuficiente", case=False, na=False).any():
    st.warning("Dados diários insuficientes para RR municipal validado nesta execução.")
    detalhe = dm["detalhe"].dropna().astype(str).iloc[0] if dm["detalhe"].notna().any() else ""
    st.info(detalhe)

st.subheader("Resultados por lag")
st.dataframe(dm, use_container_width=True)

if "rr" in dm.columns and dm["rr"].notna().any():
    plot_df = dm.dropna(subset=["rr"]).copy()
    fig = px.line(plot_df, x="lag", y="rr", color="desfecho_label", markers=True, title=f"RR por defasagem — {municipio}")
    fig.add_hline(y=1.0, line_dash="dash")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem RR numérico para gráfico. Isso é esperado quando faltam séries diárias históricas.")

st.subheader("Nota técnica metodológica")
st.markdown("""
**Projeto GeoCalor | LAGAS/UnB, Fiocruz/OCS, LASA-UFRJ & LMI-Sentinela**

O RR de internações e óbitos associados às ondas de calor é estimado considerando defasagens de 0 a 7 dias.
A definição de onda de calor utiliza o **Excess Heat Factor (EHF)**, com três ou mais dias consecutivos com EHF > 0.
O modelo de referência utiliza Regressão Binomial Negativa com estrutura de defasagem distribuída, ajustando tendência temporal, sazonalidade, umidade, amplitude térmica e dia da semana.

No SIS Clima-Saúde MT, esta camada é apresentada como componente epidemiológico complementar.
Os níveis municipais operacionais não devem ser interpretados automaticamente como RR local sem modelagem municipal específica validada.
""")
