from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _copernicus_enabled() -> bool:
    if env_name_used('USE_COPERNICUS'):
        return as_bool(env('USE_COPERNICUS'), False)
    return bool(env('COPERNICUS_KEY') or (ROOT / '.cdsapirc').exists() or (Path.home() / '.cdsapirc').exists())

DEFAULT_CAMS_VARIABLES = [
    "particulate_matter_2.5um",
    "particulate_matter_10um",
    "ozone",
    "nitrogen_dioxide",
    "carbon_monoxide",
    "sulphur_dioxide",
]

VAR_ALIASES = {
    "pm2p5": ["pm2p5", "pm2p5_conc", "particulate_matter_2.5um", "particulate_matter_2p5um", "pm2p5_ug_m3", "pm2_5"],
    "pm10": ["pm10", "pm10_conc", "particulate_matter_10um", "pm10_ug_m3"],
    "o3": ["go3", "o3", "ozone", "ozone_concentration"],
    "no2": ["no2", "nitrogen_dioxide", "nitrogen_dioxide_concentration"],
    "co": ["co", "carbon_monoxide", "carbon_monoxide_concentration"],
    "so2": ["so2", "sulphur_dioxide", "sulfur_dioxide", "sulphur_dioxide_concentration"],
}


def _parse_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def cams_request_default() -> dict:
    # A ADS/CDS recomenda gerar o código pela página do dataset. Este request é
    # parametrizado e pode ser substituído por COPERNICUS_CAMS_REQUEST_JSON.
    lead = _parse_list(env("COPERNICUS_LEADTIME_HOURS"), ["0", "3", "6", "9", "12", "15", "18", "21", "24"])
    variables = _parse_list(env("COPERNICUS_CAMS_VARIABLES"), DEFAULT_CAMS_VARIABLES)
    area = [
        float(env("COPERNICUS_AREA_NORTH", "-7.0")),
        float(env("COPERNICUS_AREA_WEST", "-62.0")),
        float(env("COPERNICUS_AREA_SOUTH", "-18.5")),
        float(env("COPERNICUS_AREA_EAST", "-50.0")),
    ]
    return {
        "date": env("COPERNICUS_DATE", _today_utc()),
        "type": ["forecast"],
        "format": env("COPERNICUS_FORMAT", "netcdf"),
        "variable": variables,
        "time": [env("COPERNICUS_FORECAST_TIME", "00:00")],
        "leadtime_hour": lead,
        "area": area,
    }


def load_cams_request() -> dict:
    raw = env("COPERNICUS_CAMS_REQUEST_JSON")
    if raw:
        try:
            p = Path(raw)
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
            return json.loads(raw)
        except Exception as e:
            raise RuntimeError(f"COPERNICUS_CAMS_REQUEST_JSON inválido: {e}") from e
    return cams_request_default()


def _ensure_cdsapi_config(url: str | None, key: str | None) -> None:
    if not url or not key:
        return
    # cdsapi aceita variáveis CDSAPI_URL/CDSAPI_KEY; evita escrever token em disco.
    os.environ.setdefault("CDSAPI_URL", url)
    os.environ.setdefault("CDSAPI_KEY", key)


def retrieve_cams_file(target: str | Path | None = None) -> Path | None:
    if not as_bool(env("USE_COPERNICUS", "false")):
        log.info("USE_COPERNICUS=false ou credencial ausente. CAMS não será consultado.")
        return None
    try:
        import cdsapi
    except Exception as e:
        log.warning("cdsapi não instalado/disponível: %s", e)
        return None

    dataset = env("COPERNICUS_CAMS_DATASET", "cams-global-atmospheric-composition-forecasts")
    url = env("COPERNICUS_URL", "https://ads.atmosphere.copernicus.eu/api")
    key = env("COPERNICUS_KEY")
    _ensure_cdsapi_config(url, key)

    out_dir = APP_CONFIG.root / "data" / "raw" / "copernicus"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_path = Path(target) if target else out_dir / f"cams_aq_mt_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.nc"
    req = load_cams_request()
    try:
        log.info("Solicitando CAMS: dataset=%s target=%s", dataset, target_path)
        client = cdsapi.Client(url=url if url else None, key=key if key else None)
        client.retrieve(dataset, req, str(target_path))
        return target_path
    except Exception as e:
        log.warning("Falha na extração CAMS/Copernicus: %s", e)
        return None


def _nearest_coord_name(ds, candidates: Iterable[str]) -> str | None:
    names = set(list(ds.coords) + list(ds.dims))
    for c in candidates:
        if c in names:
            return c
    return None


def _var_name(ds, alias_key: str) -> str | None:
    names = set(ds.data_vars)
    for candidate in VAR_ALIASES.get(alias_key, []):
        if candidate in names:
            return candidate
    # busca flexível por pedaço do nome
    for n in names:
        ln = n.lower()
        if alias_key == "pm2p5" and ("2.5" in ln or "2p5" in ln):
            return n
        if alias_key == "pm10" and "10" in ln and "pm" in ln:
            return n
        if alias_key in ln:
            return n
    return None


def _to_ugm3(v: float | None, var: str) -> float | None:
    if v is None or np.isnan(v):
        return None
    # CAMS pode vir em kg/m3 para PM e kg/kg para gases. Sem metadado completo,
    # mantemos PM em ug/m3 quando valores estão na escala kg/m3. Para gases, usamos
    # proxy operacional apenas para classificação relativa, com campo bruto preservado.
    if var in {"pm2p5", "pm10"}:
        if abs(v) < 1e-3:
            return float(v) * 1e9
    return float(v)


def extract_cams_to_municipios(nc_path: str | Path, municipios: pd.DataFrame) -> pd.DataFrame:
    try:
        import xarray as xr
    except Exception as e:
        raise RuntimeError("xarray/netCDF4 são necessários para processar CAMS NetCDF") from e
    p = Path(nc_path)
    if not p.exists():
        return pd.DataFrame()
    ds = xr.open_dataset(p)
    lat_name = _nearest_coord_name(ds, ["latitude", "lat"])
    lon_name = _nearest_coord_name(ds, ["longitude", "lon"])
    time_name = _nearest_coord_name(ds, ["time", "valid_time", "forecast_reference_time"])
    if not lat_name or not lon_name:
        raise RuntimeError(f"Não encontrei coordenadas lat/lon no arquivo CAMS: {list(ds.coords)}")
    varmap = {k: _var_name(ds, k) for k in VAR_ALIASES}
    rows = []
    for _, m in municipios.iterrows():
        try:
            lat = float(m.get("lat")); lon = float(m.get("lon"))
        except Exception:
            continue
        sel = ds.sel({lat_name: lat, lon_name: lon}, method="nearest")
        # reduz dimensões não espaciais, pegando média do horizonte disponível.
        rec = {
            "data": pd.Timestamp.utcnow().date().isoformat(),
            "cod_ibge": m.get("cod_ibge"),
            "municipio": m.get("municipio"),
            "lat": lat,
            "lon": lon,
            "fonte_qualidade_ar": "copernicus_cams",
            "arquivo_origem": str(p.name),
        }
        for out_name, ds_name in varmap.items():
            if not ds_name:
                continue
            arr = sel[ds_name]
            try:
                val = float(arr.mean(skipna=True).values)
            except Exception:
                val = None
            rec[f"{out_name}_bruto"] = val
            rec[f"{out_name}_ugm3"] = _to_ugm3(val, out_name)
        rows.append(rec)
    return pd.DataFrame(rows)


def fetch_cams_air_quality_real(municipios: pd.DataFrame) -> pd.DataFrame:
    cached = env("COPERNICUS_CAMS_LOCAL_FILE")
    path = Path(cached) if cached else retrieve_cams_file()
    if not path or not path.exists():
        return pd.DataFrame()
    return extract_cams_to_municipios(path, municipios)
