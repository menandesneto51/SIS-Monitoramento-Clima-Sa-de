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

    # Rede corporativa / proxy com certificado autoassinado na cadeia.
    # cdsapi/requests usam verify=; o monkeypatch de ssl NÃO basta.
    ssl_flag = (env("COPERNICUS_CDS_SSL_VERIFY", "true") or "true").strip().lower()
    verify_ssl = ssl_flag not in {"0", "false", "no", "off"}
    if not verify_ssl:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:  # noqa: BLE001
            pass

    key = cds_key()
    url = (env("COPERNICUS_CDS_URL", "") or "").strip() or "https://cds.climate.copernicus.eu/api"
    kwargs: dict = {"verify": verify_ssl}
    if key:
        kwargs.update({"url": url, "key": key})
    return cdsapi.Client(**kwargs)


def dismiss_stale_cds_jobs(*, keep_job_ids: set[str] | None = None, max_age_hours: float = 2.0) -> list[str]:
    """Remove requests CDS em ``accepted`` antigos que bloqueiam a fila do usuário."""
    from datetime import datetime, timezone

    keep_job_ids = keep_job_ids or set()
    client = _client()
    api = client.client
    jobs = api.get_jobs(limit=50).json.get("jobs", [])
    now = datetime.now(timezone.utc)
    stale_ids: list[str] = []
    for job in jobs:
        if job.get("status") != "accepted":
            continue
        jid = str(job.get("jobID") or "")
        if not jid or jid in keep_job_ids:
            continue
        created_raw = str(job.get("created") or "")
        try:
            created = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except ValueError:
            created = now
        age_h = (now - created.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_h >= max_age_hours:
            stale_ids.append(jid)
    if stale_ids:
        log.warning("Dismiss CDS jobs órfãos: %s", ", ".join(x[:8] for x in stale_ids))
        api.delete(*stale_ids)
    return stale_ids


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



def _normalize_months(months: list[str] | None) -> list[str]:
    return list(months or MONTHS)


def _request_matches_job(req: dict, remote_req: dict) -> bool:
    if not remote_req:
        return False
    if str(remote_req.get("year")) != str(req.get("year")):
        return False
    if str(remote_req.get("daily_statistic") or "") != str(req.get("daily_statistic") or ""):
        return False
    rm = remote_req.get("month") or []
    if isinstance(rm, str):
        rm = [rm]
    want = list(req.get("month") or [])
    return sorted(str(x) for x in rm) == sorted(str(x) for x in want)


def _find_matching_cds_job(api, req: dict) -> str | None:
    """Reusa accepted/running/successful com o mesmo year/month/statistic."""
    try:
        jobs = api.get_jobs(limit=50).json.get("jobs", [])
    except Exception:  # noqa: BLE001
        return None
    preferred = {"successful": 0, "running": 1, "accepted": 2}
    matches: list[tuple[int, str, str]] = []
    for job in jobs:
        status = str(job.get("status") or "")
        if status not in preferred:
            continue
        jid = str(job.get("jobID") or "")
        if not jid:
            continue
        remote_req = {}
        meta = job.get("metadata") or {}
        remote_req = (meta.get("request") or {}).get("ids") or meta.get("request") or {}
        if not _request_matches_job(req, remote_req):
            # Lista de jobs às vezes não traz ids; consulta só candidatos recentes accepted/running
            if status not in {"accepted", "running"}:
                continue
            try:
                remote = api.get_remote(jid)
                remote_req = getattr(remote, "request", None) or {}
                if not remote_req:
                    rmeta = (getattr(remote, "json", None) or {}).get("metadata") or {}
                    remote_req = (rmeta.get("request") or {}).get("ids") or rmeta.get("request") or {}
            except Exception:  # noqa: BLE001
                continue
        if _request_matches_job(req, remote_req):
            matches.append((preferred[status], str(job.get("created") or ""), jid))
    if not matches:
        return None
    matches.sort()
    # Mantém o melhor; dismiss accepted duplicados do mesmo pedido
    keep = matches[0][2]
    dup_accepted = [jid for rank, _, jid in matches if rank == 2 and jid != keep]
    if dup_accepted:
        try:
            log.warning("Dismiss CDS accepted duplicados: %s", ", ".join(x[:8] for x in dup_accepted))
            api.delete(*dup_accepted)
        except Exception as exc:  # noqa: BLE001
            log.warning("Falha ao dismiss duplicados CDS: %s", exc)
    return keep


def download_era5_year_stat(
    year: str,
    statistic: str,
    target: Path,
    months: list[str] | None = None,
) -> Path:
    """Baixa estatística diária ERA5-Land (mês ou ano) para ``target``.

    Usa submit + poll + download_results (em vez de ``retrieve`` bloqueante),
    porque com proxy/SSL corporativo o wait interno do cdsapi às vezes não
    detecta ``successful`` e nunca grava o arquivo.
    """
    import time

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1000:
        log.info("ERA5 cache: %s", target.name)
        return _unzip_if_needed(target)

    client = _client()
    api = client.client
    req = build_era5_request(year, months or MONTHS, statistic)
    existing = _find_matching_cds_job(api, req)
    if existing:
        log.info("CDS reusando job existente %s → %s", existing[:8], target.name)
        job_id = existing
    else:
        job_id = None
    log.info(
        "CDS retrieve %s %s meses=%s → %s",
        year,
        statistic,
        ",".join(months or MONTHS),
        target.name,
    )

    def _submit(payload: dict) -> str:
        remote = api.submit(DATASET, payload)
        jid = getattr(remote, "request_id", None) or getattr(remote, "job_id", None)
        if not jid and hasattr(remote, "json"):
            jid = (remote.json or {}).get("jobID") or (remote.json or {}).get("job_id")
        if not jid:
            # fallback: último accepted
            jobs = api.get_jobs(limit=5).json.get("jobs", [])
            for job in jobs:
                if job.get("status") in {"accepted", "running", "successful"}:
                    jid = job.get("jobID")
                    break
        if not jid:
            raise RuntimeError("CDS submit sem jobID")
        return str(jid)

    if job_id is None:
        try:
            job_id = _submit(req)
        except Exception:
            req.pop("download_format", None)
            req.pop("data_format", None)
            req["format"] = "netcdf"
            job_id = _submit(req)

    log.info("CDS job %s accepted/submitted → aguardando", job_id[:8])
    # Poll explícito (até ~10 h; fila CDS costuma levar 30–90 min)
    deadline = time.time() + 10 * 3600
    last_status = ""
    while time.time() < deadline:
        status = "unknown"
        try:
            remote = api.get_remote(job_id)
            status = str(getattr(remote, "status", None) or "unknown").lower()
            if status == "unknown":
                reply = getattr(remote, "reply", None) or getattr(remote, "json", None) or {}
                if isinstance(reply, dict):
                    status = str(reply.get("status") or "unknown").lower()
        except OSError as exc:
            log.warning("CDS get_remote OSError (%s); retry em 30s", exc)
            time.sleep(30)
            continue
        except Exception as exc:  # noqa: BLE001
            # Fallback: lista recente (job antigo pode sair do topo)
            try:
                jobs = api.get_jobs(limit=50).json.get("jobs", [])
                match = next((j for j in jobs if j.get("jobID") == job_id), None)
                status = str((match or {}).get("status") or "unknown").lower()
            except OSError as exc2:
                log.warning("CDS poll fallback OSError (%s); retry em 30s", exc2)
                time.sleep(30)
                continue
            if status == "unknown":
                log.warning("CDS poll %s: %s", job_id[:8], exc)
        if status != last_status:
            log.info("CDS job %s status=%s", job_id[:8], status)
            last_status = status
        if status == "successful":
            # OneDrive/Windows: download_results no destino final às vezes dá Errno 22.
            # Baixa em %TEMP% e copia.
            import shutil
            import tempfile

            tmp_dir = Path(tempfile.gettempdir()) / "araras_era5_cds"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / target.name
            last_err: Exception | None = None
            for attempt in range(1, 4):
                try:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except OSError:
                            pass
                    api.download_results(job_id, str(tmp_path))
                    if not tmp_path.exists() or tmp_path.stat().st_size < 1000:
                        raise RuntimeError(f"Download CDS vazio: {tmp_path}")
                    final = _unzip_if_needed(tmp_path)
                    shutil.copy2(final, target)
                    if target.stat().st_size < 1000:
                        raise RuntimeError(f"Cópia CDS vazia: {target}")
                    return _unzip_if_needed(target)
                except Exception as exc:  # noqa: BLE001
                    last_err = exc
                    log.warning("CDS download tentativa %s falhou: %s", attempt, exc)
                    time.sleep(5 * attempt)
            raise RuntimeError(f"Falha ao gravar {target.name}: {last_err}")
        if status in {"failed", "rejected", "dismissed"}:
            raise RuntimeError(f"CDS job {job_id} status={status}")
        time.sleep(30)

    raise TimeoutError(f"CDS job {job_id} não concluiu em 10h (último status={last_status})")


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
    cache_dir.mkdir(parents=True, exist_ok=True)
    y0 = int(str(start_date)[:4])
    y1 = int(str(end_date)[:4])
    parts: dict[str, list[pd.DataFrame]] = {}
    for year in range(y0, y1 + 1):
        ys = str(year)
        months = _months_in_window(year, start_date, end_date)
        for statistic, col in STATS:
            yearly = cache_dir / f"era5land_{col}_{ys}.nc"
            # Atalho: ano civil completo já em cache (ex.: 2020)
            if months == MONTHS and yearly.exists() and yearly.stat().st_size > 1000:
                log.info("ERA5 ano em cache: %s", yearly.name)
                nc = _unzip_if_needed(yearly)
                parts.setdefault(col, []).append(amostrar_netcdf_municipios(nc, municipios, col))
                continue
            # Mês a mês — retomável se a fila CDS travar
            for month in months:
                raw = cache_dir / f"era5land_{col}_{ys}_{month}.nc"
                nc = download_era5_year_stat(ys, statistic, raw, months=[month])
                parts.setdefault(col, []).append(amostrar_netcdf_municipios(nc, municipios, col))

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
    # Uma linha por município/dia (último valor se houver sobreposição ano/mês)
    merged = merged.sort_values(["cod_ibge", "data"]).drop_duplicates(["cod_ibge", "data"], keep="last")
    merged["fonte"] = "copernicus_era5_land"
    return merged


def inventariar_cache_era5(
    *,
    start_date: str,
    end_date: str,
    cache_dir: Path | None = None,
) -> dict:
    """Lista o que já existe e o que falta no cache mensal/anual ERA5."""
    cache_dir = cache_dir or (APP_CONFIG.output_dir / "star" / "era5")
    y0 = int(str(start_date)[:4])
    y1 = int(str(end_date)[:4])
    presentes: list[str] = []
    faltantes: list[dict[str, str]] = []
    for year in range(y0, y1 + 1):
        ys = str(year)
        months = _months_in_window(year, start_date, end_date)
        for statistic, col in STATS:
            yearly = cache_dir / f"era5land_{col}_{ys}.nc"
            if months == MONTHS and yearly.exists() and yearly.stat().st_size > 1000:
                presentes.append(yearly.name)
                continue
            for month in months:
                raw = cache_dir / f"era5land_{col}_{ys}_{month}.nc"
                if raw.exists() and raw.stat().st_size > 1000:
                    presentes.append(raw.name)
                else:
                    faltantes.append(
                        {"year": ys, "month": month, "statistic": statistic, "col": col, "file": raw.name}
                    )
    # Ano civil completo sem nenhum mês: 1 retrieve anual em vez de 12
    faltantes = coalesce_faltantes_anuais(faltantes)
    return {
        "cache_dir": str(cache_dir),
        "n_presentes": len(presentes),
        "n_faltantes": len(faltantes),
        "presentes": presentes,
        "faltantes": faltantes,
    }


def coalesce_faltantes_anuais(faltantes: list[dict[str, str]]) -> list[dict[str, str]]:
    """Se faltam os 12 meses de um (year, col), troca por um job anual."""
    from collections import defaultdict

    by_key: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for job in faltantes:
        by_key[(job["year"], job["col"], job["statistic"])].append(job)

    out: list[dict[str, str]] = []
    for (year, col, statistic), jobs in by_key.items():
        months = sorted({j["month"] for j in jobs})
        if months == MONTHS:
            out.append(
                {
                    "year": year,
                    "month": "all",
                    "statistic": statistic,
                    "col": col,
                    "file": f"era5land_{col}_{year}.nc",
                }
            )
        else:
            out.extend(sorted(jobs, key=lambda j: j["month"]))
    # Ordem estável: ano, variável (tmin/tmedia/tmax), mês
    col_order = {c: i for i, (_, c) in enumerate(STATS)}
    out.sort(key=lambda j: (j["year"], col_order.get(j["col"], 99), j["month"]))
    return out
