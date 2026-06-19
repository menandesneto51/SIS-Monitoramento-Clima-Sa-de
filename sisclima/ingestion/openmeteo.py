from __future__ import annotations
import time
import requests
import pandas as pd
from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _fetch_one(lat: float, lon: float, municipio: str | None = None, cod_ibge=None, days: int = 7) -> pd.DataFrame:
    base = env('OPENMETEO_BASE_URL', 'https://api.open-meteo.com/v1/forecast')
    params = {
        'latitude': lat,
        'longitude': lon,
        'hourly': 'temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,apparent_temperature',
        'daily': 'temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,wind_speed_10m_max',
        'forecast_days': days,
        'timezone': APP_CONFIG.timezone
    }
    r = requests.get(base, params=params, timeout=30)
    r.raise_for_status()
    js = r.json()
    daily = pd.DataFrame(js.get('daily', {}))
    if daily.empty:
        return pd.DataFrame()
    daily = daily.rename(columns={
        'time': 'data',
        'temperature_2m_max': 'tmax',
        'temperature_2m_min': 'tmin',
        'relative_humidity_2m_mean': 'umidade_media',
        'wind_speed_10m_max': 'vento_max'
    })
    daily['cod_ibge'] = cod_ibge
    daily['municipio'] = municipio or APP_CONFIG.municipio
    daily['lat'] = lat
    daily['lon'] = lon
    daily['fonte'] = 'openmeteo'
    return daily


def fetch_openmeteo_forecast(days: int = 7) -> pd.DataFrame:
    if not as_bool(env('USE_OPENMETEO', 'true'), True):
        return pd.DataFrame()
    try:
        return _fetch_one(APP_CONFIG.lat, APP_CONFIG.lon, APP_CONFIG.municipio, None, days)
    except Exception as e:
        log.warning('Falha ao consultar Open-Meteo: %s', e)
        return pd.DataFrame()


def fetch_openmeteo_for_municipios(municipios: pd.DataFrame, days: int = 7, max_municipios: int | None = None) -> pd.DataFrame:
    """Consulta previsão por município usando lat/lon da base municipal.

    Por padrão não limita quantidade. Use OPENMETEO_MAX_MUNICIPIOS para teste.
    """
    if not as_bool(env('USE_OPENMETEO', 'true'), True):
        return pd.DataFrame()
    if municipios is None or municipios.empty or not {'lat','lon'}.issubset(municipios.columns):
        return fetch_openmeteo_forecast(days)
    max_env = env('OPENMETEO_MAX_MUNICIPIOS')
    if max_municipios is None and max_env:
        try: max_municipios = int(max_env)
        except Exception: max_municipios = None
    dfm = municipios.dropna(subset=['lat','lon']).copy()
    if max_municipios:
        dfm = dfm.head(max_municipios)
    frames = []
    for _, m in dfm.iterrows():
        try:
            frames.append(_fetch_one(float(m['lat']), float(m['lon']), str(m.get('municipio','')), m.get('cod_ibge'), days))
            time.sleep(0.15)
        except Exception as e:
            log.warning('Falha Open-Meteo para %s: %s', m.get('municipio'), e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
