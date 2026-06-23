# -*- coding: utf-8 -*-
"""
Entrada padrão para Streamlit Community Cloud.
Prioriza o painel VIGIA completo validado e mantém fallback para versões anteriores.
"""

from pathlib import Path
import runpy
import streamlit as st

APPS = [
    "app_vigia_sistema_completo_validado.py",
    "app_v9.py",
    "app_v8.py",
    "app_v6.py",
]

for app in APPS:
    if Path(app).exists():
        runpy.run_path(app, run_name="__main__")
        break
else:
    st.error("Nenhum app do VIGIA/SIS Clima-Saúde MT encontrado.")
