# -*- coding: utf-8 -*-
"""
Entrada padrão para Streamlit Community Cloud / local.
Painel unificado com navegação horizontal (sem menu lateral de páginas).

Importante: não use pasta `pages/` com apps extras — isso cria a barra esquerda
de multipáginas do Streamlit.
"""

from pathlib import Path
import runpy
import streamlit as st

# Carrega .env local sem sobrescrever DATABASE_URL já definida (Docker/Compose).
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except Exception:
    pass

try:
    st.set_page_config(
        page_title="SIS Integrado Clima-Saúde MT",
        page_icon="🌡️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
except Exception:
    pass

for app in ["app_v9.py", "app_v8.py", "app_v6.py"]:
    if Path(app).exists():
        runpy.run_path(app, run_name="__main__")
        break
else:
    st.error("Nenhum app_v9.py, app_v8.py ou app_v6.py encontrado.")
