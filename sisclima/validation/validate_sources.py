from __future__ import annotations

from pathlib import Path
import pandas as pd

from sisclima.core.config import APP_CONFIG, env, as_bool, ROOT, env_name_used
from sisclima.ingestion.sqlserver import build_sqlserver_conn

SECRET_WORDS = ('PASSWORD', 'SENHA', 'TOKEN', 'KEY', 'PWD', 'PASS')


def _redact(name: str | None, value: str | None) -> str:
    if not value:
        return ''
    if name and any(w in name.upper() for w in SECRET_WORDS):
        return '***configurado***'
    if any(w in str(value).upper() for w in SECRET_WORDS):
        return '***configurado***'
    return str(value)


def check_file(path: Path, required: bool = False, label: str | None = None) -> dict:
    return {
        'item': label or str(path),
        'ok': path.exists(),
        'required': required,
        'detail': str(path) if path.exists() else f'ausente: {path}',
    }


def check_env(key: str, required: bool = False) -> dict:
    used = env_name_used(key)
    value = env(key)
    return {
        'item': key,
        'ok': bool(value) or not required,
        'required': required,
        'detail': f'{used}={_redact(used, value)}' if used else 'não informado',
    }




def _env_exists(key: str) -> bool:
    """Retorna True somente se alguma variável alias foi informada no .env/ambiente."""
    return env_name_used(key) is not None


def _has_copernicus_credential() -> bool:
    return bool(env('COPERNICUS_KEY')) or (ROOT / '.cdsapirc').exists() or (Path.home() / '.cdsapirc').exists()


def copernicus_enabled_for_validation() -> bool:
    """Ativa Copernicus se a chave existir e não houver desativação explícita."""
    if _env_exists('USE_COPERNICUS'):
        return as_bool(env('USE_COPERNICUS'), False)
    return _has_copernicus_credential()


def telegram_enabled_for_validation() -> bool:
    if _env_exists('ALERT_TELEGRAM_ENABLED'):
        return as_bool(env('ALERT_TELEGRAM_ENABLED'), False)
    return bool(env('TELEGRAM_BOT_TOKEN') and env('TELEGRAM_CHAT_ID'))


def email_enabled_for_validation() -> bool:
    if _env_exists('ALERT_EMAIL_ENABLED'):
        return as_bool(env('ALERT_EMAIL_ENABLED'), False)
    return bool(env('SMTP_HOST') and env('SMTP_USER') and env('SMTP_PASSWORD') and env('ALERT_EMAIL_TO'))

def validate_sources() -> pd.DataFrame:
    rows = []
    rows.append(check_env('RUN_MODE', required=False))
    rows.append({'item': 'DATABASE_URL', 'ok': bool(APP_CONFIG.database_url), 'required': True, 'detail': env_name_used('DATABASE_URL') + '=' + _redact(env_name_used('DATABASE_URL'), env('DATABASE_URL')) if env_name_used('DATABASE_URL') else f'padrão aplicado: {APP_CONFIG.database_url}'})
    rows.append(check_env('APP_TIMEZONE', required=False))

    # Base territorial. Aceita tanto estrutura organizada quanto arquivos soltos na raiz.
    rows.append(check_file(APP_CONFIG.shapefile_municipios, required=True, label='Shapefile municipal MT'))
    rows.append(check_file(APP_CONFIG.municipios_csv, required=True, label='CSV municípios MT'))
    rows.append(check_file(APP_CONFIG.populacao_path, required=True, label='População municipal'))

    # Copernicus
    cop_on = copernicus_enabled_for_validation()
    cop_key = _has_copernicus_credential()
    rows.append({'item': 'Copernicus CDS/ADS credencial', 'ok': cop_key or not cop_on, 'required': cop_on, 'detail': 'COPERNICUS_KEY/.cdsapirc encontrado' if cop_key else 'ausente'})
    rows.append({'item': 'USE_COPERNICUS', 'ok': True, 'required': False, 'detail': (env_name_used('USE_COPERNICUS') + '=' + str(env('USE_COPERNICUS'))) if env_name_used('USE_COPERNICUS') else ('auto=true por credencial encontrada' if cop_key else 'auto=false sem credencial')})
    rows.append(check_env('COPERNICUS_URL', required=False))

    # SQL Server DW — fonte institucional para IndicaSUS/CNES/SINAN/SIM/GAL.
    conn = build_sqlserver_conn('DW')
    rows.append({'item': 'SQL Server DW', 'ok': bool(conn), 'required': as_bool(env('USE_SQLSERVER', 'false')), 'detail': 'conexão configurada' if conn else 'servidor/base/usuário/senha ausentes ou incompletos'})
    for k in ['DW_SERVER', 'DW_DATABASE', 'DW_USER', 'DW_PASSWORD', 'DW_DRIVER']:
        rows.append(check_env(k, required=as_bool(env('USE_SQLSERVER', 'false')) and k != 'DW_DRIVER'))

    # SIVEP local.
    sivep_db = APP_CONFIG.root / (env('SIVEP_LOCAL_DB_PATH', 'data/local/sivep/sivep_srag_local.db') or 'data/local/sivep/sivep_srag_local.db')
    sivep_folder = APP_CONFIG.root / (env('SIVEP_UPDATE_FOLDER', 'data/input/sivep_atualizacao') or 'data/input/sivep_atualizacao')
    rows.append(check_file(sivep_folder, required=as_bool(env('USE_SIVEP_LOCAL', 'true'), True), label='Pasta atualização SIVEP'))
    rows.append(check_file(sivep_db, required=False, label='Banco local SIVEP'))

    # Alertas
    rows.append(check_env('TELEGRAM_BOT_TOKEN', required=telegram_enabled_for_validation()))
    rows.append(check_env('TELEGRAM_CHAT_ID', required=telegram_enabled_for_validation()))
    rows.append(check_env('SMTP_HOST', required=email_enabled_for_validation()))
    rows.append(check_env('SMTP_USER', required=email_enabled_for_validation()))
    rows.append(check_env('SMTP_PASSWORD', required=email_enabled_for_validation()))
    rows.append(check_env('ALERT_EMAIL_TO', required=email_enabled_for_validation()))
    rows.append(check_env('WEBHOOK_URL', required=as_bool(env('ALERT_WEBHOOK_ENABLED', 'false'))))

    return pd.DataFrame(rows)
