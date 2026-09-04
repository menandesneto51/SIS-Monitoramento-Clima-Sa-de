"""Open-Meteo Archive — série diária municipal para EHF/GeoCalor."""
from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd

from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.openmeteo import _as_locations

log = get_logger(__name__)

DAILY_VARS = (
    "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
    "relative_humidity_2m_mean,precipitation_sum"
)


def default_window(years: int = 5) -> tuple[str, str]:
    end = date.today() - timedelta(days=1)
    start = end.replace(year=end.year - int(years)) - timedelta(days=40)
    return start.isoformat(), end.isoformat()


def _payload_to_daily(js: dict, municipio: str | None, cod_ibge, lat: float, lon: float) -> pd.DataFrame:
    daily = pd.DataFrame(js.get("daily") or {})
    if daily.empty:
        return pd.DataFrame()
    daily = daily.rename(
        columns={
            "time": "data",
            "temperature_2m_max": "tmax",
            "temperature_2m_min": "tmin",
            "temperature_2m_mean": "tmedia",
            "relative_humidity_2m_mean": "umidade_media",
            "precipitation_sum": "precipitacao_mm",
        }
    )
    daily["data"] = pd.to_datetime(daily["data"], errors="coerce").dt.strftime("%Y-%m-%d")
    daily["cod_ibge"] = str(cod_ibge).replace(".0", "").zfill(7) if cod_ibge is not None else None
    daily["municipio"] = municipio or ""
    daily["lat"] = lat
    daily["lon"] = lon
    daily["fonte"] = "openmeteo_archive"
    return daily


def _request_archive(lats: list[float], lons: list[float], start: str, end: str) -> list[dict]:
    base = env("OPENMETEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive")
    params = {
        "latitude": ",".join(f"{x:.5f}" for x in lats),
        "longitude": ",".join(f"{x:.5f}" for x in lons),
        "start_date": start,
        "end_date": end,
        "daily": DAILY_VARS,
        "timezone": APP_CONFIG.timezone,
    }
    api_key = (env("OPENMETEO_API_KEY", "") or "").strip()
    if api_key:
        params["apikey"] = api_key
    last_err = None
    for attempt in range(8):
        r = http_get(
            base,
            params=params,
            timeout=120,
            ssl_env_key="OPENMETEO_SSL_VERIFY",
            retries=0,
        )
        if r.status_code == 429:
            wait = min(90.0, 12.0 * (attempt + 1))
            log.warning("Open-Meteo Archive 429 — aguardando %.0fs (tentativa %s)", wait, attempt + 1)
            time.sleep(wait)
            last_err = r
            continue
        r.raise_for_status()
        return _as_locations(r.json())
    if last_err is not None:
        last_err.raise_for_status()
    raise RuntimeError("Archive sem resposta")


def fetch_openmeteo_archive_municipios(
    municipios: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    max_municipios: int | None = None,
) -> pd.DataFrame:
    if not as_bool(env("USE_OPENMETEO", "true"), True):
        return pd.DataFrame()
    if municipios is None or municipios.empty or not {"lat", "lon"}.issubset(municipios.columns):
        return pd.DataFrame()

    dfm = municipios.dropna(subset=["lat", "lon"]).copy()
    if "cod_ibge" in dfm.columns:
        dfm["cod_ibge"] = dfm["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
        dfm = dfm.drop_duplicates("cod_ibge")
    if max_municipios:
        dfm = dfm.head(int(max_municipios))

    size = max(1, int(env("OPENMETEO_ARCHIVE_BATCH_SIZE", "1") or 1))
    pause = float(env("OPENMETEO_ARCHIVE_PAUSE_S", "2.0") or 2.0)
    frames: list[pd.DataFrame] = []

    for start in range(0, len(dfm), size):
        chunk = dfm.iloc[start : start + size]
        rows = chunk.to_dict("records")
        try:
            payloads = _request_archive(
                [float(r["lat"]) for r in rows],
                [float(r["lon"]) for r in rows],
                start_date,
                end_date,
            )
            if len(payloads) != len(rows):
                raise RuntimeError(f"Archive lote: {len(payloads)} respostas para {len(rows)} municípios")
            for row, payload in zip(rows, payloads):
                got = _payload_to_daily(
                    payload,
                    str(row.get("municipio") or ""),
                    row.get("cod_ibge"),
                    float(row["lat"]),
                    float(row["lon"]),
                )
                if not got.empty:
                    frames.append(got)
            time.sleep(pause)
        except Exception as exc:
            log.warning(
                "Lote archive falhou (%s–%s): %s — município a município",
                start + 1,
                start + len(chunk),
                exc,
            )
            for row in rows:
                try:
                    payloads = _request_archive(
                        [float(row["lat"])],
                        [float(row["lon"])],
                        start_date,
                        end_date,
                    )
                    if payloads:
                        got = _payload_to_daily(
                            payloads[0],
                            str(row.get("municipio") or ""),
                            row.get("cod_ibge"),
                            float(row["lat"]),
                            float(row["lon"]),
                        )
                        if not got.empty:
                            frames.append(got)
                    time.sleep(max(pause, 0.4))
                except Exception as one_exc:
                    log.warning("Archive falhou para %s: %s", row.get("municipio"), one_exc)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if not out.empty:
        log.info(
            "Open-Meteo Archive: %s municípios · %s a %s · %s linhas",
            int(out["cod_ibge"].nunique()),
            start_date,
            end_date,
            len(out),
        )
    return out
