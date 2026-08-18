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


def _as_locations(js) -> list[dict]:
    if isinstance(js, list):
        return [x for x in js if isinstance(x, dict)]
    if isinstance(js, dict):
        return [js]
    return []


def _current_from_payload(js: dict, municipio: str | None, cod_ibge, lat: float, lon: float) -> pd.DataFrame:
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


def _hourly_from_payload(js: dict, municipio: str | None, cod_ibge, lat: float, lon: float) -> pd.DataFrame:
    hourly = js.get("hourly") or {}
    times = hourly.get("time") or []
    if not times:
        return pd.DataFrame()
    raw = pd.DataFrame(
        {
            "data": pd.to_datetime(times, errors="coerce"),
            "pm25_ugm3": hourly.get("pm2_5"),
            "pm10_ugm3": hourly.get("pm10"),
            "o3_ugm3": hourly.get("ozone"),
            "no2_ugm3": hourly.get("nitrogen_dioxide"),
            "so2_ugm3": hourly.get("sulphur_dioxide"),
            "co_mgm3": hourly.get("carbon_monoxide"),
            "european_aqi": hourly.get("european_aqi"),
        }
    )
    raw = raw.dropna(subset=["data"])
    if raw.empty:
        return pd.DataFrame()
    if "co_mgm3" in raw.columns:
        raw["co_mgm3"] = pd.to_numeric(raw["co_mgm3"], errors="coerce") / 1000.0
    raw["data"] = raw["data"].dt.strftime("%Y-%m-%d")
    num = [c for c in ["pm25_ugm3", "pm10_ugm3", "o3_ugm3", "no2_ugm3", "so2_ugm3", "co_mgm3", "european_aqi"] if c in raw.columns]
    out = raw.groupby("data", as_index=False)[num].mean(numeric_only=True)
    out["cod_ibge"] = cod_ibge
    out["municipio"] = municipio or APP_CONFIG.municipio
    out["lat"] = lat
    out["lon"] = lon
    out["fonte"] = "openmeteo_air_quality"
    return out


def _one(lat: float, lon: float, municipio: str | None, cod_ibge) -> pd.DataFrame:
    url = env("OPENMETEO_AIRQUALITY_URL", DEFAULT_AQ_URL) or DEFAULT_AQ_URL
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide,european_aqi",
        "timezone": APP_CONFIG.timezone,
    }
    r = _ssl_get(url, params)
    payloads = _as_locations(r.json())
    if not payloads:
        return pd.DataFrame()
    return _current_from_payload(payloads[0], municipio, cod_ibge, lat, lon)


def _daily_series(lat: float, lon: float, municipio: str | None, cod_ibge, past_days: int = 7) -> pd.DataFrame:
    url = env("OPENMETEO_AIRQUALITY_URL", DEFAULT_AQ_URL) or DEFAULT_AQ_URL
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide,european_aqi",
        "past_days": max(1, int(past_days)),
        "forecast_days": 1,
        "timezone": APP_CONFIG.timezone,
    }
    r = _ssl_get(url, params)
    payloads = _as_locations(r.json())
    if not payloads:
        return pd.DataFrame()
    return _hourly_from_payload(payloads[0], municipio, cod_ibge, lat, lon)


def _aq_batch_size() -> int:
    try:
        return max(1, int(env("OPENMETEO_AQ_BATCH_SIZE", "8") or 8))
    except (TypeError, ValueError):
        return 8


def _fetch_aq_chunk(chunk: pd.DataFrame, past_days: int) -> pd.DataFrame:
    url = env("OPENMETEO_AIRQUALITY_URL", DEFAULT_AQ_URL) or DEFAULT_AQ_URL
    rows = chunk.to_dict("records")
    lats = ",".join(f"{float(r['lat']):.5f}" for r in rows)
    lons = ",".join(f"{float(r['lon']):.5f}" for r in rows)
    if past_days and int(past_days) > 0:
        params = {
            "latitude": lats,
            "longitude": lons,
            "hourly": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide,european_aqi",
            "past_days": max(1, int(past_days)),
            "forecast_days": 1,
            "timezone": APP_CONFIG.timezone,
        }
        parse = _hourly_from_payload
    else:
        params = {
            "latitude": lats,
            "longitude": lons,
            "current": "pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,ozone,sulphur_dioxide,european_aqi",
            "timezone": APP_CONFIG.timezone,
        }
        parse = _current_from_payload
    r = _ssl_get(url, params, timeout=90)
    payloads = _as_locations(r.json())
    if len(payloads) != len(rows):
        raise RuntimeError(f"Open-Meteo AQ lote: {len(payloads)} respostas para {len(rows)} municípios")
    frames = [
        parse(payload, str(row.get("municipio") or ""), row.get("cod_ibge"), float(row["lat"]), float(row["lon"]))
        for row, payload in zip(rows, payloads)
    ]
    frames = [f for f in frames if f is not None and not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_openmeteo_air_quality_municipal(municipios: pd.DataFrame, past_days: int = 0) -> pd.DataFrame:
    """PM2,5 por município (Open-Meteo). past_days>0 gera série diária; 0 = snapshot atual."""
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
    size = _aq_batch_size()
    pause = float(env("OPENMETEO_PAUSE_S", "0.35") or 0.35)
    frames: list[pd.DataFrame] = []
    for start in range(0, len(dfm), size):
        chunk = dfm.iloc[start : start + size]
        try:
            got = _fetch_aq_chunk(chunk, past_days)
            if not got.empty:
                frames.append(got)
            time.sleep(pause)
        except Exception as exc:
            log.warning(
                "Lote qualidade do ar falhou (%s–%s): %s — tentando um a um",
                start + 1,
                start + len(chunk),
                exc,
            )
            for _, m in chunk.iterrows():
                try:
                    if past_days and int(past_days) > 0:
                        frames.append(
                            _daily_series(
                                float(m["lat"]),
                                float(m["lon"]),
                                str(m.get("municipio") or ""),
                                m.get("cod_ibge"),
                                past_days=int(past_days),
                            )
                        )
                    else:
                        frames.append(
                            _one(float(m["lat"]), float(m["lon"]), str(m.get("municipio") or ""), m.get("cod_ibge"))
                        )
                    time.sleep(max(pause, 0.4))
                except Exception as one_exc:
                    log.warning("Open-Meteo qualidade do ar falhou para %s: %s", m.get("municipio"), one_exc)
    if not frames:
        return pd.DataFrame()
    out = pd.concat([f for f in frames if f is not None and not f.empty], ignore_index=True)
    log.info(
        "Open-Meteo qualidade do ar: %s municípios",
        int(out["cod_ibge"].nunique()) if "cod_ibge" in out.columns else len(out),
    )
    return out
