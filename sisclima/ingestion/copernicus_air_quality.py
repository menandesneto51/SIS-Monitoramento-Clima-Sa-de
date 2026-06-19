from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import os
import numpy as np
import pandas as pd
from sisclima.core.config import APP_CONFIG, env, as_bool, SETTINGS
from sisclima.core.logging_utils import get_logger
from sisclima.engines.air_quality import normalize_air_quality

log = get_logger(__name__)


def _copernicus_enabled() -> bool:
    if env_name_used('USE_COPERNICUS'):
        return as_bool(env('USE_COPERNICUS'), False)
    return bool(env('COPERNICUS_KEY') or (ROOT / '.cdsapirc').exists() or (Path.home() / '.cdsapirc').exists())

CAMS_VARIABLES = [
    'particulate_matter_2.5um',
    'particulate_matter_10um',
    'ozone',
    'nitrogen_dioxide',
    'carbon_monoxide',
    'sulphur_dioxide',
]


def _leadtime_hours() -> list[str]:
    raw = env('COPERNICUS_LEADTIME_HOURS', '0,3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,48') or ''
    return [x.strip() for x in raw.split(',') if x.strip()]


def build_cams_air_quality_request() -> tuple[str, dict, Path]:
    """Monta a requisição CAMS/ADS para qualidade do ar em tempo quase real.

    A autenticação deve estar em ~/.cdsapirc ou no .env com COPERNICUS_URL/COPERNICUS_KEY.
    """
    dataset = env('COPERNICUS_CAMS_DATASET', 'cams-global-atmospheric-composition-forecasts') or 'cams-global-atmospheric-composition-forecasts'
    today = datetime.now(timezone.utc).date().isoformat()
    leadtimes = _leadtime_hours()
    fmt = env('COPERNICUS_FORMAT', 'netcdf') or 'netcdf'
    area = [
        float(env('COPERNICUS_AREA_NORTH', '-7.0') or -7.0),
        float(env('COPERNICUS_AREA_WEST', '-62.0') or -62.0),
        float(env('COPERNICUS_AREA_SOUTH', '-18.5') or -18.5),
        float(env('COPERNICUS_AREA_EAST', '-50.0') or -50.0),
    ]
    request = {
        'variable': CAMS_VARIABLES,
        'date': today,
        'time': env('COPERNICUS_FORECAST_TIME', '00:00') or '00:00',
        'leadtime_hour': leadtimes,
        'type': 'forecast',
        'area': area,
        'format': fmt,
    }
    target = APP_CONFIG.output_dir / f'cams_air_quality_mt_{today.replace("-", "")}.{ "nc" if fmt == "netcdf" else "grib" }'
    return dataset, request, target


def download_cams_air_quality() -> Path | None:
    if not as_bool(env('USE_COPERNICUS', 'false')):
        log.info('Copernicus/CAMS desativado. USE_COPERNICUS=false')
        return None
    try:
        import cdsapi
    except Exception as e:
        log.warning('cdsapi não instalado/configurado: %s', e)
        return None
    dataset, request, target = build_cams_air_quality_request()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        if env('COPERNICUS_KEY'):
            client = cdsapi.Client(url=env('COPERNICUS_URL', 'https://ads.atmosphere.copernicus.eu/api'), key=env('COPERNICUS_KEY'))
        else:
            client = cdsapi.Client()
        log.info('Solicitando CAMS qualidade do ar: dataset=%s target=%s', dataset, target)
        client.retrieve(dataset, request, str(target))
        return target
    except Exception as e:
        log.warning('Falha ao baixar CAMS qualidade do ar: %s', e)
        return None


def _pick_var(ds, candidates: list[str]):
    for c in candidates:
        if c in ds.data_vars:
            return c
    # procura por aproximação no nome
    lower = {str(v).lower(): v for v in ds.data_vars}
    for c in candidates:
        c0 = c.lower().replace('.', '').replace('_', '')
        for lname, original in lower.items():
            if c0 in lname.replace('.', '').replace('_', ''):
                return original
    return None


def transform_cams_to_municipal(nc_path: str | Path, municipios: pd.DataFrame) -> pd.DataFrame:
    """Extrai valores do CAMS no ponto lat/lon de cada município.

    Se houver shapefile e rotina zonal habilitada, esta função pode ser substituída por média zonal.
    Para operação imediata, a extração por ponto municipal é robusta e rápida.
    """
    try:
        import xarray as xr
    except Exception as e:
        log.warning('xarray não instalado: %s', e)
        return pd.DataFrame()
    if municipios is None or municipios.empty or not {'lat','lon'}.issubset(municipios.columns):
        log.warning('Base municipal sem lat/lon; não é possível interpolar CAMS por município.')
        return pd.DataFrame()
    try:
        ds = xr.open_dataset(nc_path)
    except Exception as e:
        log.warning('Falha ao abrir arquivo CAMS %s: %s', nc_path, e)
        return pd.DataFrame()

    lat_name = 'latitude' if 'latitude' in ds.coords else ('lat' if 'lat' in ds.coords else None)
    lon_name = 'longitude' if 'longitude' in ds.coords else ('lon' if 'lon' in ds.coords else None)
    time_name = 'time' if 'time' in ds.coords else ('valid_time' if 'valid_time' in ds.coords else None)
    varmap = {
        'pm25_ugm3': ['pm2p5','pm2_5','particulate_matter_2.5um','particulate_matter_d_less_than_2.5_um'],
        'pm10_ugm3': ['pm10','particulate_matter_10um','particulate_matter_d_less_than_10_um'],
        'o3_ugm3': ['go3','o3','ozone'],
        'no2_ugm3': ['no2','nitrogen_dioxide'],
        'co_mgm3': ['co','carbon_monoxide'],
        'so2_ugm3': ['so2','sulphur_dioxide','sulfur_dioxide'],
    }
    rows = []
    for _, m in municipios.iterrows():
        try:
            if not lat_name or not lon_name:
                continue
            point = ds.sel({lat_name: float(m['lat']), lon_name: float(m['lon'])}, method='nearest')
            rec = {
                'cod_ibge': m.get('cod_ibge'), 'municipio': m.get('municipio'),
                'lat': m.get('lat'), 'lon': m.get('lon'), 'fonte':'copernicus_cams'
            }
            if time_name and time_name in point.coords:
                try:
                    rec['data'] = pd.to_datetime(point[time_name].values.ravel()[0]).date().isoformat()
                except Exception:
                    rec['data'] = pd.Timestamp.now().date().isoformat()
            else:
                rec['data'] = pd.Timestamp.now().date().isoformat()
            for outcol, candidates in varmap.items():
                vname = _pick_var(point, candidates)
                if vname:
                    vals = np.asarray(point[vname].values).astype(float).ravel()
                    rec[outcol] = float(np.nanmean(vals)) if vals.size else np.nan
            rows.append(rec)
        except Exception as e:
            log.debug('Falha CAMS município %s: %s', m.get('municipio'), e)
    return normalize_air_quality(pd.DataFrame(rows))


def fetch_cams_air_quality_municipal(municipios: pd.DataFrame) -> pd.DataFrame:
    target = download_cams_air_quality()
    if target is None:
        return pd.DataFrame()
    return transform_cams_to_municipal(target, municipios)
