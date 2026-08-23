from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from sisclima.core.config import APP_CONFIG, as_bool, env
from sisclima.core.http_client import USER_AGENT, ssl_verify
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols

log = get_logger(__name__)

IBGE_UF_MT = "51"
# Recorte oficial vigente (IBGE): 142 municípios de MT (Boa Esperança do Norte, 5101837).
MT_MUNICIPIOS_OFICIAIS = int(env("MT_MUNICIPIOS_OFICIAIS", "142") or 142)
# Município emancipado sem malha antiga: herda centróide do município de origem até a malha IBGE atualizar.
_PARENT_COORDS = {"5101837": "5106240"}  # Boa Esperança do Norte ← Nova Ubiratã
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


def _parse_municipios_ibge_json(payload) -> pd.DataFrame:
    rows = []
    for item in payload or []:
        micror = item.get("microrregiao") or {}
        mesor = micror.get("mesorregiao") or {}
        rows.append({
            "cod_ibge": int(item.get("id")),
            "municipio": item.get("nome"),
            "uf": "MT",
            "microrregiao": micror.get("nome"),
            "mesorregiao": mesor.get("nome"),
        })
    return pd.DataFrame(rows).sort_values("municipio").reset_index(drop=True) if rows else pd.DataFrame()


def fetch_municipios_ibge(uf: str = IBGE_UF_MT, timeout: int = 60) -> pd.DataFrame:
    """Baixa a lista oficial de municípios do IBGE para a UF informada."""
    url = IBGE_LOCALIDADES_MUNICIPIOS.format(uf=uf)
    sess = _session()
    try:
        r = sess.get(url, timeout=timeout)
        r.raise_for_status()
        return _parse_municipios_ibge_json(r.json())
    except Exception as e:
        log.warning("Falha ao baixar municípios do IBGE (SSL/rede): %s", e)
        try:
            r = sess.get(url, timeout=timeout, verify=False)
            r.raise_for_status()
            log.warning("IBGE localidades obtido sem verificação SSL (proxy SES).")
            return _parse_municipios_ibge_json(r.json())
        except Exception as e2:
            log.warning("Falha ao baixar municípios do IBGE: %s", e2)
            return pd.DataFrame()


def _cod7(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{7})", expand=False)


def _has_nomes_municipais(df: pd.DataFrame) -> bool:
    if df is None or df.empty or "municipio" not in df.columns:
        return False
    nomes = df["municipio"].dropna().astype(str).str.strip()
    nomes = nomes[~nomes.str.lower().isin({"", "none", "nan", "nat", "<na>", "cuiabá", "cuiaba"})]
    # recusa catálogo degenerado (tudo Cuiabá / vazio)
    return int(nomes.nunique()) >= 50


def anexar_nomes_ibge(df: pd.DataFrame) -> pd.DataFrame:
    """Completa coluna municipio a partir do código IBGE (malha IBGE não traz NM_MUN)."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return df if df is not None else pd.DataFrame()
    nomes = fetch_municipios_ibge()
    if nomes.empty:
        return df
    out = df.copy()
    out["cod_ibge"] = _cod7(out["cod_ibge"])
    nomes = nomes.copy()
    nomes["cod_ibge"] = _cod7(nomes["cod_ibge"])
    if "municipio" in out.columns:
        out = out.drop(columns=["municipio"])
    return out.merge(nomes[["cod_ibge", "municipio"]], on="cod_ibge", how="left")


def catalogo_municipios_mt() -> pd.DataFrame:
    """Catálogo MT com nome IBGE utilizável para cruzar SISREG/resumo."""
    df = load_or_refresh_municipios(force=False)
    if not _has_nomes_municipais(df):
        df = anexar_nomes_ibge(df if df is not None else pd.DataFrame())
    if not _has_nomes_municipais(df):
        df = fetch_municipios_ibge()
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["cod_ibge"] = _cod7(out["cod_ibge"])
    out = out.dropna(subset=["cod_ibge", "municipio"]).drop_duplicates("cod_ibge")
    return completar_recorte_ibge(out)


def aplicar_nomes_ibge(df: pd.DataFrame) -> pd.DataFrame:
    """Substitui municipio pelo nome oficial IBGE (evita 'nan' após merges Open-Meteo)."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return df if df is not None else pd.DataFrame()
    cat = catalogo_municipios_mt()
    if cat is None or cat.empty:
        return df
    out = df.copy()
    out["cod_ibge"] = _cod7(out["cod_ibge"])
    inj = cat[["cod_ibge", "municipio"]].drop_duplicates("cod_ibge").rename(columns={"municipio": "municipio_ibge"})
    if "municipio" in out.columns:
        out = out.drop(columns=["municipio"])
    out = out.merge(inj, on="cod_ibge", how="left")
    return out.rename(columns={"municipio_ibge": "municipio"})


def relabel_resumo_municipios() -> dict:
    """Corrige municipio no resumo quando veio vazio ou tudo Cuiabá."""
    from sisclima.core.db import read_table, write_df

    resumo = read_table("resumo_municipal_atual")
    out = aplicar_nomes_ibge(resumo)
    if out is None or out.empty:
        return {"ok": False, "n": 0, "motivo": "resumo ou catálogo vazio"}
    from sisclima.ingestion.regionais_ses import aplicar_regionais_ses

    out = aplicar_regionais_ses(out)
    n = int(out["municipio"].nunique(dropna=True)) if "municipio" in out.columns else 0
    write_df(out, "resumo_municipal_atual", if_exists="replace")
    nreg = int(out["regional_saude"].nunique(dropna=True)) if "regional_saude" in out.columns else 0
    return {"ok": n >= 50, "n": n, "regionais": nreg}


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
                        "regional_saude": props.get("regional_saude"),
                    }
                )
            df = pd.DataFrame(rows).dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")
            df = normalize_cols(df)
            if not _has_nomes_municipais(df):
                df = anexar_nomes_ibge(df)
            if len(df) >= 50 and _has_nomes_municipais(df):
                log.info("Municípios carregados de %s (%s)", gj_path.name, len(df))
                return df
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
    return completar_recorte_ibge(df)


def completar_recorte_ibge(df: pd.DataFrame) -> pd.DataFrame:
    """Garante o universo IBGE de 142 municípios (left-join; não descarta quem já existe)."""
    esperado = MT_MUNICIPIOS_OFICIAIS
    if df is not None and not df.empty:
        nuniq = int(pd.Series(_cod7(df["cod_ibge"])).nunique()) if "cod_ibge" in df.columns else len(df)
        if nuniq >= esperado:
            return df
    oficial = fetch_municipios_ibge()
    if oficial is None or oficial.empty:
        log.warning("Lista IBGE indisponível; recorte permanece com %s município(s).", 0 if df is None else len(df))
        return df if df is not None else pd.DataFrame()
    left = oficial.copy()
    left["cod_ibge"] = _cod7(left["cod_ibge"])
    right = (df if df is not None else pd.DataFrame()).copy()
    if not right.empty and "cod_ibge" in right.columns:
        right["cod_ibge"] = _cod7(right["cod_ibge"])
        extra = [c for c in right.columns if c not in left.columns or c == "cod_ibge"]
        extra = [c for c in extra if c in right.columns]
        merged = left.merge(right[extra].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        if "municipio" in right.columns and "municipio" in merged.columns:
            merged["municipio"] = merged["municipio"].fillna(
                merged["cod_ibge"].map(right.drop_duplicates("cod_ibge").set_index("cod_ibge")["municipio"])
            )
    else:
        merged = left
    if "lat" not in merged.columns:
        merged["lat"] = pd.NA
    if "lon" not in merged.columns:
        merged["lon"] = pd.NA
    miss = merged["lat"].isna() | (pd.to_numeric(merged["lat"], errors="coerce").isna())
    if bool(miss.any()):
        geo, _geojson = fetch_malha_municipal_ibge()
        if geo is not None and not geo.empty and "cod_ibge" in geo.columns:
            geo = geo.copy()
            geo["cod_ibge"] = _cod7(geo["cod_ibge"])
            geo = geo.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge")
            inj = geo[[c for c in ["cod_ibge", "lat", "lon"] if c in geo.columns]]
            inj = inj.rename(columns={"lat": "_lat_malha", "lon": "_lon_malha"})
            merged = merged.merge(inj, on="cod_ibge", how="left")
            if "_lat_malha" in merged.columns:
                merged["lat"] = merged["lat"].fillna(merged["_lat_malha"])
                merged["lon"] = merged["lon"].fillna(merged["_lon_malha"])
                merged = merged.drop(columns=["_lat_malha", "_lon_malha"], errors="ignore")
    # Fallback de coordenadas do município-pai (emancipações recentes).
    by_cod = merged.drop_duplicates("cod_ibge").set_index("cod_ibge") if "cod_ibge" in merged.columns else None
    for child, parent in _PARENT_COORDS.items():
        mask = merged["cod_ibge"].astype(str) == str(child)
        if not bool(mask.any()) or by_cod is None or str(parent) not in set(by_cod.index.astype(str)):
            continue
        prow = by_cod.loc[parent] if parent in by_cod.index else by_cod.loc[str(parent)]
        if isinstance(prow, pd.DataFrame):
            prow = prow.iloc[0]
        if merged.loc[mask, "lat"].isna().all():
            merged.loc[mask, "lat"] = prow.get("lat") if hasattr(prow, "get") else prow["lat"]
            merged.loc[mask, "lon"] = prow.get("lon") if hasattr(prow, "get") else prow["lon"]
    log.info("Recorte IBGE oficial: %s municípios (base local tinha %s).", len(merged), 0 if df is None else len(df))
    return merged


def alinha_recorte_oficial(resumo: pd.DataFrame) -> pd.DataFrame:
    """Painel e pipeline passam a ter 142 linhas: indicadores left-join; ausência = cobertura incompleta."""
    cat = catalogo_municipios_mt()
    if cat is None or cat.empty or resumo is None or resumo.empty or "cod_ibge" not in getattr(resumo, "columns", []):
        return resumo if resumo is not None else pd.DataFrame()
    out = resumo.copy()
    out["cod_ibge"] = _cod7(out["cod_ibge"])
    cat = cat.copy()
    cat["cod_ibge"] = _cod7(cat["cod_ibge"])
    keep_cat = [c for c in ["cod_ibge", "municipio", "lat", "lon", "regional_saude", "populacao"] if c in cat.columns]
    base = cat[keep_cat].drop_duplicates("cod_ibge")
    extra = [c for c in out.columns if c not in base.columns or c == "cod_ibge"]
    merged = base.merge(out[extra].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
    no_clima = pd.Series(True, index=merged.index)
    tem_clima = False
    for col in ("tmax", "utci_proxy", "pm25_ugm3"):
        if col in merged.columns:
            tem_clima = True
            no_clima = no_clima & pd.to_numeric(merged[col], errors="coerce").isna()
    if tem_clima:
        if "nivel" not in merged.columns:
            merged["nivel"] = "verde"
        if bool(no_clima.any()):
            merged.loc[no_clima, "nivel"] = "cinza"
            if "motivo" not in merged.columns:
                merged["motivo"] = pd.NA
            merged.loc[no_clima & merged["motivo"].isna(), "motivo"] = (
                "Município do recorte IBGE 142 ainda sem série nesta rodada — manter no mapa e completar no ciclo climático."
            )
        stale = (~no_clima) & merged["nivel"].astype(str).str.lower().eq("cinza")
        if bool(stale.any()):
            if "qualidade_ar_nivel" in merged.columns:
                merged.loc[stale, "nivel"] = (
                    merged.loc[stale, "qualidade_ar_nivel"].astype(str).str.lower().replace({"nan": "verde", "": "verde"})
                )
            else:
                merged.loc[stale, "nivel"] = "verde"
    return merged
