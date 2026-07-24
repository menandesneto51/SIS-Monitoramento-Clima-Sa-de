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


def _odbc_yes_no(value: str | None, default: bool = True) -> str:
    """Normaliza atributos ODBC que exigem yes/no (Driver 17/18).

    Aceita true/false/1/0/yes/no e rejeita valores ambíguos caindo no default.
    """
    if value is None or str(value).strip() == '':
        return 'yes' if default else 'no'
    text = str(value).strip().lower()
    if text in {'yes', 'y', 'true', 't', '1', 'on'}:
        return 'yes'
    if text in {'no', 'n', 'false', 'f', '0', 'off'}:
        return 'no'
    # Valores especiais do Encrypt no Driver 18.
    if text in {'optional', 'mandatory', 'strict'}:
        return text
    return 'yes' if default else 'no'


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
    encrypt = env(f'{prefix}_ENCRYPT') or (env('DW_ENCRYPT') if fallback_to_dw else None) or 'no'
    trusted = env(f'{prefix}_TRUSTED_CONNECTION') or (env('DW_TRUSTED_CONNECTION') if fallback_to_dw else None) or 'false'
    trust_cert = env(f'{prefix}_TRUST_SERVER_CERTIFICATE') or (env('DW_TRUST_SERVER_CERTIFICATE') if fallback_to_dw else None) or 'yes'
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
    # ODBC Driver 17/18 exige yes/no (não true/false/0/1) em TrustServerCertificate.
    encrypt_raw = str(parts.get('encrypt') or 'no')
    encrypt = _odbc_yes_no(encrypt_raw, default=False)
    if encrypt_raw.strip().lower() in {'optional', 'mandatory', 'strict'}:
        encrypt = encrypt_raw.strip().lower()
    trusted = as_bool(parts['trusted'], False)
    trust_cert = _odbc_yes_no(parts.get('trust_cert'), default=True)
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


def _is_placeholder_password(password: str | None) -> bool:
    if password is None:
        return True
    text = str(password).strip()
    if not text:
        return True
    upper = text.upper()
    return (
        'COLE_AQUI' in upper
        or 'SENHA_REAL' in upper
        or 'PLACEHOLDER' in upper
        or 'CHANGEME' in upper
        or text.strip() in {'***', 'changeme'}
    )


def probe_sqlserver(prefix: str = 'DW') -> dict[str, str | bool]:
    """Testa a conexão SQL Server e devolve status/detalhe sem vazar a senha."""
    try:
        import pyodbc
    except Exception as e:
        return {'ok': False, 'detail': f'pyodbc indisponível: {e}'}

    parts = _conn_parts(prefix)
    password = str(parts.get('password') or '')
    user = parts.get('user') or '?'
    if _is_placeholder_password(password):
        return {
            'ok': False,
            'detail': (
                f'{prefix}_PASSWORD ainda está com placeholder '
                f'(ex.: COLE_AQUI_A_SENHA_DW); substitua pela senha real no .env'
            ),
        }

    conn_str = build_sqlserver_conn(prefix)
    if not conn_str:
        return {'ok': False, 'detail': f'conexão SQL Server não configurada para prefixo {prefix}'}

    try:
        with pyodbc.connect(conn_str, timeout=30) as conn:
            cur = conn.cursor()
            cur.execute('SELECT SYSTEM_USER AS usuario, DB_NAME() AS banco')
            row = cur.fetchone()
            usuario = row[0] if row else '?'
            banco = row[1] if row else '?'
            return {'ok': True, 'detail': f'conectado como {usuario} no banco {banco}'}
    except Exception as e:
        detail = str(e)
        # Evita vazamento acidental de senha no log/diagnóstico.
        if password:
            detail = detail.replace(password, '***')
        lower = detail.lower()
        if '18456' in detail or 'login failed' in lower:
            return {
                'ok': False,
                'detail': (
                    f"Login failed (18456) para usuário '{user}'. "
                    f"Confirme a senha em {prefix}_PASSWORD no .env (sem placeholder), "
                    f"SQL Authentication habilitado e conta ativa no SQL Server."
                ),
            }
        if 'trustservercertificate' in lower.replace(' ', ''):
            return {
                'ok': False,
                'detail': (
                    "TrustServerCertificate inválido para ODBC Driver 18. "
                    f"Use {prefix}_TRUST_SERVER_CERTIFICATE=yes (ou no) no .env — não use true/false/0/1."
                ),
            }
        return {'ok': False, 'detail': detail}


def read_sqlserver(prefix: str, sql: str) -> pd.DataFrame:
    try:
        import pyodbc
    except Exception as e:
        log.warning('pyodbc indisponível: %s', e)
        return pd.DataFrame()
    parts = _conn_parts(prefix)
    if _is_placeholder_password(parts.get('password')):
        log.warning(
            'Falha SQL Server %s: %s_PASSWORD ainda está com placeholder; não tentando conexão',
            prefix,
            prefix,
        )
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
