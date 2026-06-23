# -*- coding: utf-8 -*-
from pathlib import Path
import pandas as pd
import streamlit as st

BASE = Path(__file__).resolve().parents[1]
PUBLIC = BASE / "data" / "public"

st.set_page_config(page_title="VIGIA Alertas Agendados", page_icon="📨", layout="wide")
st.title("📨 VIGIA — Alertas Agendados")
st.caption("Estado, regionais com municípios em alerta e alerta focado em Cuiabá.")

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
cuiaba = load("alerta_cuiaba_vigia.csv")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Estado", "OK" if not estado.empty else "Pendente")
c2.metric("Regionais", len(regionais))
c3.metric("Cuiabá", "OK" if not cuiaba.empty else "Pendente")
if not status.empty and "email_enviado" in status.columns:
    enviados = status["email_enviado"].astype(str).str.lower().isin(["true", "1", "sim"]).sum()
    c4.metric("E-mails enviados", int(enviados))
else:
    c4.metric("E-mails enviados", "—")

tab1, tab2, tab3, tab4 = st.tabs(["Estado", "Regionais", "Cuiabá", "Status geral"])

with tab1:
    if estado.empty:
        st.info("alertas_estado_vigia.csv ainda não publicado em data/public.")
    else:
        st.dataframe(estado, use_container_width=True, hide_index=True)

with tab2:
    if regionais.empty:
        st.info("Nenhuma regional com município em alerta ou arquivo ainda não publicado.")
    else:
        st.dataframe(regionais, use_container_width=True, hide_index=True)

with tab3:
    if cuiaba.empty:
        st.info("alerta_cuiaba_vigia.csv ainda não publicado em data/public.")
    else:
        st.dataframe(cuiaba, use_container_width=True, hide_index=True)

with tab4:
    if status.empty:
        st.info("status_alertas_vigia.csv ainda não publicado em data/public.")
    else:
        st.dataframe(status, use_container_width=True, hide_index=True)
