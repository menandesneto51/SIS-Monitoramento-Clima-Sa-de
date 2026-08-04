# -*- coding: utf-8 -*-
"""Camada única de banco operacional (SQLite local ou PostgreSQL/Docker)."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from .config import APP_CONFIG, ROOT

_ENGINE: Engine | None = None


def is_sqlite(url: str | None = None) -> bool:
    u = (url or APP_CONFIG.database_url or "").strip().lower()
    return u.startswith("sqlite:")


def is_postgres(url: str | None = None) -> bool:
    u = (url or APP_CONFIG.database_url or "").strip().lower()
    return u.startswith("postgresql") or u.startswith("postgres:")


def sqlite_path_from_url(url: str | None = None) -> Path:
    url = url or APP_CONFIG.database_url
    if url.startswith("sqlite:///"):
        p = url.replace("sqlite:///", "", 1)
        path = ROOT / p if not Path(p).is_absolute() else Path(p)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    return ROOT / "data" / "output" / "sis_integrado.db"


def _normalize_url(url: str | None = None) -> str:
    url = (url or APP_CONFIG.database_url or "").strip()
    if not url:
        path = ROOT / "data" / "output" / "sis_integrado.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.as_posix()}"
    if url.startswith("sqlite:///"):
        path = sqlite_path_from_url(url)
        return f"sqlite:///{path.as_posix()}"
    # Aceita postgres:// e normaliza para o driver psycopg2.
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://") :]
    elif url.startswith("postgresql://") and "+psycopg2" not in url and "+psycopg" not in url:
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def _sqlite_fallback_url() -> str:
    """Prefere a base SQLite com dados mais recentes (seed Cloud vs operacional local)."""
    cloud_seed = ROOT / "data" / "cloud" / "sis_cloud_seed.db"
    local_ops = ROOT / "data" / "output" / "sis_integrado.db"
    local_ops.parent.mkdir(parents=True, exist_ok=True)

    def _ts(val: object) -> float | None:
        t = pd.to_datetime(val, errors="coerce")
        if pd.isna(t):
            return None
        return float(pd.Timestamp(t).timestamp())

    def _freshness(path: Path) -> float:
        if not path.exists() or path.stat().st_size <= 0:
            return -1.0
        try:
            import sqlite3

            with sqlite3.connect(path) as con:
                for sql in (
                    "SELECT MAX(data_processamento) FROM alerta_integrado_sis_titan",
                    "SELECT MAX(data_referencia) FROM resumo_municipal_atual",
                ):
                    try:
                        row = con.execute(sql).fetchone()
                        if row and row[0]:
                            ts = _ts(row[0])
                            if ts is not None:
                                return ts
                    except Exception:
                        continue
        except Exception:
            pass
        return float(path.stat().st_mtime)

    c_score = _freshness(cloud_seed)
    l_score = _freshness(local_ops)
    if l_score > c_score:
        return f"sqlite:///{local_ops.as_posix()}"
    if c_score >= 0:
        return f"sqlite:///{cloud_seed.as_posix()}"
    return f"sqlite:///{local_ops.as_posix()}"


def get_engine(force_refresh: bool = False) -> Engine:
    global _ENGINE
    if _ENGINE is not None and not force_refresh:
        return _ENGINE
    url = _normalize_url()
    kwargs: dict[str, Any] = {"future": True, "pool_pre_ping": True}
    if is_sqlite(url):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    # Se Postgres/Docker estiver fora, usa o SQLite local para o painel não ficar vazio.
    if is_postgres(url):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            try:
                engine.dispose()
            except Exception:
                pass
            url = _sqlite_fallback_url()
            kwargs = {"future": True, "pool_pre_ping": True, "connect_args": {"check_same_thread": False}}
            engine = create_engine(url, **kwargs)
    _ENGINE = engine
    return _ENGINE


def reset_engine() -> None:
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None


@contextmanager
def db_conn() -> Iterator[Connection]:
    engine = get_engine()
    with engine.begin() as conn:
        yield conn


# Compatibilidade com código legado.
@contextmanager
def sqlite_conn() -> Iterator[Connection]:
    with db_conn() as conn:
        yield conn


def execute(conn: Connection, sql: str, params: dict | list | tuple | None = None):
    if params is None:
        return conn.execute(text(sql))
    if isinstance(params, (list, tuple)):
        # Converte '?' estilo sqlite para binds nomeados :p0, :p1...
        bind: dict[str, Any] = {}
        out = []
        i = 0
        for ch in sql:
            if ch == "?":
                key = f"p{i}"
                out.append(f":{key}")
                bind[key] = params[i]
                i += 1
            else:
                out.append(ch)
        return conn.execute(text("".join(out)), bind)
    return conn.execute(text(sql), params)


def fetchone(conn: Connection, sql: str, params: dict | list | tuple | None = None):
    result = execute(conn, sql, params)
    row = result.mappings().first()
    return row


def fetchall(conn: Connection, sql: str, params: dict | list | tuple | None = None):
    result = execute(conn, sql, params)
    return list(result.mappings().all())


def table_exists(table: str) -> bool:
    try:
        return inspect(get_engine()).has_table(table)
    except Exception:
        return False


def write_df(df: pd.DataFrame, table: str, if_exists: str = "replace") -> None:
    if df is None:
        df = pd.DataFrame()
    if df.empty and len(df.columns) == 0:
        df = pd.DataFrame(columns=["_empty"])
    engine = get_engine()
    df.to_sql(table, engine, if_exists=if_exists, index=False, method="multi", chunksize=2000)


def read_table(table: str) -> pd.DataFrame:
    try:
        if not table_exists(table):
            return pd.DataFrame()
        return pd.read_sql_table(table, get_engine())
    except Exception:
        try:
            return pd.read_sql_query(text(f'SELECT * FROM "{table}"'), get_engine())
        except Exception:
            return pd.DataFrame()


def read_sql(query: str, params: dict | None = None) -> pd.DataFrame:
    try:
        return pd.read_sql_query(text(query), get_engine(), params=params or {})
    except Exception:
        return pd.DataFrame()


def table_count(table: str) -> int:
    if not table_exists(table):
        return 0
    try:
        df = pd.read_sql_query(text(f'SELECT COUNT(*) AS n FROM "{table}"'), get_engine())
        return int(df.iloc[0]["n"])
    except Exception:
        return 0


DDL_SQLITE = [
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
""",
    """
CREATE TABLE IF NOT EXISTS nivel_historico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_referencia TEXT,
    nivel TEXT,
    score INTEGER,
    motivo TEXT,
    nivel_anterior TEXT,
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS alertas_validacao_humana (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    data_referencia TEXT,
    nivel TEXT,
    usuario TEXT,
    decisao TEXT,
    checklist_json TEXT,
    observacao TEXT
)
""",
]

DDL_POSTGRES = [
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
    id SERIAL PRIMARY KEY,
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
    id SERIAL PRIMARY KEY,
    data_referencia TEXT,
    indicador TEXT,
    valor DOUBLE PRECISION,
    nivel TEXT,
    fonte TEXT,
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS recomendacoes_operacionais (
    id SERIAL PRIMARY KEY,
    data_referencia TEXT,
    nivel TEXT,
    eixo TEXT,
    recomendacao TEXT,
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS nivel_historico (
    id SERIAL PRIMARY KEY,
    data_referencia TEXT,
    nivel TEXT,
    score INTEGER,
    motivo TEXT,
    nivel_anterior TEXT,
    created_at TEXT
)
""",
    """
CREATE TABLE IF NOT EXISTS alertas_validacao_humana (
    id SERIAL PRIMARY KEY,
    created_at TEXT,
    data_referencia TEXT,
    nivel TEXT,
    usuario TEXT,
    decisao TEXT,
    checklist_json TEXT,
    observacao TEXT
)
""",
]


def init_db() -> None:
    ddl = DDL_POSTGRES if is_postgres() else DDL_SQLITE
    with db_conn() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


def backend_name() -> str:
    """Nome do backend efetivamente conectado (após eventual fallback)."""
    try:
        url = str(get_engine().url).lower()
    except Exception:
        url = (APP_CONFIG.database_url or "").strip().lower()
    if url.startswith("postgresql") or url.startswith("postgres"):
        return "postgresql"
    if url.startswith("sqlite"):
        return "sqlite"
    return "outro"
