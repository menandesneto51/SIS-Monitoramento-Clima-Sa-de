from __future__ import annotations
import pandas as pd
from sisclima.core.config import env, as_bool
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _available_pyodbc_drivers() -> list[str]:
    try:
        import pyodbc
        return [str(d) for d in pyodbc.drivers()]
    except Exception:
        return []


def _pick_sqlserver_driver(preferred: str | None) -> str:
    """Seleciona o melhor driver SQL Server disponível.

    Prioridade:
    1) Driver preferido configurado no .env (se instalado)
    2) ODBC Driver 18 for SQL Server
    3) ODBC Driver 17 for SQL Server
    4) SQL Server (driver legado)
    5) Valor preferido mesmo não instalado (permite log explícito na conexão)
    """
    available = _available_pyodbc_drivers()
    if preferred and preferred in available:
        return preferred
    for candidate in ['ODBC Driver 18 for SQL Server', 'ODBC Driver 17 for SQL Server', 'SQL Server']:
        if candidate in available:
            return candidate
    return preferred or 'ODBC Driver 17 for SQL Server'


def _conn_parts(prefix: str = 'DW') -> dict[str, str | None]:
    # Para fontes institucionais, se INDICASUS/SINAN/SIM/GAL não tiver prefixo próprio,
    # usa automaticamente o DW, conforme operação real SES/MT.
    fallback_to_dw = prefix.upper() != 'DW'
    server = env(f'{prefix}_SERVER') or (env('DW_SERVER') if fallback_to_dw else None)
    database = env(f'{prefix}_DATABASE') or (env('DW_DATABASE') if fallback_to_dw else None)
    user = env(f'{prefix}_USER') or (env('DW_USER') if fallback_to_dw else None)
    password = env(f'{prefix}_PASSWORD') or (env('DW_PASSWORD') if fallback_to_dw else None)
    preferred_driver = env(f'{prefix}_DRIVER') or (env('DW_DRIVER') if fallback_to_dw else None) or 'ODBC Driver 17 for SQL Server'
    driver = _pick_sqlserver_driver(preferred_driver)
    port = env(f'{prefix}_PORT') or (env('DW_PORT') if fallback_to_dw else None)
    encrypt = env(f'{prefix}_ENCRYPT') or (env('DW_ENCRYPT') if fallback_to_dw else None) or 'yes'
    trusted = env(f'{prefix}_TRUSTED_CONNECTION') or (env('DW_TRUSTED_CONNECTION') if fallback_to_dw else None) or 'false'
    trust_cert = env(f'{prefix}_TRUST_SERVER_CERTIFICATE') or (env('DW_TRUST_SERVER_CERTIFICATE') if fallback_to_dw else None) or 'true'
    return {
        'server': server,
        'port': port,
        'database': database,
        'user': user,
        'password': password,
        'driver': driver,
        'preferred_driver': preferred_driver,
        'encrypt': encrypt,
        'trusted': trusted,
        'trust_cert': trust_cert
    }


def build_sqlserver_conn(prefix: str = 'DW') -> str | None:
    parts = _conn_parts(prefix)
    server = parts['server']; database = parts['database']; user = parts['user']; password = parts['password']
    port = parts.get('port')
    driver = parts['driver']
    preferred_driver = parts.get('preferred_driver')
    encrypt = parts.get('encrypt', 'yes')
    trusted = as_bool(parts['trusted'], False)
    trust_cert = parts['trust_cert']
    if not server or not database:
        return None
    server_target = f'{server},{port}' if port else str(server)
    base = (
        f'DRIVER={{{driver}}};'
        f'SERVER={server_target};'
        f'DATABASE={database};'
        f'Encrypt={encrypt};'
        f'TrustServerCertificate={trust_cert};'
    )
    if preferred_driver and preferred_driver != driver:
        log.info('Driver SQL Server ajustado automaticamente: preferido=%s, usando=%s', preferred_driver, driver)
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
