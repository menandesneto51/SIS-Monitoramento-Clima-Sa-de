from __future__ import annotations
import pandas as pd
from sisclima.core.config import env, as_bool
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _conn_parts(prefix: str = 'DW') -> dict[str, str | None]:
    # Para fontes institucionais, se INDICASUS/SINAN/SIM/GAL não tiver prefixo próprio,
    # usa automaticamente o DW, conforme operação real SES/MT.
    fallback_to_dw = prefix.upper() != 'DW'
    server = env(f'{prefix}_SERVER') or (env('DW_SERVER') if fallback_to_dw else None)
    database = env(f'{prefix}_DATABASE') or (env('DW_DATABASE') if fallback_to_dw else None)
    user = env(f'{prefix}_USER') or (env('DW_USER') if fallback_to_dw else None)
    password = env(f'{prefix}_PASSWORD') or (env('DW_PASSWORD') if fallback_to_dw else None)
    driver = env(f'{prefix}_DRIVER') or (env('DW_DRIVER') if fallback_to_dw else None) or 'ODBC Driver 17 for SQL Server'
    trusted = env(f'{prefix}_TRUSTED_CONNECTION') or (env('DW_TRUSTED_CONNECTION') if fallback_to_dw else None) or 'false'
    trust_cert = env(f'{prefix}_TRUST_SERVER_CERTIFICATE') or (env('DW_TRUST_SERVER_CERTIFICATE') if fallback_to_dw else None) or 'true'
    return {'server': server, 'database': database, 'user': user, 'password': password, 'driver': driver, 'trusted': trusted, 'trust_cert': trust_cert}


def build_sqlserver_conn(prefix: str = 'DW') -> str | None:
    parts = _conn_parts(prefix)
    server = parts['server']; database = parts['database']; user = parts['user']; password = parts['password']
    driver = parts['driver']; trusted = as_bool(parts['trusted'], False); trust_cert = parts['trust_cert']
    if not server or not database:
        return None
    base = f'DRIVER={{{driver}}};SERVER={server};DATABASE={database};TrustServerCertificate={trust_cert};'
    if trusted and not user:
        return base + 'Trusted_Connection=yes;'
    if user and password:
        return base + f'UID={user};PWD={password};'
    return None


def read_sqlserver(prefix: str, sql: str) -> pd.DataFrame:
    try:
        import pyodbc
    except Exception as e:
        log.warning('pyodbc indisponível: %s', e)
        return pd.DataFrame()
    conn_str = build_sqlserver_conn(prefix)
    if not conn_str:
        log.warning('Conexão SQL Server não configurada para prefixo %s', prefix)
        return pd.DataFrame()
    try:
        timeout = int(env(f'{prefix}_QUERY_TIMEOUT_SECONDS', env('DW_QUERY_TIMEOUT_SECONDS', '120')) or 120)
    except Exception:
        timeout = 120
    try:
        with pyodbc.connect(conn_str, timeout=30) as conn:
            return pd.read_sql(sql, conn)
    except Exception as e:
        log.warning('Falha SQL Server %s: %s', prefix, e)
        return pd.DataFrame()


def use_sqlserver() -> bool:
    return as_bool(env('USE_SQLSERVER', 'false'))


def use_dw_source(name: str) -> bool:
    return use_sqlserver() and as_bool(env(f'USE_DW_{name.upper()}', 'true'))
