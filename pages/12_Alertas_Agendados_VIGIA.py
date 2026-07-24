# -*- coding: utf-8 -*-
from pathlib import Path
import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parents[1]
PUBLIC = BASE / "data" / "public"

st.set_page_config(page_title="VIGIA Alertas Agendados", page_icon="📨", layout="wide")
st.title("📨 VIGIA — Alertas em 4 categorias")
st.caption(
    "1) Estado (SES/CIEVS) · 2) Regional (1 por ERS) · "
    "3) Municipal (1 por município) · 4) Cuiabá (capital)"
)

def load(name):
    p = PUBLIC / name
    if not p.exists():
        return pd.DataFrame()
    for enc in ["utf-8-sig", "utf-8", "latin1"]:
        try:
            return pd.read_csv(p, encoding=enc)
        except Exception:
            continue
    return pd.read_csv(p)

status = load("status_alertas_vigia.csv")
estado = load("alertas_estado_vigia.csv")
regionais = load("alertas_regionais_vigia.csv")
municipais = load("alertas_municipais_vigia.csv")
cuiaba = load("alerta_cuiaba_vigia.csv")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Estado", "OK" if not estado.empty else "Pendente")
c2.metric("Regionais (ERS)", len(regionais))
c3.metric("Municipais", len(municipais) if not municipais.empty else 0)
c4.metric("Cuiabá", "OK" if not cuiaba.empty else "Pendente")
if not status.empty and "email_enviado" in status.columns:
    enviados = status["email_enviado"].astype(str).str.lower().isin(["true", "1", "sim"]).sum()
    c5.metric("Status e-mail", int(enviados))
else:
    c5.metric("Status e-mail", "—")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["1) Estado SES/CIEVS", "2) Regionais (ERS)", "3) Municipais", "4) Cuiabá", "Status"]
)

with tab1:
    st.markdown("**Público:** gestores SES/MT e CIEVS — panorama estadual completo.")
    if estado.empty:
        st.info("alertas_estado_vigia.csv ainda não publicado em data/public.")
    else:
        st.dataframe(estado, use_container_width=True, hide_index=True)

with tab2:
    st.markdown("**Público:** cada um dos 16 Escritórios Regionais de Saúde, com municípios da jurisdição.")
    if regionais.empty:
        st.info("Nenhuma regional publicada ou arquivo ainda não gerado.")
    else:
        st.dataframe(regionais, use_container_width=True, hide_index=True)

with tab3:
    st.markdown("**Público:** gestão municipal — um alerta por município (Cuiabá fica na categoria 4).")
    if municipais.empty:
        st.info("alertas_municipais_vigia.csv ainda não publicado. Rode o ciclo completo.")
    else:
        st.dataframe(municipais, use_container_width=True, hide_index=True)

with tab4:
    st.markdown("**Público:** gestão de Cuiabá (capital) e ERS Cuiabá.")
    if cuiaba.empty:
        st.info("alerta_cuiaba_vigia.csv ainda não publicado em data/public.")
    else:
        st.dataframe(cuiaba, use_container_width=True, hide_index=True)

with tab5:
    if status.empty:
        st.info("status_alertas_vigia.csv ainda não publicado em data/public.")
    else:
        st.dataframe(status, use_container_width=True, hide_index=True)
