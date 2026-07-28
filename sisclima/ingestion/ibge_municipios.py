from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from sisclima.core.config import APP_CONFIG, env
from sisclima.core.http_client import USER_AGENT, ssl_verify
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
    """Sessão IBGE com User-Agent institucional (auditável na rede SES)."""
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    # Redes corporativas SES/MT podem exigir certificado do proxy — só desliga com env explícito.
    s.verify = ssl_verify("IBGE_SSL_VERIFY", True)
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
    """Carrega municípios reais de MT.

    Ordem:
    1) GeoJSON processado local (completo)
    2) Cache IBGE
    3) CSV territorial completo (>=50 municípios)
    4) API IBGE (com fallback SSL)
    5) CSV sample (último recurso)
    """
    cache_path = APP_CONFIG.root / "data" / "raw" / "ibge" / "municipios_mt_ibge.csv"
    geo_cache_path = APP_CONFIG.root / "data" / "raw" / "ibge" / "malha_municipios_mt.geojson"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    geojson_candidates = [
        APP_CONFIG.root / "data" / "processed" / "municipios_mt_2025_simplificado.geojson",
        APP_CONFIG.root / "data" / "processed" / "municipios_mt_2025.geojson",
        geo_cache_path,
    ]
    for gj_path in geojson_candidates:
        if not gj_path.exists() or force:
            continue
        try:
            geojson = json.loads(gj_path.read_text(encoding="utf-8"))
            rows = []
            for feat in geojson.get("features", []):
                props = feat.get("properties", {}) or {}
                raw_id = (
                    props.get("cod_ibge")
                    or props.get("CD_MUN")
                    or props.get("codarea")
                    or props.get("id")
                )
                try:
                    cod_ibge = int(str(raw_id).replace(".0", ""))
                except Exception:
                    cod_ibge = None
                nome = props.get("municipio") or props.get("NM_MUN") or props.get("nome")
                lat = props.get("lat")
                lon = props.get("lon")
                if lat is None or lon is None:
                    lat, lon = _centroid_from_geometry(feat.get("geometry") or {})
                rows.append(
                    {
                        "cod_ibge": cod_ibge,
                        "municipio": nome,
                        "uf": props.get("uf", "MT"),
                        "lat": lat,
                        "lon": lon,
                        "populacao": props.get("populacao_2025") or props.get("populacao"),
                        "regional_saude": props.get("regiao_geografica_imediata"),
                    }
                )
            df = pd.DataFrame(rows).dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")
            if len(df) >= 50:
                log.info("Municípios carregados de %s (%s)", gj_path.name, len(df))
                return normalize_cols(df)
        except Exception as e:
            log.warning("Falha ao ler %s: %s", gj_path, e)

    if cache_path.exists() and not force:
        df = normalize_cols(pd.read_csv(cache_path))
        if len(df) >= 50:
            return df

    # CSV completo primeiro; sample só no fim.
    input_candidates = [
        APP_CONFIG.root / "data" / "input" / "municipios_mt_base_2025.csv",
        APP_CONFIG.municipios_csv,
        APP_CONFIG.input_dir / "municipios_mt.csv",
        APP_CONFIG.input_dir / "municipios_metadata.csv",
        APP_CONFIG.root / "municipios_mt.csv",
    ]
    complete_csv = None
    sample_csv = None
    for path in input_candidates:
        if not path.exists():
            continue
        df = normalize_cols(pd.read_csv(path, sep=None, engine="python"))
        if not {"cod_ibge", "municipio"}.issubset(set(df.columns)):
            continue
        if len(df) >= 50:
            complete_csv = df
            break
        if sample_csv is None:
            sample_csv = df

    if complete_csv is not None and not force:
        return complete_csv

    mun = fetch_municipios_ibge()
    geo, geojson = fetch_malha_municipal_ibge()
    if not mun.empty and not geo.empty and "cod_ibge" in geo.columns:
        mun = mun.merge(geo[["cod_ibge", "lat", "lon"]], on="cod_ibge", how="left")
    if not mun.empty:
        mun.to_csv(cache_path, index=False, encoding="utf-8-sig")
        if geojson:
            geo_cache_path.write_text(json.dumps(geojson), encoding="utf-8")
        return mun

    if sample_csv is not None:
        log.warning("Usando CSV municipal incompleto (%s municípios).", len(sample_csv))
        return sample_csv
    return pd.DataFrame()


def get_municipios_operacionais() -> pd.DataFrame:
    force = as_bool(env("REFRESH_IBGE_MUNICIPIOS", "false"), False)
    df = load_or_refresh_municipios(force=force)
    if df.empty:
        log.warning("Municípios IBGE indisponíveis. Usando município padrão do APP_CONFIG.")
        return pd.DataFrame([{"cod_ibge": None, "municipio": APP_CONFIG.municipio, "lat": APP_CONFIG.lat, "lon": APP_CONFIG.lon, "uf": "MT"}])
    return df
