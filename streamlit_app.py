# -*- coding: utf-8 -*-
"""
Entrada padrão para Streamlit Community Cloud / local.
Painel unificado com navegação horizontal (sem menu lateral de páginas).

Importante: não use pasta `pages/` com apps extras — isso cria a barra esquerda
de multipáginas do Streamlit.
"""

from pathlib import Path
import os
import runpy
import streamlit as st

ROOT = Path(__file__).resolve().parent

# Carrega .env local sem sobrescrever DATABASE_URL já definida (Docker/Compose).
try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

# Secrets do Streamlit Cloud → ambiente (antes de importar o painel).
try:
    for key in st.secrets:
        val = st.secrets.get(key)
        if val is None or key in os.environ:
            continue
        if isinstance(val, (dict, list)):
            continue
        os.environ[str(key)] = str(val)
except Exception:
    pass

# Sem Postgres público: usa snapshot versionado para o Cloud não ficar vazio.
_seed = ROOT / "data" / "cloud" / "sis_cloud_seed.db"
if not os.getenv("DATABASE_URL") and _seed.exists() and _seed.stat().st_size > 0:
    os.environ["DATABASE_URL"] = f"sqlite:///{_seed.as_posix()}"

_logo = ROOT / "assets" / "ses-logo.jpg"
try:
    st.set_page_config(
        page_title="SES-MT · CIEVS · SIS Clima-Saúde",
        page_icon=str(_logo) if _logo.exists() else None,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
except Exception:
    pass

# Entrada única do painel institucional (não usar app.py legado — tema antigo).
try:
    for app in ["app_v9.py"]:
        if Path(app).exists():
            runpy.run_path(app, run_name="__main__")
            break
    else:
        st.error("app_v9.py não encontrado. O painel SES-MT usa exclusivamente app_v9.py.")
except ImportError as exc:
    # Streamlit Cloud reda a mensagem original; ecoamos nome do módulo sem secrets.
    missing = getattr(exc, "name", None) or "desconhecido"
    st.error("Falha de importação ao abrir o painel.")
    st.code(
        f"ImportError\n"
        f"módulo ausente/quebrado: {missing}\n"
        f"detalhe: {exc}\n"
        f"Dica: confira se a branch do Cloud é painel-v9 e reinicie o app em Manage app.",
        language="text",
    )
    raise
except Exception as exc:
    st.error(f"Erro ao iniciar o painel: {type(exc).__name__}")
    st.code(str(exc)[:2000], language="text")
    raise
