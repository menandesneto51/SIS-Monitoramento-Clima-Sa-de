from __future__ import annotations
import sys
import pandas as pd
from sisclima.core.config import env, as_bool
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _conn_parts(prefix: str = "DW") -> dict[str, str | None]:
    fallback_to_dw = prefix.upper() != "DW"
    server = env(f"{prefix}_SERVER") or (env("DW_SERVER") if fallback_to_dw else None)
    database = env(f"{prefix}_DATABASE") or (env("DW_DATABASE") if fallback_to_dw else None)
    user = env(f"{prefix}_USER") or (env("DW_USER") if fallback_to_dw else None)
    password = env(f"{prefix}_PASSWORD") or (env("DW_PASSWORD") if fallback_to_dw else None)
    driver = (
        env(f"{prefix}_DRIVER")
        or (env("DW_DRIVER") if fallback_to_dw else None)
        or "ODBC Driver 17 for SQL Server"
    )
    trusted = env(f"{prefix}_TRUSTED_CONNECTION") or (
        env("DW_TRUSTED_CONNECTION") if fallback_to_dw else None
    ) or "false"
    trust_cert = env(f"{prefix}_TRUST_SERVER_CERTIFICATE") or (
        env("DW_TRUST_SERVER_CERTIFICATE") if fallback_to_dw else None
    ) or "true"
    port = env(f"{prefix}_PORT") or (env("DW_PORT") if fallback_to_dw else None) or "1433"
    return {
        "server": server,
        "database": database,
        "user": user,
        "password": password,
        "driver": driver,
        "trusted": trusted,
        "trust_cert": trust_cert,
        "port": port,
    }


def build_sqlserver_conn(prefix: str = "DW") -> str | None:
    parts = _conn_parts(prefix)
    server = parts["server"]
    database = parts["database"]
    user = parts["user"]
    password = parts["password"]
    driver = parts["driver"]
    trusted = as_bool(parts["trusted"], False)
    trust_cert = parts["trust_cert"]
    encrypt = env(f"{prefix}_ENCRYPT") or env("DW_ENCRYPT") or "no"
    port = parts["port"] or "1433"
    if not server or not database:
        return None
    # Prefer host,port form (ODBC 18 / FreeTDS friendly)
    server_target = server if ("," in str(server) or str(server).lower().startswith("tcp:")) else f"{server},{port}"
    base = (
        f"DRIVER={{{driver}}};SERVER={server_target};DATABASE={database};"
        f"Encrypt={encrypt};TrustServerCertificate={trust_cert};"
    )
    if trusted and not user:
        return base + "Trusted_Connection=yes;"
    if user and password:
        return base + f"UID={user};PWD={password};"
    return None


def _read_with_pyodbc(prefix: str, sql: str) -> pd.DataFrame:
    import pyodbc

    conn_str = build_sqlserver_conn(prefix)
    if not conn_str:
        raise RuntimeError("DSN ODBC incompleto")
    with pyodbc.connect(conn_str, timeout=30) as conn:
        return pd.read_sql(sql, conn)


def _parse_server_port(server: str, default_port: int = 1433) -> tuple[str, int]:
    port = default_port
    if "," in server:
        host, p = server.split(",", 1)
        return host.strip(), int(p.strip())
    if ":" in server and not server.lower().startswith("tcp:"):
        host, p = server.rsplit(":", 1)
        if p.isdigit():
            return host.strip(), int(p)
    return server, port


def _read_with_pymssql(prefix: str, sql: str) -> pd.DataFrame:
    import pymssql

    parts = _conn_parts(prefix)
    if not parts["server"] or not parts["database"] or not parts["user"] or not parts["password"]:
        raise RuntimeError("Credenciais pymssql incompletas")
    server, port = _parse_server_port(parts["server"], int(parts["port"] or 1433))
    timeout = int(env(f"{prefix}_QUERY_TIMEOUT_SECONDS", env("DW_QUERY_TIMEOUT_SECONDS", "120")) or 120)
    with pymssql.connect(
        server=server,
        user=parts["user"],
        password=parts["password"],
        database=parts["database"],
        port=port,
        login_timeout=30,
        timeout=timeout,
    ) as conn:
        return pd.read_sql(sql, conn)


def read_sqlserver(prefix: str, sql: str) -> pd.DataFrame:
    prefer = (env("DW_CLIENT", "auto") or "auto").strip().lower()
    if prefer == "pymssql":
        clients = [("pymssql", _read_with_pymssql)]
    elif prefer == "pyodbc":
        clients = [("pyodbc", _read_with_pyodbc)]
    elif sys.platform.startswith("linux"):
        clients = [("pymssql", _read_with_pymssql), ("pyodbc", _read_with_pyodbc)]
    else:
        clients = [("pyodbc", _read_with_pyodbc), ("pymssql", _read_with_pymssql)]

    errors: list[str] = []
    for name, fn in clients:
        try:
            return fn(prefix, sql)
        except Exception as e:
            errors.append(f"{name}: {e}")
            continue

    log.warning("Falha SQL Server %s: %s", prefix, " | ".join(errors[-3:]))
    return pd.DataFrame()


def use_sqlserver() -> bool:
    return as_bool(env("USE_SQLSERVER", "false"))


def use_dw_source(name: str) -> bool:
    return use_sqlserver() and as_bool(env(f"USE_DW_{name.upper()}", "true"))
