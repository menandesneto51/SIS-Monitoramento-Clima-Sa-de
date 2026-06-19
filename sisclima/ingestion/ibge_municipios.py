from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from sisclima.core.config import APP_CONFIG, env, as_bool
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols

log = get_logger(__name__)

IBGE_UF_MT = "51"
IBGE_LOCALIDADES_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
IBGE_MALHAS_MUNICIPIOS = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}"
    "?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=municipio"
)


def _flatten_coords(coords: Any):
    """Yield lon/lat pairs from a GeoJSON coordinate object."""
    if not isinstance(coords, list):
        return
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        yield float(coords[0]), float(coords[1])
    else:
        for item in coords:
            yield from _flatten_coords(item)


def _centroid_from_geometry(geom: dict) -> tuple[float | None, float | None]:
    pts = list(_flatten_coords((geom or {}).get("coordinates")))
    if not pts:
        return None, None
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return lat, lon


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "SIS-MT-Clima-Saude/3.0"})
    return s


def fetch_municipios_ibge(uf: str = IBGE_UF_MT, timeout: int = 60) -> pd.DataFrame:
    """Baixa a lista oficial de municípios do IBGE para a UF informada."""
    url = IBGE_LOCALIDADES_MUNICIPIOS.format(uf=uf)
    try:
        r = _session().get(url, timeout=timeout)
        r.raise_for_status()
        rows = []
        for item in r.json():
            micror = item.get("microrregiao") or {}
            mesor = micror.get("mesorregiao") or {}
            rows.append({
                "cod_ibge": int(item.get("id")),
                "municipio": item.get("nome"),
                "uf": "MT",
                "microrregiao": micror.get("nome"),
                "mesorregiao": mesor.get("nome"),
            })
        return pd.DataFrame(rows).sort_values("municipio").reset_index(drop=True)
    except Exception as e:
        log.warning("Falha ao baixar municípios do IBGE: %s", e)
        return pd.DataFrame()


def fetch_malha_municipal_ibge(uf: str = IBGE_UF_MT, timeout: int = 120) -> tuple[pd.DataFrame, dict | None]:
    """Baixa GeoJSON municipal do IBGE e calcula centróides aproximados em Python puro."""
    url = IBGE_MALHAS_MUNICIPIOS.format(uf=uf)
    try:
        r = _session().get(url, timeout=timeout)
        r.raise_for_status()
        geojson = r.json()
        rows = []
        for feat in geojson.get("features", []):
            props = feat.get("properties", {}) or {}
            raw_id = props.get("codarea") or props.get("id") or props.get("CD_MUN") or props.get("cod_mun")
            try:
                cod_ibge = int(str(raw_id))
            except Exception:
                cod_ibge = None
            nome = props.get("nome") or props.get("NM_MUN") or props.get("name")
            lat, lon = _centroid_from_geometry(feat.get("geometry") or {})
            rows.append({"cod_ibge": cod_ibge, "municipio_geo": nome, "lat": lat, "lon": lon})
        return pd.DataFrame(rows), geojson
    except Exception as e:
        log.warning("Falha ao baixar malha municipal do IBGE: %s", e)
        return pd.DataFrame(), None


def load_or_refresh_municipios(force: bool = False) -> pd.DataFrame:
    """Carrega municípios reais de MT. Ordem: CSV real -> cache IBGE -> API IBGE."""
    input_candidates = [APP_CONFIG.municipios_csv, APP_CONFIG.input_dir / "municipios_metadata.csv", APP_CONFIG.input_dir / "municipios_mt.csv", APP_CONFIG.root / "municipios_mt.csv"]
    input_path = next((p for p in input_candidates if p.exists()), input_candidates[0])
    cache_path = APP_CONFIG.root / "data" / "raw" / "ibge" / "municipios_mt_ibge.csv"
    geo_cache_path = APP_CONFIG.root / "data" / "raw" / "ibge" / "malha_municipios_mt.geojson"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.exists() and not force:
        df = normalize_cols(pd.read_csv(input_path, sep=None, engine="python"))
        if {"cod_ibge", "municipio"}.issubset(set(df.columns)):
            return df

    if cache_path.exists() and not force:
        df = normalize_cols(pd.read_csv(cache_path))
        if not df.empty:
            return df

    mun = fetch_municipios_ibge()
    geo, geojson = fetch_malha_municipal_ibge()
    if not mun.empty and not geo.empty and "cod_ibge" in geo.columns:
        mun = mun.merge(geo[["cod_ibge", "lat", "lon"]], on="cod_ibge", how="left")
    if not mun.empty:
        mun.to_csv(cache_path, index=False, encoding="utf-8-sig")
        if geojson:
            geo_cache_path.write_text(json.dumps(geojson), encoding="utf-8")
    return mun


def get_municipios_operacionais() -> pd.DataFrame:
    force = as_bool(env("REFRESH_IBGE_MUNICIPIOS", "false"), False)
    df = load_or_refresh_municipios(force=force)
    if df.empty:
        log.warning("Municípios IBGE indisponíveis. Usando município padrão do APP_CONFIG.")
        return pd.DataFrame([{"cod_ibge": None, "municipio": APP_CONFIG.municipio, "lat": APP_CONFIG.lat, "lon": APP_CONFIG.lon, "uf": "MT"}])
    return df
