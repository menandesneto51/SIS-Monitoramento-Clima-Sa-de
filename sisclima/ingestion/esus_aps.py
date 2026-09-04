# -*- coding: utf-8 -*-
"""
Leitura do Centralizador e-SUS APS (Postgres SES).

Fonte externa, somente leitura. NÃO reutiliza DATABASE_URL / get_engine()
do Postgres operacional do ARARAS.

Credenciais: ESUS_APS_HOST / PORT / DATABASE / USER / PASSWORD (ver .env).
"""
from __future__ import annotations

import re
import socket
from typing import Any, Callable

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL

from sisclima.core.config import as_bool, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

_ENGINE: Engine | None = None

_WRITE_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|COPY|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"VACUUM|CLUSTER|REINDEX|CALL|DO|LOCK|NOTIFY|LISTEN)\b",
    re.IGNORECASE,
)
_READ_START = re.compile(r"^\s*(SELECT|WITH|SHOW|EXPLAIN)\b", re.IGNORECASE | re.DOTALL)

PII_COLUMN_TOKENS: tuple[str, ...] = (
    "cpf",
    "cns",
    "nu_cpf",
    "nu_cns",
    "no_cidadao",
    "nome",
    "no_mae",
    "no_pai",
    "mae",
    "pai",
    "endereco",
    "endereço",
    "logradouro",
    "bairro",
    "complemento",
    "cep",
    "email",
    "telefone",
    "celular",
    "fone",
    "rg",
    "nis",
    "cartao_sus",
    "dt_nascimento",
    "data_nascimento",
)

DATE_COLUMN_CANDIDATES: tuple[str, ...] = (
    "dt_registro",
    "dt_atendimento",
    "dt_ficha",
    "dt_inicial",
    "dt_final",
    "co_dim_tempo",
    "nu_ano",
    "nu_mes",
)

RELEVANT_TABLE_HINTS: tuple[str, ...] = (
    "atendimento_individual",
    "atendimento_proced",
    "procedimento",
    "cad_individual",
    "visita_domiciliar",
    "dim_municipio",
    "dim_unidade",
    "dim_tempo",
    "dim_cid",
)

INDICATOR_HINTS: tuple[dict[str, str], ...] = (
    {
        "id": "atendimento_individual",
        "hint": "atendimento_individual",
        "uso": "Volume APS 7d/28d por município; CID respiratório, desidratação, calor.",
    },
    {
        "id": "procedimentos",
        "hint": "procedimento",
        "uso": "Nebulização SIGTAP 0301100039 / 0301100047 (bloco El Niño pendente).",
    },
    {
        "id": "cadastro_individual",
        "hint": "cad_individual",
        "uso": "Proxy de vulneráveis (idoso, gestante, hipertenso, diabético, asma).",
    },
    {
        "id": "visita_acs",
        "hint": "visita_domiciliar",
        "uso": "Intensidade de território em municípios vermelho/roxo ARARAS.",
    },
    {
        "id": "dim_municipio",
        "hint": "dim_municipio",
        "uso": "Cruzar IBGE-7 dígitos com a base territorial do painel.",
    },
)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def use_esus_aps() -> bool:
    return as_bool(env("USE_ESUS_APS", "false"), False)


def esus_aps_config() -> dict[str, Any]:
    """Lê só ESUS_APS_* (aliases). Nunca cai em DATABASE_URL."""
    host = (env("ESUS_APS_HOST") or "").strip()
    port_raw = (env("ESUS_APS_PORT", "5432") or "5432").strip()
    database = (env("ESUS_APS_DATABASE", "esus2") or "esus2").strip()
    user = (env("ESUS_APS_USER") or "").strip()
    password = env("ESUS_APS_PASSWORD") or ""
    sslmode = (env("ESUS_APS_SSLMODE", "disable") or "disable").strip()
    schema = (env("ESUS_APS_SCHEMA", "public") or "public").strip()
    connect_timeout = int(env("ESUS_APS_CONNECT_TIMEOUT", "15") or 15)
    query_timeout = int(env("ESUS_APS_QUERY_TIMEOUT_SECONDS", "120") or 120)
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"ESUS_APS_PORT inválida: {port_raw}") from exc
    if not host:
        raise ValueError("ESUS_APS_HOST não configurado no .env")
    return {
        "host": host,
        "port": port,
        "database": database,
        "user": user,
        "password": password,
        "sslmode": sslmode,
        "schema": schema,
        "connect_timeout": connect_timeout,
        "query_timeout_seconds": query_timeout,
    }


def credentials_ready(cfg: dict[str, Any] | None = None) -> bool:
    data = cfg or esus_aps_config()
    return bool(data.get("host") and data.get("database") and data.get("user") and data.get("password"))


def build_esus_aps_url(cfg: dict[str, Any] | None = None, *, hide_password: bool = False) -> str:
    data = cfg or esus_aps_config()
    password = data.get("password") or ""
    url = URL.create(
        "postgresql+psycopg2",
        username=data.get("user") or None,
        password=password if password else None,
        host=data["host"],
        port=int(data["port"]),
        database=data["database"],
        query={
            "sslmode": str(data.get("sslmode") or "disable"),
            "connect_timeout": str(int(data.get("connect_timeout") or 15)),
        },
    )
    return url.render_as_string(hide_password=hide_password)


def reset_esus_engine() -> None:
    global _ENGINE
    if _ENGINE is not None:
        _ENGINE.dispose()
    _ENGINE = None


def get_esus_engine(cfg: dict[str, Any] | None = None) -> Engine:
    """Engine própria do Centralizador — isolada de sisclima.core.db.get_engine()."""
    global _ENGINE
    if _ENGINE is not None and cfg is None:
        return _ENGINE
    data = cfg or esus_aps_config()
    if not credentials_ready(data):
        raise RuntimeError("Credenciais ESUS_APS_USER / ESUS_APS_PASSWORD incompletas")
    timeout = int(data.get("connect_timeout") or 15)
    engine = create_engine(
        build_esus_aps_url(data),
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "connect_timeout": timeout,
            "options": "-c default_transaction_read_only=on",
        },
    )
    if cfg is None:
        _ENGINE = engine
    return engine


def assert_read_only_sql(sql: str) -> None:
    stripped = (sql or "").strip()
    if not stripped:
        raise ValueError("SQL vazio")
    lines = [
        ln
        for ln in stripped.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    ]
    body = "\n".join(lines).strip()
    if not _READ_START.match(body):
        raise ValueError("SQL de escrita bloqueado no Centralizador e-SUS (somente leitura)")
    if ";" in body.rstrip().rstrip(";"):
        raise ValueError("Múltiplos comandos SQL bloqueados no Centralizador e-SUS")


def read_esus_sql(
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    engine: Engine | None = None,
    query_timeout_seconds: int | None = None,
) -> pd.DataFrame:
    assert_read_only_sql(sql)
    eng = engine or get_esus_engine()
    timeout = query_timeout_seconds
    if timeout is None:
        try:
            timeout = int(esus_aps_config().get("query_timeout_seconds") or 120)
        except ValueError:
            timeout = 120
    timeout_ms = int(timeout) * 1000
    with eng.connect() as conn:
        conn.execute(text("SET default_transaction_read_only = on"))
        conn.execute(text(f"SET statement_timeout = {timeout_ms}"))
        return pd.read_sql(text(sql), conn, params=params or {})


def probe_tcp_ports(
    host: str,
    ports: list[int],
    *,
    timeout: float = 3.0,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    open_port: int | None = None
    for port in ports:
        ok = False
        error = ""
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                ok = True
                open_port = int(port)
        except OSError as exc:
            error = str(exc)
        attempts.append({"port": int(port), "ok": ok, "error": error})
        if ok:
            break
    return {"host": host, "open_port": open_port, "attempts": attempts}


def classify_esus_layout(table_names: list[str]) -> dict[str, Any]:
    names = [str(n).strip().lower() for n in table_names if str(n).strip()]
    uniq = sorted(set(names))
    facts = [n for n in uniq if n.startswith("tb_fat_")]
    dims = [n for n in uniq if n.startswith("tb_dim_")]
    pec_hits = [n for n in uniq if n in {"tb_cidadao", "tb_atend"}]
    if facts and dims:
        kind = "centralizador_cubo"
    elif pec_hits:
        kind = "pec_operacional"
    elif facts or dims:
        kind = "parcial_cubo"
    else:
        kind = "desconhecido"
    return {
        "kind": kind,
        "facts": facts,
        "dims": dims,
        "pec_hits": pec_hits,
        "n_tables": len(uniq),
    }


def is_pii_column(name: str) -> bool:
    raw = str(name or "").strip().lower()
    if not raw:
        return False
    compact = raw.replace(" ", "_")
    for token in PII_COLUMN_TOKENS:
        if token in compact:
            return True
    return False


def select_relevant_tables(table_names: list[str], *, limit: int = 24) -> list[str]:
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for name in table_names:
        key = str(name).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        score = 0
        for i, hint in enumerate(RELEVANT_TABLE_HINTS):
            if hint in key:
                score = 100 - i
                break
        if key.startswith("tb_fat_") or key.startswith("tb_dim_"):
            score = max(score, 1)
        if score:
            scored.append((score, key))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _, name in scored[:limit]]


def suggest_indicators(table_names: list[str]) -> list[dict[str, str]]:
    names = [str(n).lower() for n in table_names]
    out: list[dict[str, str]] = []
    for item in INDICATOR_HINTS:
        matches = [n for n in names if item["hint"] in n]
        if matches:
            out.append(
                {
                    "id": item["id"],
                    "tabelas": ", ".join(sorted(set(matches))),
                    "uso": item["uso"],
                    "status": "candidato",
                }
            )
        else:
            out.append(
                {
                    "id": item["id"],
                    "tabelas": "",
                    "uso": item["uso"],
                    "status": "nao_encontrado",
                }
            )
    return out


def safe_ident(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"Identificador SQL inválido: {name!r}")
    return name


SqlReader = Callable[..., pd.DataFrame]


def fetch_table_catalog(reader: SqlReader | None = None) -> pd.DataFrame:
    sql = """
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
      AND table_schema NOT IN ('pg_catalog', 'information_schema')
    ORDER BY table_schema, table_name
    """
    fn = reader or read_esus_sql
    return fn(sql)


def fetch_columns(schema: str, table: str, reader: SqlReader | None = None) -> pd.DataFrame:
    sql = """
    SELECT column_name, data_type, udt_name
    FROM information_schema.columns
    WHERE table_schema = :schema AND table_name = :table
    ORDER BY ordinal_position
    """
    fn = reader or read_esus_sql
    return fn(sql, {"schema": safe_ident(schema), "table": safe_ident(table)})


def fetch_reltuples(schema: str, table: str, reader: SqlReader | None = None) -> float | None:
    sql = """
    SELECT c.reltuples::bigint AS reltuples
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relname = :table
    """
    fn = reader or read_esus_sql
    df = fn(sql, {"schema": safe_ident(schema), "table": safe_ident(table)})
    if df is None or df.empty:
        return None
    try:
        return float(df.iloc[0, 0])
    except (TypeError, ValueError):
        return None


def fetch_date_bounds(
    schema: str,
    table: str,
    columns: list[str],
    reader: SqlReader | None = None,
) -> dict[str, Any]:
    usable = [c for c in columns if c.lower() in DATE_COLUMN_CANDIDATES and not is_pii_column(c)]
    if not usable:
        return {}
    col = safe_ident(usable[0])
    sch = safe_ident(schema)
    tbl = safe_ident(table)
    sql = f"SELECT MIN({col}) AS dt_min, MAX({col}) AS dt_max FROM {sch}.{tbl}"
    fn = reader or read_esus_sql
    df = fn(sql)
    if df is None or df.empty:
        return {"coluna": col}
    return {
        "coluna": col,
        "min": None if pd.isna(df.iloc[0]["dt_min"]) else str(df.iloc[0]["dt_min"]),
        "max": None if pd.isna(df.iloc[0]["dt_max"]) else str(df.iloc[0]["dt_max"]),
    }
