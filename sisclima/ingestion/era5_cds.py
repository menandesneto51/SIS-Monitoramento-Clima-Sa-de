"""ERA5-Land diário via Copernicus Climate Data Store (CDS).

Usa o dataset *derived-era5-land-daily-statistics* (T2m mín/méd/máx) no recorte de MT
e amostra o ponto de grade mais próximo de cada município.

A chave CDS (climate.copernicus.eu) é distinta da chave CAMS/ADS (atmosfera).
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from sisclima.core.config import APP_CONFIG, ROOT, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DATASET = "derived-era5-land-daily-statistics"
STATS = (
    ("daily_minimum", "tmin"),
    ("daily_mean", "tmedia"),
    ("daily_maximum", "tmax"),
)
DAYS = [f"{d:02d}" for d in range(1, 32)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]


def mt_area() -> list[float]:
    return [
        float(env("COPERNICUS_AREA_NORTH", "-7.0") or -7.0),
        float(env("COPERNICUS_AREA_WEST", "-62.0") or -62.0),
        float(env("COPERNICUS_AREA_SOUTH", "-18.5") or -18.5),
        float(env("COPERNICUS_AREA_EAST", "-50.0") or -50.0),
    ]


def cds_key() -> str:
    return (env("COPERNICUS_CDS_KEY", "") or "").strip()


def has_cds_credentials() -> bool:
    if cds_key():
        return True
    return (ROOT / ".cdsapirc").exists() or (Path.home() / ".cdsapirc").exists()


def _client():
    import cdsapi

    key = cds_key()
    url = (env("COPERNICUS_CDS_URL", "") or "").strip() or "https://cds.climate.copernicus.eu/api"
    if key:
        return cdsapi.Client(url=url, key=key)
    return cdsapi.Client()


def _kelvin_to_c(arr: np.ndarray) -> np.ndarray:
    out = np.asarray(arr, dtype=float)
    finite = np.isfinite(out)
    if finite.any() and float(np.nanmedian(out[finite])) > 100:
        out = out - 273.15
    return out


def _coord_1d(ds, names: tuple[str, ...]) -> np.ndarray:
    for name in names:
        if name in ds.variables:
            return np.asarray(ds.variables[name][:], dtype=float)
        if hasattr(ds, name):
            return np.asarray(getattr(ds, name).values, dtype=float)
    raise KeyError(f"Coordenada não encontrada: {names}")


def _open_dataset(path: Path):
    try:
        import xarray as xr

        return xr.open_dataset(path)
    except Exception:
        import netCDF4

        return netCDF4.Dataset(path)


def _time_index(ds) -> pd.DatetimeIndex:
    for name in ("valid_time", "time", "date"):
        if hasattr(ds, "variables") and name in getattr(ds, "variables", {}):
            vals = ds.variables[name][:]
            return pd.to_datetime(vals)
        if hasattr(ds, name):
            return pd.to_datetime(np.asarray(getattr(ds, name).values))
    raise KeyError("Eixo temporal não encontrado no NetCDF ERA5")


def _t2m_array(ds) -> np.ndarray:
    for name in ("t2m", "T2M", "2m_temperature", "temperature_2m"):
        if hasattr(ds, "data_vars") and name in ds.data_vars:
            return np.asarray(ds[name].values, dtype=float)
        if hasattr(ds, "variables") and name in ds.variables:
            return np.asarray(ds.variables[name][:], dtype=float)
    if hasattr(ds, "data_vars"):
        for name, var in ds.data_vars.items():
            if var.ndim >= 3:
                return np.asarray(var.values, dtype=float)
    raise KeyError("Variável de temperatura 2 m não encontrada")


def _nearest(grid: np.ndarray, value: float) -> int:
    return int(np.nanargmin(np.abs(grid - value)))


def amostrar_netcdf_municipios(path: Path, municipios: pd.DataFrame, col_out: str) -> pd.DataFrame:
    """Amostra a grade ERA5 no vizinho mais próximo de cada município."""
    ds = _open_dataset(path)
    try:
        lat = _coord_1d(ds, ("latitude", "lat"))
        lon = _coord_1d(ds, ("longitude", "lon"))
        if float(np.nanmin(lon)) >= 0:
            lon_pts = pd.to_numeric(municipios["lon"], errors="coerce") % 360
        else:
            lon_pts = pd.to_numeric(municipios["lon"], errors="coerce")
        lat_pts = pd.to_numeric(municipios["lat"], errors="coerce")
        times = _time_index(ds)
        cube = _kelvin_to_c(_t2m_array(ds))
        while cube.ndim > 3:
            cube = cube.squeeze()
        if cube.ndim != 3:
            raise ValueError(f"Grade T2m inesperada ndim={cube.ndim}")
        # (time, lat, lon) ou (time, lon, lat)
        if cube.shape[1] == lat.size and cube.shape[2] == lon.size:
            lat_axis, lon_axis = 1, 2
        elif cube.shape[1] == lon.size and cube.shape[2] == lat.size:
            lat_axis, lon_axis = 2, 1
        else:
            lat_axis, lon_axis = 1, 2

        rows = []
        mun = municipios.reset_index(drop=True)
        for i, rec in mun.iterrows():
            if pd.isna(lat_pts.iloc[i]) or pd.isna(lon_pts.iloc[i]):
                continue
            iy = _nearest(lat, float(lat_pts.iloc[i]))
            ix = _nearest(lon, float(lon_pts.iloc[i]))
            if lat_axis == 1:
                series = cube[:, iy, ix]
            else:
                series = cube[:, ix, iy]
            for t, val in zip(times, series):
                rows.append(
                    {
                        "cod_ibge": str(rec.get("cod_ibge", "")).replace(".0", "").zfill(7),
                        "municipio": rec.get("municipio"),
                        "data": pd.Timestamp(t).strftime("%Y-%m-%d"),
                        col_out: None if not np.isfinite(val) else float(val),
                    }
                )
        return pd.DataFrame(rows)
    finally:
        close = getattr(ds, "close", None)
        if callable(close):
            close()


def _unzip_if_needed(path: Path) -> Path:
    if path.suffix.lower() != ".zip" and not zipfile.is_zipfile(path):
        return path
    dest = path.with_suffix("")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.extractall(dest)
    ncs = sorted(dest.rglob("*.nc"))
    if not ncs:
        raise FileNotFoundError(f"ZIP CDS sem NetCDF: {path}")
    return ncs[0]


def build_era5_request(year: str, months: list[str], statistic: str) -> dict:
    return {
        "variable": ["2m_temperature"],
        "year": year,
        "month": months,
        "day": DAYS,
        "daily_statistic": statistic,
        "time_zone": env("COPERNICUS_ERA5_TZ", "utc-04:00") or "utc-04:00",
        "frequency": "1_hourly",
        "area": mt_area(),
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def _months_in_window(year: int, start_date: str, end_date: str) -> list[str]:
    y_start = int(str(start_date)[:4])
    y_end = int(str(end_date)[:4])
    y0m = int(str(start_date)[5:7]) if year == y_start else 1
    y1m = int(str(end_date)[5:7]) if year == y_end else 12
    return [f"{m:02d}" for m in range(y0m, y1m + 1)]


def download_era5_year_stat(
    year: str,
    statistic: str,
    target: Path,
    months: list[str] | None = None,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1000:
        log.info("ERA5 cache: %s", target.name)
        return _unzip_if_needed(target)
    client = _client()
    req = build_era5_request(year, months or MONTHS, statistic)
    log.info(
        "CDS retrieve %s %s meses=%s → %s",
        year,
        statistic,
        ",".join(months or MONTHS),
        target.name,
    )
    try:
        client.retrieve(DATASET, req, str(target))
    except Exception:
        req.pop("download_format", None)
        req.pop("data_format", None)
        req["format"] = "netcdf"
        client.retrieve(DATASET, req, str(target))
    return _unzip_if_needed(target)


def fetch_era5_land_municipal(
    municipios: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    cache_dir: Path | None = None,
) -> pd.DataFrame:
    if municipios is None or municipios.empty:
        return pd.DataFrame()
    if not has_cds_credentials():
        raise RuntimeError(
            "Sem credencial CDS. Defina COPERNICUS_CDS_KEY (climate.copernicus.eu) "
            "ou ~/.cdsapirc. Não use a chave CAMS/ADS neste conector."
        )

    cache_dir = cache_dir or (APP_CONFIG.output_dir / "star" / "era5")
    y0 = int(str(start_date)[:4])
    y1 = int(str(end_date)[:4])
    parts: dict[str, list[pd.DataFrame]] = {}
    for year in range(y0, y1 + 1):
        ys = str(year)
        months = _months_in_window(year, start_date, end_date)
        for statistic, col in STATS:
            tag = f"{ys}_{''.join(months)}" if months != MONTHS else ys
            raw = cache_dir / f"era5land_{col}_{tag}.nc"
            nc = download_era5_year_stat(ys, statistic, raw, months=months)
            parts.setdefault(col, [])
            parts[col].append(amostrar_netcdf_municipios(nc, municipios, col))

    merged = None
    for col, frames in parts.items():
        df = pd.concat(frames, ignore_index=True)
        df = df[(df["data"] >= start_date) & (df["data"] <= end_date)]
        if merged is None:
            merged = df
        else:
            merged = merged.merge(df, on=["cod_ibge", "municipio", "data"], how="outer")
    if merged is None or merged.empty:
        return pd.DataFrame()
    merged["fonte"] = "copernicus_era5_land"
    return merged
