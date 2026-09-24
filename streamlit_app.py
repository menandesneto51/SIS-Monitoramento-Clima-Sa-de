# -*- coding: utf-8 -*-
"""
Entrada padrão para Streamlit Community Cloud / local.
Painel unificado com navegação horizontal (sem menu lateral de páginas).
Painel unificado com navegação horizontal (sem menu lateral de páginas).

Importante: não use pasta `pages/` com apps extras — isso cria a barra esquerda
de multipáginas do Streamlit.
"""

from pathlib import Path
import os
import runpy
import sys
import streamlit as st

from sisclima.branding import ARARAS_SYMBOL_PATH

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Streamlit (Windows) pode relançar o script com sys._base_executable (Python do sistema),
# perdendo o site-packages do venv → ImportError falso em views_extra.
_venv_home = os.environ.get("VIRTUAL_ENV") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "araras-mt-venv")
_venv_sp = Path(_venv_home) / "Lib" / "site-packages"
if _venv_sp.is_dir():
    os.environ.setdefault("VIRTUAL_ENV", _venv_home)
    if str(_venv_sp) not in sys.path:
        sys.path.insert(0, str(_venv_sp))
    _pp = os.environ.get("PYTHONPATH", "")
    _parts = [str(ROOT), str(_venv_sp)] + ([_pp] if _pp else [])
    # Dedup preservando ordem
    _seen: set[str] = set()
    _ordered: list[str] = []
    for _p in _parts:
        if _p and _p not in _seen:
            _seen.add(_p)
            _ordered.append(_p)
    os.environ["PYTHONPATH"] = os.pathsep.join(_ordered)

# Evita painel subir com Python do sistema SEM site-packages do venv — sintoma típico:
# ImportError: cannot import name 'render_cenario_epidemiologico' from views_extra
_exe = Path(sys.executable).resolve().as_posix().lower()
_venv_ok = ("araras-mt-venv" in _exe) or ("/.venv/" in _exe) or ("/venv/" in _exe)
_has_pandas = False
try:
    import pandas  # noqa: F401

    _has_pandas = True
except Exception:
    _has_pandas = False
if os.name == "nt" and (not _has_pandas):
    try:
        st.set_page_config(page_title="ARARAS MT · ambiente Python incompleto", layout="wide")
    except Exception:
        pass
    st.error("Ambiente Python sem dependências do ARARAS (ex.: pandas).")
    st.markdown(
        "O erro `cannot import name 'render_cenario_epidemiologico'` costuma ser **efeito colateral**: "
        "o módulo `views_extra` não termina de carregar neste interpretador."
    )
    st.code(
        f"sys.executable = {sys.executable}\n"
        f"VIRTUAL_ENV = {os.environ.get('VIRTUAL_ENV')}\n"
        f"venv site-packages = {_venv_sp} (exists={_venv_sp.is_dir()})\n\n"
        "Inicie com:\n"
        "  .\\scripts\\start_painel.ps1\n"
        "ou:\n"
        "  %LOCALAPPDATA%\\araras-mt-venv\\Scripts\\python.exe -m streamlit run streamlit_app.py --server.port 8501",
        language="text",
    )
    st.stop()

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

_logo = ARARAS_SYMBOL_PATH
try:
    st.set_page_config(
        page_title="ARARAS MT · Clima, ambiente e saúde em uma só visão",
        page_icon=str(_logo) if _logo.exists() else None,
        layout="wide",
        initial_sidebar_state="expanded",
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
        st.error("app_v9.py não encontrado. O painel ARARAS MT usa exclusivamente app_v9.py.")
except ImportError as exc:
    # Streamlit Cloud reda a mensagem original; ecoamos nome do módulo sem secrets.
    missing = getattr(exc, "name", None) or "desconhecido"
    st.error("Falha de importação ao abrir o painel.")
    st.code(
        f"ImportError\n"
        f"módulo ausente/quebrado: {missing}\n"
        f"detalhe: {exc}\n"
        f"Dica: confira se a branch do Cloud é araras-mt (produção) e reinicie o app em Manage app.",
        language="text",
    )
    raise
except Exception as exc:
    st.error(f"Erro ao iniciar o painel: {type(exc).__name__}")
    st.code(str(exc)[:2000], language="text")
    raise
