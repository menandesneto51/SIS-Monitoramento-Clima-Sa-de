"""Testes unitários do conector ERA5-Land / CDS (sem chamada ao CDS)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sisclima.ingestion.era5_cds import (
    _kelvin_to_c,
    _months_in_window,
    _nearest,
    amostrar_netcdf_municipios,
    build_era5_request,
)


def test_kelvin_to_c_detects_kelvin():
    arr = np.array([300.0, 310.0])
    out = _kelvin_to_c(arr)
    assert out[0] == pytest.approx(26.85, abs=0.01)


def test_kelvin_to_c_keeps_celsius():
    arr = np.array([26.0, 38.0])
    out = _kelvin_to_c(arr)
    assert out[0] == pytest.approx(26.0)


def test_nearest():
    grid = np.array([-18.0, -15.5, -12.0])
    assert _nearest(grid, -15.4) == 1


def test_months_in_window_partial():
    assert _months_in_window(2024, "2024-01-01", "2024-01-31") == ["01"]
    assert _months_in_window(2024, "2023-11-01", "2024-02-15") == ["01", "02"]
    assert _months_in_window(2023, "2023-11-01", "2024-02-15") == ["11", "12"]


def test_build_era5_request_shape():
    req = build_era5_request("2024", ["01"], "daily_maximum")
    assert req["variable"] == ["2m_temperature"]
    assert req["daily_statistic"] == "daily_maximum"
    assert len(req["area"]) == 4


def test_amostrar_netcdf_municipios(tmp_path: Path):
    xr = pytest.importorskip("xarray")
    times = pd.date_range("2024-01-01", periods=3, freq="D")
    lat = np.array([-15.6, -15.5, -15.4])
    lon = np.array([-56.1, -56.0, -55.9])
    # Kelvin cube (time, lat, lon)
    cube = np.full((3, 3, 3), 300.0)
    cube[:, 1, 1] = 310.0
    ds = xr.Dataset(
        {"t2m": (("valid_time", "latitude", "longitude"), cube)},
        coords={"valid_time": times, "latitude": lat, "longitude": lon},
    )
    nc = tmp_path / "t2m.nc"
    ds.to_netcdf(nc)
    mun = pd.DataFrame(
        [
            {"cod_ibge": "5103403", "municipio": "Cuiabá", "lat": -15.5, "lon": -56.0},
        ]
    )
    out = amostrar_netcdf_municipios(nc, mun, "tmax")
    assert len(out) == 3
    assert out["tmax"].iloc[0] == pytest.approx(36.85, abs=0.05)
