from __future__ import annotations
from pathlib import Path
import sqlite3
from contextlib import contextmanager
import pandas as pd
from .config import APP_CONFIG, ROOT


def sqlite_path_from_url(url: str | None = None) -> Path:
    url = url or APP_CONFIG.database_url
    if url.startswith('sqlite:///'):
        p = url.replace('sqlite:///', '')
        path = ROOT / p if not Path(p).is_absolute() else Path(p)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return ROOT / 'data' / 'output' / 'sis_integrado.db'


def get_engine():
    """Retorna engine SQLAlchemy quando disponível. Para SQLite, o sistema usa sqlite3 diretamente."""
    url = APP_CONFIG.database_url
    if url.startswith('sqlite:///'):
        return None
    try:
        from sqlalchemy import create_engine
        return create_engine(url)
    except Exception as e:
        raise RuntimeError('Para bancos não SQLite, instale SQLAlchemy e o driver correspondente.') from e


@contextmanager
def sqlite_conn():
    path = sqlite_path_from_url()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def write_df(df: pd.DataFrame, table: str, if_exists: str = 'replace') -> None:
    url = APP_CONFIG.database_url
    if df is None:
        df = pd.DataFrame()
    # pandas/sqlite não cria tabela sem colunas. Mantém uma tabela vazia auditável.
    if df.empty and len(df.columns) == 0:
        df = pd.DataFrame(columns=['_empty'])
    if url.startswith('sqlite:///'):
        with sqlite_conn() as conn:
            df.to_sql(table, conn, if_exists=if_exists, index=False)
    else:
        engine = get_engine()
        df.to_sql(table, engine, if_exists=if_exists, index=False)


def read_table(table: str) -> pd.DataFrame:
    url = APP_CONFIG.database_url
    try:
        if url.startswith('sqlite:///'):
            with sqlite_conn() as conn:
                return pd.read_sql_query(f'SELECT * FROM {table}', conn)
        engine = get_engine()
        return pd.read_sql_table(table, engine)
    except Exception:
        return pd.DataFrame()


def read_sql(query: str) -> pd.DataFrame:
    url = APP_CONFIG.database_url
    if url.startswith('sqlite:///'):
        with sqlite_conn() as conn:
            return pd.read_sql_query(query, conn)
    try:
        from sqlalchemy import text
    except Exception as e:
        raise RuntimeError('Para bancos não SQLite, instale SQLAlchemy.') from e
    engine = get_engine()
    return pd.read_sql_query(text(query), engine)

DDL_BASE = [
"""
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    status TEXT,
    message TEXT
)
""",
"""
CREATE TABLE IF NOT EXISTS nivel_atual (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data_referencia TEXT,
    nivel TEXT,
    score INTEGER,
    motivo TEXT,
    updated_at TEXT
)
""",
"""
CREATE TABLE IF NOT EXISTS alertas_enviados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    nivel_anterior TEXT,
    nivel_novo TEXT,
    titulo TEXT,
    mensagem TEXT,
    canais TEXT,
    status TEXT
)
""",
"""
CREATE TABLE IF NOT EXISTS auditoria_indicadores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_referencia TEXT,
    indicador TEXT,
    valor REAL,
    nivel TEXT,
    fonte TEXT,
    created_at TEXT
)
""",
"""
CREATE TABLE IF NOT EXISTS recomendacoes_operacionais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_referencia TEXT,
    nivel TEXT,
    eixo TEXT,
    recomendacao TEXT,
    created_at TEXT
)
"""
]


def init_db() -> None:
    with sqlite_conn() as conn:
        for ddl in DDL_BASE:
            conn.execute(ddl)
