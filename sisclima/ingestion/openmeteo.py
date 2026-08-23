from __future__ import annotations
import time
import pandas as pd
from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

SOIL_HOURLY = (
    "soil_moisture_0_to_1cm,"
    "soil_moisture_1_to_3cm,"
    "soil_moisture_3_to_9cm"
)


def _hourly_soil_daily_means(js: dict) -> pd.DataFrame:
    """Agrega umidade do solo horária em média diária."""
    hourly = js.get("hourly") or {}
    if not hourly or "time" not in hourly:
        return pd.DataFrame()
    hdf = pd.DataFrame(hourly)
    hdf["time"] = pd.to_datetime(hdf["time"], errors="coerce")
    hdf = hdf.dropna(subset=["time"])
    if hdf.empty:
        return pd.DataFrame()
    hdf["data"] = hdf["time"].dt.strftime("%Y-%m-%d")
    rename = {
        "soil_moisture_0_to_1cm": "umidade_solo_0_1cm",
        "soil_moisture_1_to_3cm": "umidade_solo_1_3cm",
        "soil_moisture_3_to_9cm": "umidade_solo_3_9cm",
    }
    hdf = hdf.rename(columns={k: v for k, v in rename.items() if k in hdf.columns})
    cols = [c for c in ["umidade_solo_0_1cm", "umidade_solo_1_3cm", "umidade_solo_3_9cm"] if c in hdf.columns]
    if not cols:
        return pd.DataFrame()
    for c in cols:
        hdf[c] = pd.to_numeric(hdf[c], errors="coerce")
    return hdf.groupby("data", as_index=False)[cols].mean()


def _as_locations(js) -> list[dict]:
    if isinstance(js, list):
        return [x for x in js if isinstance(x, dict)]
    if isinstance(js, dict):
        return [js]
    return []


def _daily_from_payload(js: dict, municipio: str | None, cod_ibge, lat: float, lon: float) -> pd.DataFrame:
    daily = pd.DataFrame(js.get("daily", {}))
    if daily.empty:
        return pd.DataFrame()
    daily = daily.rename(
        columns={
            "time": "data",
            "temperature_2m_max": "tmax",
            "temperature_2m_min": "tmin",
            "relative_humidity_2m_mean": "umidade_media",
            "wind_speed_10m_max": "vento_max",
            "precipitation_sum": "precipitacao_mm",
            "precipitation_hours": "precipitacao_horas",
        }
    )
    if "precipitacao_mm" in daily.columns:
        daily["chuva_mm"] = daily["precipitacao_mm"]
    daily["data"] = pd.to_datetime(daily["data"], errors="coerce").dt.strftime("%Y-%m-%d")

    soil = _hourly_soil_daily_means(js)
    if not soil.empty:
        daily = daily.merge(soil, on="data", how="left")
        daily["fonte_solo"] = "openmeteo"

    daily["cod_ibge"] = cod_ibge
    daily["municipio"] = municipio or APP_CONFIG.municipio
    daily["lat"] = lat
    daily["lon"] = lon
    daily["fonte"] = "openmeteo"
    return daily


def _past_days(default: int = 7) -> int:
    """Dias observados recentes (API forecast past_days) — cobre a SE em curso."""
    try:
        return max(0, min(92, int(env("OPENMETEO_PAST_DAYS", str(default)) or default)))
    except (TypeError, ValueError):
        return default


def _forecast_params(lats: list[float], lons: list[float], days: int, past_days: int | None = None) -> dict:
    hourly = (
        "temperature_2m,relative_humidity_2m,wind_speed_10m,shortwave_radiation,"
        f"apparent_temperature,precipitation,{SOIL_HOURLY}"
    )
    past = _past_days() if past_days is None else max(0, int(past_days))
    params = {
        "latitude": ",".join(f"{x:.5f}" for x in lats),
        "longitude": ",".join(f"{x:.5f}" for x in lons),
        "hourly": hourly,
        "daily": (
            "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
            "wind_speed_10m_max,precipitation_sum,precipitation_hours"
        ),
        "forecast_days": days,
        "timezone": APP_CONFIG.timezone,
    }
    if past > 0:
        params["past_days"] = past
    return params


def _request_forecast(
    lats: list[float],
    lons: list[float],
    days: int,
    past_days: int | None = None,
) -> list[dict]:
    base = env("OPENMETEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
    r = http_get(
        base,
        params=_forecast_params(lats, lons, days, past_days=past_days),
        timeout=90,
        ssl_env_key="OPENMETEO_SSL_VERIFY",
    )
    r.raise_for_status()
    return _as_locations(r.json())


def _batch_size(env_key: str = "OPENMETEO_BATCH_SIZE", default: int = 20) -> int:
    try:
        return max(1, int(env(env_key, str(default)) or default))
    except (TypeError, ValueError):
        return default


def _fetch_one(
    lat: float,
    lon: float,
    municipio: str | None = None,
    cod_ibge=None,
    days: int = 7,
    past_days: int | None = None,
) -> pd.DataFrame:
    payloads = _request_forecast([lat], [lon], days, past_days=past_days)
    if not payloads:
        return pd.DataFrame()
    return _daily_from_payload(payloads[0], municipio, cod_ibge, lat, lon)


def _fetch_chunk(chunk: pd.DataFrame, days: int, past_days: int | None = None) -> pd.DataFrame:
    rows = chunk.to_dict("records")
    lats = [float(r["lat"]) for r in rows]
    lons = [float(r["lon"]) for r in rows]
    payloads = _request_forecast(lats, lons, days, past_days=past_days)
    if len(payloads) != len(rows):
        raise RuntimeError(f"Open-Meteo lote: {len(payloads)} respostas para {len(rows)} municípios")
    frames = [
        _daily_from_payload(
            payload,
            str(row.get("municipio") or ""),
            row.get("cod_ibge"),
            float(row["lat"]),
            float(row["lon"]),
        )
        for row, payload in zip(rows, payloads)
    ]
    frames = [f for f in frames if f is not None and not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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

    Lotes (OPENMETEO_BATCH_SIZE, padrão 20) evitam 503 da API gratuita.
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
    size = _batch_size()
    past = _past_days()
    frames = []
    pause = float(env("OPENMETEO_PAUSE_S", "0.35") or 0.35)
    for start in range(0, len(dfm), size):
        chunk = dfm.iloc[start : start + size]
        try:
            got = _fetch_chunk(chunk, days, past_days=past)
            if not got.empty:
                frames.append(got)
            time.sleep(pause)
        except Exception as exc:
            log.warning(
                "Lote Open-Meteo falhou (%s–%s): %s — tentando município a município",
                start + 1,
                start + len(chunk),
                exc,
            )
            for _, m in chunk.iterrows():
                try:
                    frames.append(
                        _fetch_one(
                            float(m["lat"]),
                            float(m["lon"]),
                            str(m.get("municipio") or ""),
                            m.get("cod_ibge"),
                            days,
                            past_days=past,
                        )
                    )
                    time.sleep(max(pause, 0.4))
                except Exception as one_exc:
                    log.warning("Falha Open-Meteo para %s: %s", m.get("municipio"), one_exc)
    out = [f for f in frames if f is not None and not f.empty]
    result = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    if not result.empty and "cod_ibge" in result.columns:
        dmin = str(result["data"].min()) if "data" in result.columns else "?"
        dmax = str(result["data"].max()) if "data" in result.columns else "?"
        log.info(
            "Open-Meteo: %s municípios · past_days=%s · forecast_days=%s · janela %s a %s",
            int(result["cod_ibge"].nunique()),
            past,
            days,
            dmin,
            dmax,
        )
    return result
