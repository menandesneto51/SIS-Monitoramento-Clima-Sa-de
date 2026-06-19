from __future__ import annotations
from pathlib import Path
import pandas as pd
from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _copernicus_enabled() -> bool:
    if env_name_used('USE_COPERNICUS'):
        return as_bool(env('USE_COPERNICUS'), False)
    return bool(env('COPERNICUS_KEY') or (ROOT / '.cdsapirc').exists() or (Path.home() / '.cdsapirc').exists())


def fetch_era5_land_daily(year: int, month: int, output_nc: str | None = None) -> Path | None:
    """Baixa ERA5-Land via cdsapi quando credenciais estiverem configuradas.

    Esta função é deliberadamente conservadora: não roda se USE_COPERNICUS=false.
    Para operar, configure ~/.cdsapirc ou COPERNICUS_URL/COPERNICUS_KEY no .env.
    """
    if not _copernicus_enabled():
        log.info('Copernicus desativado. USE_COPERNICUS=false ou credencial ausente')
        return None
    try:
        import cdsapi
    except Exception as e:
        log.warning('cdsapi não instalado/configurado: %s', e)
        return None

    target = Path(output_nc or APP_CONFIG.output_dir / f'era5_land_{year}_{month:02d}.nc')
    target.parent.mkdir(parents=True, exist_ok=True)
    c = cdsapi.Client(url=env('COPERNICUS_URL'), key=env('COPERNICUS_KEY')) if env('COPERNICUS_KEY') else cdsapi.Client()
    days = [f'{d:02d}' for d in range(1, 32)]
    request = {
        'variable': ['2m_temperature', '2m_dewpoint_temperature', '10m_u_component_of_wind', '10m_v_component_of_wind', 'surface_solar_radiation_downwards'],
        'year': str(year),
        'month': f'{month:02d}',
        'day': days,
        'time': [f'{h:02d}:00' for h in range(24)],
        'area': [-14.8, -56.9, -16.4, -55.3],  # N, W, S, E - Cuiabá e entorno
        'format': 'netcdf'
    }
    dataset = env('COPERNICUS_DATASET', 'reanalysis-era5-land') or 'reanalysis-era5-land'
    c.retrieve(dataset, request, str(target))
    return target


def transform_era5_to_daily_placeholder(nc_path: str | Path) -> pd.DataFrame:
    """Placeholder de transformação.

    Em produção, usar xarray para recortar por município/malha e agregar por dia.
    """
    log.info('Arquivo ERA5 recebido: %s. Transformação xarray deve ser ligada em produção.', nc_path)
    return pd.DataFrame()
