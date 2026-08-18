# -*- coding: utf-8 -*-
"""Qualidade do ar municipal via Open-Meteo (PM2,5 / IQA) — fallback sem ADS/CAMS."""
from __future__ import annotations

import time

import pandas as pd

from sisclima.core.config import APP_CONFIG, as_bool, env
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DEFAULT_AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


def _ssl_get(url: str, params: dict, timeout: float = 45):
    try:
        r = http_get(url, params=params, timeout=timeout, ssl_env_key="OPENMETEO_SSL_VERIFY")
        r.raise_for_status()
        return r
    except Exception as exc:
        if "CERTIFICATE" not in str(exc).upper() and "SSL" not in str(exc).upper():
            raise
        r = http_get(url, params=params, timeout=timeout, verify=False)
        r.raise_for_status()
        return r


def _one(lat: float, lon: float, municipio: str | None, cod_ibge) -> pd.DataFrame:
    url = env("OPENMETEO_AIRQUALITY_URL", DEFAULT_AQ_URL) or DEFAULT_AQ_URL
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide,european_aqi",
        "timezone": APP_CONFIG.timezone,
    }
    r = _ssl_get(url, params)
    js = r.json()
    cur = js.get("current") or {}
    if not cur:
        return pd.DataFrame()
    pm25 = cur.get("pm2_5")
    co_ug = cur.get("carbon_monoxide")
    return pd.DataFrame(
        [
            {
                "data": str(cur.get("time") or "")[:10],
                "cod_ibge": cod_ibge,
                "municipio": municipio or APP_CONFIG.municipio,
                "lat": lat,
                "lon": lon,
                "pm25_ugm3": pm25,
                "pm10_ugm3": cur.get("pm10"),
                "o3_ugm3": cur.get("ozone"),
                "no2_ugm3": cur.get("nitrogen_dioxide"),
                "so2_ugm3": cur.get("sulphur_dioxide"),
                "co_mgm3": (float(co_ug) / 1000.0) if co_ug is not None else None,
                "european_aqi": cur.get("european_aqi"),
                "fonte": "openmeteo_air_quality",
            }
        ]
    )


def fetch_openmeteo_air_quality_municipal(municipios: pd.DataFrame) -> pd.DataFrame:
    """PM2,5 atual por município (Open-Meteo Air Quality API)."""
    if not as_bool(env("USE_OPENMETEO_AQ", "true"), True):
        return pd.DataFrame()
    if municipios is None or municipios.empty or not {"lat", "lon"}.issubset(municipios.columns):
        try:
            return _one(APP_CONFIG.lat, APP_CONFIG.lon, APP_CONFIG.municipio, None)
        except Exception as exc:
            log.warning("Open-Meteo qualidade do ar (sede) falhou: %s", exc)
            return pd.DataFrame()

    dfm = municipios.dropna(subset=["lat", "lon"]).copy()
    max_env = env("OPENMETEO_AQ_MAX_MUNICIPIOS")
    if max_env:
        try:
            dfm = dfm.head(int(max_env))
        except Exception:
            pass
    frames: list[pd.DataFrame] = []
    for i, m in dfm.iterrows():
        try:
            frames.append(
                _one(float(m["lat"]), float(m["lon"]), str(m.get("municipio") or ""), m.get("cod_ibge"))
            )
            time.sleep(0.05)
        except Exception as exc:
            log.warning("Open-Meteo qualidade do ar falhou para %s: %s", m.get("municipio"), exc)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    log.info("Open-Meteo qualidade do ar: %s municípios", int(out["cod_ibge"].nunique()) if "cod_ibge" in out.columns else len(out))
    return out
