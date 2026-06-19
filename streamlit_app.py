# -*- coding: utf-8 -*-
"""
Entrada padrão para Streamlit Community Cloud.
Mantém compatibilidade com app_v9.py/app_v8.py/app_v6.py.
"""

from pathlib import Path
import runpy
import streamlit as st

for app in ["app_v9.py", "app_v8.py", "app_v6.py"]:
    if Path(app).exists():
        runpy.run_path(app, run_name="__main__")
        break
else:
    st.error("Nenhum app_v9.py, app_v8.py ou app_v6.py encontrado.")
