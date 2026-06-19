from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass
import os
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]

# Carrega SEM sobrescrever variáveis já existentes do ambiente.
for _candidate in [ROOT / '.env', ROOT.parent / '.env', Path.cwd() / '.env']:
    if _candidate.exists():
        load_dotenv(_candidate, override=False)


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}

SETTINGS = _load_yaml(ROOT / 'config' / 'settings.yaml')

# Compatibilidade com os nomes de variáveis usados nos projetos anteriores
# TITAN/AESOP/LACEN/Monitora Hospitalar/SIVEP e com a V4 do SIS.
ENV_ALIASES: dict[str, list[str]] = {
    # Geral
    'RUN_MODE': ['RUN_MODE', 'MODO_PRODUCAO', 'MODO_EXECUCAO', 'AMBIENTE'],
    'DATABASE_URL': ['DATABASE_URL', 'DB_URL', 'SQLITE_URL', 'SQLITE_DATABASE_URL', 'DB_SQLITE_URL'],
    'APP_UF': ['APP_UF', 'UF', 'ESTADO_UF'],
    'APP_TIMEZONE': ['APP_TIMEZONE', 'TZ', 'TIMEZONE', 'FUSO_HORARIO'],
    'APP_LAT': ['APP_LAT', 'CUIABA_LAT', 'LATITUDE_PADRAO'],
    'APP_LON': ['APP_LON', 'CUIABA_LON', 'LONGITUDE_PADRAO'],
    'APP_MUNICIPIO': ['APP_MUNICIPIO', 'MUNICIPIO_PADRAO', 'CIDADE_PADRAO'],

    # Território
    'SHAPEFILE_MT': ['SHAPEFILE_MT', 'SHAPEFILE_MUNICIPIOS', 'SHAPEFILE_MUNICIPIOS_MT', 'SHP_MUNICIPIOS', 'MUNICIPIOS_SHP', 'PATH_SHAPEFILE_MUNICIPIOS'],
    'MUNICIPIOS_CSV': ['MUNICIPIOS_CSV', 'MUNICIPIOS_MT_CSV', 'CSV_MUNICIPIOS', 'CSV_MUNICIPIOS_MT', 'MUNICIPIOS_METADATA_CSV'],
    'POPULACAO_CSV': ['POPULACAO_CSV', 'POPULACAO_MUNICIPAL_CSV', 'POPULACAO_MT_CSV', 'CSV_POPULACAO', 'POPULACAO_XLSX', 'POPULACAO_MUNICIPAL_XLSX'],
    'MUNICIPIO_KEY': ['MUNICIPIO_KEY', 'CHAVE_IBGE', 'COD_IBGE_COL', 'CODIGO_IBGE_COL'],
    'MUNICIPIOS_SOURCE': ['MUNICIPIOS_SOURCE', 'FONTE_MUNICIPIOS'],

    # SQL Server / DW
    'USE_SQLSERVER': ['USE_SQLSERVER', 'USAR_SQLSERVER', 'USE_DW', 'USAR_DW', 'SQLSERVER_ENABLED', 'DW_ENABLED'],
    'DW_SERVER': ['DW_SERVER', 'DW_HOST', 'DATAWAREHOUSE_SERVER', 'DATAWAREHOUSE_HOST', 'SQLSERVER_HOST', 'SQLSERVER_SERVER', 'SERVER_SQL', 'DB_HOST', 'INDICASUS_SERVER'],
    'DW_DATABASE': ['DW_DATABASE', 'DW_DB', 'DATAWAREHOUSE_DATABASE', 'DATAWAREHOUSE_DB', 'SQLSERVER_DATABASE', 'SQLSERVER_DB', 'SQLSERVER_DATABASE_DW', 'DATABASE_DW', 'DB_NAME', 'INDICASUS_DATABASE'],
    'DW_USER': ['DW_USER', 'DW_LOGIN', 'DATAWAREHOUSE_USER', 'SQLSERVER_USER', 'SQLSERVER_USERNAME', 'DB_USER', 'USUARIO_DW', 'LOGIN_DW'],
    'DW_PASSWORD': ['DW_PASSWORD', 'DW_PASS', 'DATAWAREHOUSE_PASSWORD', 'SQLSERVER_PASSWORD', 'SQLSERVER_PWD', 'DB_PASSWORD', 'SENHA_DW', 'PASSWORD_DW'],
    'DW_DRIVER': ['DW_DRIVER', 'SQLSERVER_DRIVER', 'ODBC_DRIVER', 'DB_DRIVER'],
    'DW_TRUSTED_CONNECTION': ['DW_TRUSTED_CONNECTION', 'SQLSERVER_TRUSTED_CONNECTION', 'TRUSTED_CONNECTION'],
    'DW_TRUST_SERVER_CERTIFICATE': ['DW_TRUST_SERVER_CERTIFICATE', 'SQLSERVER_TRUST_SERVER_CERTIFICATE', 'TRUST_SERVER_CERTIFICATE'],
    'DW_QUERY_TIMEOUT_SECONDS': ['DW_QUERY_TIMEOUT_SECONDS', 'SQLSERVER_QUERY_TIMEOUT_SECONDS', 'QUERY_TIMEOUT_SECONDS'],

    # SIVEP local
    'USE_SIVEP_LOCAL': ['USE_SIVEP_LOCAL', 'SIVEP_LOCAL_ENABLED', 'USAR_SIVEP_LOCAL'],
    'SIVEP_LOCAL_DB_PATH': ['SIVEP_LOCAL_DB_PATH', 'SIVEP_LOCAL_DB', 'SIVEP_DB_PATH', 'SIVEP_DB', 'CAMINHO_SIVEP_DB'],
    'SIVEP_LOCAL_TABLE': ['SIVEP_LOCAL_TABLE', 'SIVEP_TABLE', 'TABELA_SIVEP'],
    'SIVEP_UPDATE_FOLDER': ['SIVEP_UPDATE_FOLDER', 'SIVEP_INPUT_DIR', 'SIVEP_FOLDER', 'PASTA_SIVEP', 'PASTA_ATUALIZACAO_SIVEP'],
    'SIVEP_FILE_PATTERN': ['SIVEP_FILE_PATTERN', 'SIVEP_PATTERN', 'PADRAO_ARQUIVOS_SIVEP'],

    # Copernicus / CDS / ADS / TITAN
    'USE_COPERNICUS': ['USE_COPERNICUS', 'COPERNICUS_ENABLED', 'USAR_COPERNICUS', 'TITAN_COPERNICUS_ENABLED'],
    'COPERNICUS_URL': ['COPERNICUS_URL', 'CDSAPI_URL', 'CDS_URL', 'ADS_URL', 'COPERNICUS_API_URL'],
    'COPERNICUS_KEY': ['COPERNICUS_KEY', 'CDSAPI_KEY', 'CDS_API_KEY', 'ADS_KEY', 'CDS_KEY', 'COPERNICUS_API_KEY'],
    'COPERNICUS_CAMS_DATASET': ['COPERNICUS_CAMS_DATASET', 'CAMS_DATASET'],
    'COPERNICUS_CAMS_VARIABLES': ['COPERNICUS_CAMS_VARIABLES', 'CAMS_VARIABLES'],
    'COPERNICUS_CAMS_LOCAL_FILE': ['COPERNICUS_CAMS_LOCAL_FILE', 'CAMS_LOCAL_FILE', 'TITAN_CAMS_FILE'],

    # INMET
    'USE_INMET': ['USE_INMET', 'INMET_ENABLED', 'USAR_INMET'],
    'INMET_ALERTS_URL': ['INMET_ALERTS_URL', 'INMET_ALERT_URL', 'URL_INMET_ALERTAS', 'INMET_URL_ALERTAS'],
    'INMET_STATION_CODE': ['INMET_STATION_CODE', 'INMET_ESTACAO', 'CODIGO_ESTACAO_INMET'],

    # Alertas e relatórios
    'SEND_ALERT_ON_LEVEL_CHANGE': ['SEND_ALERT_ON_LEVEL_CHANGE', 'ENVIAR_ALERTA_MUDANCA_NIVEL'],
    'ALERT_EMAIL_ENABLED': ['ALERT_EMAIL_ENABLED', 'EMAIL_ENABLED', 'USE_EMAIL', 'USAR_EMAIL'],
    'SMTP_HOST': ['SMTP_HOST', 'EMAIL_SMTP_HOST'],
    'SMTP_PORT': ['SMTP_PORT', 'EMAIL_SMTP_PORT'],
    'SMTP_USER': ['SMTP_USER', 'EMAIL_USER', 'EMAIL_REMETENTE'],
    'SMTP_PASSWORD': ['SMTP_PASSWORD', 'EMAIL_PASSWORD', 'EMAIL_SENHA'],
    'ALERT_EMAIL_TO': ['ALERT_EMAIL_TO', 'EMAIL_TO', 'DESTINATARIOS_EMAIL', 'ALERTA_EMAIL_DESTINATARIOS'],
    'ALERT_TELEGRAM_ENABLED': ['ALERT_TELEGRAM_ENABLED', 'TELEGRAM_ENABLED', 'USE_TELEGRAM', 'USAR_TELEGRAM'],
    'TELEGRAM_BOT_TOKEN': ['TELEGRAM_BOT_TOKEN', 'BOT_TOKEN_TELEGRAM', 'TELEGRAM_TOKEN'],
    'TELEGRAM_CHAT_ID': ['TELEGRAM_CHAT_ID', 'CHAT_ID_TELEGRAM', 'TELEGRAM_CHAT'],
    'ALERT_WEBHOOK_ENABLED': ['ALERT_WEBHOOK_ENABLED', 'WEBHOOK_ENABLED'],
    'WEBHOOK_URL': ['WEBHOOK_URL', 'WHATSAPP_WEBHOOK_URL', 'TEAMS_WEBHOOK_URL'],

    # IA
    'USE_LLM_REPORT': ['USE_LLM_REPORT', 'USE_IA_RELATORIO', 'USAR_IA_RELATORIO'],
    'LLM_API_URL': ['LLM_API_URL', 'OPENAI_BASE_URL', 'IA_API_URL'],
    'LLM_API_KEY': ['LLM_API_KEY', 'OPENAI_API_KEY', 'IA_API_KEY'],
    'LLM_MODEL': ['LLM_MODEL', 'OPENAI_MODEL', 'IA_MODEL'],
}


def env(key: str, default: str | None = None) -> str | None:
    """Lê variável de ambiente com aliases. Retorna o primeiro valor não vazio."""
    names = ENV_ALIASES.get(key, [key])
    if key not in names:
        names = [key] + names
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != '':
            return value
    return default


def env_name_used(key: str) -> str | None:
    """Indica qual nome real do .env alimentou uma chave canônica."""
    names = ENV_ALIASES.get(key, [key])
    if key not in names:
        names = [key] + names
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != '':
            return name
    return None


def as_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {'1','true','t','yes','y','sim','s','on'}


def path_from_root(*parts: str) -> Path:
    return ROOT.joinpath(*parts)


def resolve_path(value: str | None, default: str | None = None, must_exist: bool = False, candidates: list[str] | None = None) -> Path:
    """Resolve caminhos relativos ao ROOT e permite fallback para arquivos soltos na raiz."""
    options: list[str] = []
    if value:
        options.append(value)
    if default:
        options.append(default)
    options.extend(candidates or [])
    seen: set[str] = set()
    resolved: list[Path] = []
    for opt in options:
        if not opt or opt in seen:
            continue
        seen.add(opt)
        p = Path(opt)
        if not p.is_absolute():
            p = ROOT / p
        resolved.append(p)
        if p.exists():
            return p
    if resolved:
        return resolved[0]
    return ROOT


@dataclass
class AppConfig:
    root: Path = ROOT
    database_url: str = env('DATABASE_URL', 'sqlite:///data/output/sis_integrado.db') or 'sqlite:///data/output/sis_integrado.db'
    input_dir: Path = ROOT / SETTINGS.get('data_sources', {}).get('input_dir', 'data/input')
    output_dir: Path = ROOT / SETTINGS.get('data_sources', {}).get('output_dir', 'data/output')
    geo_dir: Path = ROOT / SETTINGS.get('data_sources', {}).get('geo_dir', 'data/geo')
    municipio: str = env('APP_MUNICIPIO', SETTINGS.get('app', {}).get('municipio', 'Cuiabá')) or 'Cuiabá'
    uf: str = env('APP_UF', SETTINGS.get('app', {}).get('uf', 'MT')) or 'MT'
    lat: float = float(env('APP_LAT', str(SETTINGS.get('app', {}).get('lat', -15.6014))) or -15.6014)
    lon: float = float(env('APP_LON', str(SETTINGS.get('app', {}).get('lon', -56.0979))) or -56.0979)
    timezone: str = env('APP_TIMEZONE', SETTINGS.get('app', {}).get('timezone', 'America/Cuiaba')) or 'America/Cuiaba'

    @property
    def shapefile_municipios(self) -> Path:
        return resolve_path(
            env('SHAPEFILE_MT'),
            SETTINGS.get('municipalizacao', {}).get('shapefile_mt', 'data/geo/municipios_mt/MT_Municipios_2025.shp'),
            candidates=['MT_Municipios_2025.shp', 'data/geo/MT_Municipios_2025.shp']
        )

    @property
    def municipios_csv(self) -> Path:
        return resolve_path(
            env('MUNICIPIOS_CSV'),
            'data/input/municipios_mt.csv',
            candidates=['municipios_mt.csv', 'Municípios MT lat long.csv', 'Municipios MT lat long.csv']
        )

    @property
    def populacao_path(self) -> Path:
        return resolve_path(
            env('POPULACAO_CSV'),
            SETTINGS.get('data_sources', {}).get('populacao_csv', 'populacao_municipal_mt_2020_2025.csv'),
            candidates=[
                'data/input/populacao_municipal_mt_2020_2025.csv',
                'populacao_municipal_mt_2020_2025.csv',
                'data/input/População Municípios Brasil 2020-2025.xlsx',
                'data/input/População Municípios Brasil 2020-2025(2).xlsx',
                'População Municípios Brasil 2020-2025.xlsx',
                'População Municípios Brasil 2020-2025(2).xlsx',
            ]
        )

APP_CONFIG = AppConfig()

for p in [APP_CONFIG.input_dir, APP_CONFIG.output_dir, APP_CONFIG.geo_dir, ROOT / 'logs', ROOT / 'data' / 'local' / 'sivep']:
    p.mkdir(parents=True, exist_ok=True)
