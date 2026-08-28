# -*- coding: utf-8 -*-
"""Georreferenciamento de unidades de saúde (CNES) em Mato Grosso.

Cascata: tabela operacional → DW SES → API Dados Abertos CNES → CSV local
→ centroide municipal (marcado).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT, env
from sisclima.core.db import read_table, table_exists, write_df
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.dw_sources import load_dw_cnes_estabelecimentos

log = get_logger(__name__)

TABLE = "cnes_unidades_geo"
UF_IBGE = "51"
CACHE_CSV = ROOT / "data" / "input" / "cnes_estabelecimentos_mt.csv"
OPEN_API = env("CNES_GEO_API_URL", "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos") or (
    "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
)

_LAT_MIN, _LAT_MAX = -18.2, -7.2
_LON_MIN, _LON_MAX = -61.8, -50.0

_TIPO_GRUPOS = (
    ("hospital", r"hospital|maternidade|pronto.?socorro hospitalar"),
    ("urgencia", r"upa|pronto.?atendimento|pronto.?socorro|samu|urg[eê]ncia"),
    ("aps", r"ubs|posto de sa[uú]de|centro de sa[uú]de|estrat[eé]gia sa[uú]de|sa[uú]de da fam[ií]lia|aps"),
    ("laboratorio", r"laborat[oó]rio|hemocentro|vigil[aâ]ncia"),
    ("ambulatorio", r"cl[ií]nica|ambulat[oó]rio|especializad"),
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ibge7(s: pd.Series) -> pd.Series:
    raw = s.astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{6,7})", expand=False)
    # Códigos municipais do CNES vêm com 6 dígitos; não prefixar zero (51xxxx ≠ 051xxxx).
    return raw


def grupo_tipo(texto: str) -> str:
    t = str(texto or "").casefold()
    for nome, pat in _TIPO_GRUPOS:
        if pd.Series([t]).str.contains(pat, regex=True, na=False).iloc[0]:
            return nome
    return "outros"


def coords_validas_mt(lat: pd.Series, lon: pd.Series) -> pd.Series:
    la = pd.to_numeric(lat, errors="coerce")
    lo = pd.to_numeric(lon, errors="coerce")
    swapped = la.between(_LON_MIN, _LON_MAX) & lo.between(_LAT_MIN, _LAT_MAX)
    ok = la.between(_LAT_MIN, _LAT_MAX) & lo.between(_LON_MIN, _LON_MAX)
    return ok | swapped


def _corrige_lat_lon(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "lat" not in out.columns:
        out["lat"] = pd.NA
    if "lon" not in out.columns:
        out["lon"] = pd.NA
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    swapped = out["lat"].between(_LON_MIN, _LON_MAX) & out["lon"].between(_LAT_MIN, _LAT_MAX)
    if swapped.any():
        out.loc[swapped, ["lat", "lon"]] = out.loc[swapped, ["lon", "lat"]].to_numpy()
    ok = coords_validas_mt(out["lat"], out["lon"])
    out.loc[~ok, ["lat", "lon"]] = pd.NA
    return out


def _records_from_payload(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("estabelecimentos", "data", "items", "content", "registros"):
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    return []


def normalize_opendata_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    raw = pd.DataFrame(rows)
    rename = {
        "codigo_cnes": "cnes",
        "cnes": "cnes",
        "nome_fantasia": "nome_unidade",
        "nome_razao_social": "razao_social",
        "descricao_tipo_unidade": "tipo_unidade",
        "tipo_unidade": "tipo_unidade",
        "codigo_tipo_unidade": "codigo_tipo_unidade",
        "codigo_municipio": "cod_ibge",
        "codigo_municipio_ibge": "cod_ibge",
        "nome_municipio": "municipio",
        "latitude": "lat",
        "longitude": "lon",
        "latitude_estabelecimento_decimo_grau": "lat",
        "longitude_estabelecimento_decimo_grau": "lon",
        "estabelecimento_faz_atendimento_ambulatorial_sus": "vinculo_sus",
        "vinculo_sus": "vinculo_sus",
    }
    out = raw.rename(columns={k: v for k, v in rename.items() if k in raw.columns})
    if "cnes" not in out.columns:
        return pd.DataFrame()
    out["cnes"] = out["cnes"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = _ibge7(out["cod_ibge"])
        keep = out["cod_ibge"].isna() | out["cod_ibge"].astype(str).str.startswith(UF_IBGE)
        out = out[keep]
    out = _corrige_lat_lon(out)
    if "tipo_unidade" not in out.columns or out["tipo_unidade"].astype(str).str.strip().eq("").all():
        mapa_tipo = {
            "1": "Posto de Saúde",
            "2": "Centro de Saúde / Unidade Básica",
            "4": "Policlínica",
            "5": "Hospital Geral",
            "7": "Pronto Socorro Geral",
            "15": "Unidade Mista",
            "21": "Pronto Socorro Especializado",
            "62": "Hospital Geral",
            "67": "Laboratório de Saúde Pública",
            "68": "UPA",
            "73": "Pronto Atendimento",
        }
        if "codigo_tipo_unidade" in out.columns:
            out["tipo_unidade"] = (
                out["codigo_tipo_unidade"].astype(str).str.replace(r"\.0$", "", regex=True).map(mapa_tipo).fillna("Outros")
            )
        else:
            out["tipo_unidade"] = ""
    out["grupo_tipo"] = out["tipo_unidade"].map(grupo_tipo)
    out["fonte_coord"] = "opendata_cnes"
    out.loc[out["lat"].isna() | out["lon"].isna(), "fonte_coord"] = ""
    return out


def fetch_opendata_cnes_mt(*, limit: int = 20, max_rows: int = 8000) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    offset = 0
    # A API pública do MS pagina no máximo 20 registros por offset.
    page_size = max(1, min(int(limit), 20))
    while offset < max_rows:
        try:
            resp = http_get(
                OPEN_API,
                params={"codigo_uf": UF_IBGE, "limit": page_size, "offset": offset},
                timeout=45,
            )
            if resp.status_code >= 400:
                log.warning("API CNES HTTP %s em offset=%s", resp.status_code, offset)
                break
            payload = resp.json()
        except Exception as exc:
            log.warning("API CNES indisponível: %s", exc)
            break
        rows = _records_from_payload(payload)
        if not rows:
            break
        part = normalize_opendata_rows(rows)
        if not part.empty:
            chunks.append(part)
        if len(rows) < page_size:
            break
        offset += page_size
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True).drop_duplicates("cnes", keep="first")


def _from_dw() -> pd.DataFrame:
    try:
        dw = load_dw_cnes_estabelecimentos()
    except Exception as exc:
        log.warning("DW CNES estabelecimentos falhou: %s", exc)
        return pd.DataFrame()
    if dw is None or dw.empty:
        return pd.DataFrame()
    out = dw.copy()
    rename = {
        "nome_estabelecimento": "nome_unidade",
        "latitude": "lat",
        "longitude": "lon",
        "lat_estabelecimento": "lat",
        "lon_estabelecimento": "lon",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    if "cnes" in out.columns:
        out["cnes"] = out["cnes"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = _ibge7(out["cod_ibge"])
    out = _corrige_lat_lon(out)
    out["fonte_coord"] = "dw_cnes"
    out.loc[out["lat"].isna() | out["lon"].isna(), "fonte_coord"] = ""
    if "tipo_unidade" not in out.columns:
        out["tipo_unidade"] = ""
    out["grupo_tipo"] = out["tipo_unidade"].map(grupo_tipo)
    return out


def _from_csv() -> pd.DataFrame:
    if not CACHE_CSV.exists():
        return pd.DataFrame()
    try:
        raw = pd.read_csv(CACHE_CSV, dtype=str)
    except Exception as exc:
        log.warning("CSV CNES local ilegível: %s", exc)
        return pd.DataFrame()
    return normalize_opendata_rows(raw.to_dict("records"))


def _prefer_nonempty(base: pd.Series, other: pd.Series) -> pd.Series:
    a = base
    b = other
    empty = a.isna() | (a.astype(str).str.strip() == "") | (a.astype(str) == "nan")
    return a.where(~empty, b)


def _merge_sources(*parts: pd.DataFrame) -> pd.DataFrame:
    alive = [p for p in parts if p is not None and not p.empty and "cnes" in p.columns]
    if not alive:
        return pd.DataFrame()
    out = alive[0].copy()
    out["cnes"] = out["cnes"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
    for extra in alive[1:]:
        add = extra.copy()
        add["cnes"] = add["cnes"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
        out = out.merge(add, on="cnes", how="outer", suffixes=("", "_x"))
        for col in ("lat", "lon", "nome_unidade", "tipo_unidade", "municipio", "cod_ibge", "fonte_coord", "vinculo_sus"):
            alt = f"{col}_x"
            if col in out.columns and alt in out.columns:
                out[col] = _prefer_nonempty(out[col], out[alt])
        drop = [c for c in out.columns if c.endswith("_x")]
        out = out.drop(columns=drop, errors="ignore")
    return out.drop_duplicates("cnes", keep="first")


def _centroid_fill(df: pd.DataFrame, resumo: pd.DataFrame | None) -> pd.DataFrame:
    if resumo is None or resumo.empty or not {"cod_ibge", "lat", "lon"}.issubset(resumo.columns):
        return df
    geo = resumo[["cod_ibge", "lat", "lon"]].drop_duplicates("cod_ibge").copy()
    geo["cod_ibge"] = _ibge7(geo["cod_ibge"])
    geo["lat"] = pd.to_numeric(geo["lat"], errors="coerce")
    geo["lon"] = pd.to_numeric(geo["lon"], errors="coerce")
    geo = geo.dropna(subset=["lat", "lon"])
    if geo.empty or "cod_ibge" not in df.columns:
        return df
    out = df.copy()
    out["cod_ibge"] = _ibge7(out["cod_ibge"])
    miss = out["lat"].isna() | out["lon"].isna()
    if not miss.any():
        return out
    merged = out.loc[miss, ["cod_ibge"]].merge(geo, on="cod_ibge", how="left")
    out.loc[miss, "lat"] = pd.to_numeric(merged["lat"], errors="coerce").to_numpy()
    out.loc[miss, "lon"] = pd.to_numeric(merged["lon"], errors="coerce").to_numpy()
    filled = miss & out["lat"].notna() & out["lon"].notna()
    out.loc[filled, "fonte_coord"] = "centroid_municipio"
    return out


def load_cnes_unidades_geo(
    resumo: pd.DataFrame | None = None,
    *,
    fetch: bool = False,
    persist: bool = True,
) -> pd.DataFrame:
    if not fetch and table_exists(TABLE):
        cached = read_table(TABLE)
        if cached is not None and not cached.empty:
            return _corrige_lat_lon(cached)

    dw = _from_dw()
    api = fetch_opendata_cnes_mt() if fetch else pd.DataFrame()
    local = _from_csv()
    base = _merge_sources(api, local, dw)
    if base.empty:
        log.warning("CNES geo: nenhuma fonte de estabelecimentos disponível.")
        return pd.DataFrame()

    if "tipo_unidade" not in base.columns:
        base["tipo_unidade"] = ""
    if "grupo_tipo" not in base.columns:
        base["grupo_tipo"] = base["tipo_unidade"].map(grupo_tipo)
    if "fonte_coord" not in base.columns:
        base["fonte_coord"] = ""
    base = _corrige_lat_lon(base)
    base = _centroid_fill(base, resumo)
    if resumo is not None and not resumo.empty and "cod_ibge" in base.columns and "cod_ibge" in resumo.columns:
        r = resumo[["cod_ibge"]].dropna().copy()
        r["k"] = _ibge7(r["cod_ibge"]).str[:6]
        lookup = r.drop_duplicates("k").set_index("k")["cod_ibge"].astype(str)
        k = _ibge7(base["cod_ibge"]).str[:6]
        mapped = k.map(lookup)
        base["cod_ibge"] = mapped.where(mapped.notna(), base["cod_ibge"])
    base["atualizado_em"] = _now()
    keep = [
        c
        for c in [
            "cnes",
            "nome_unidade",
            "razao_social",
            "tipo_unidade",
            "grupo_tipo",
            "municipio",
            "cod_ibge",
            "regional_saude",
            "lat",
            "lon",
            "vinculo_sus",
            "fonte_coord",
            "atualizado_em",
        ]
        if c in base.columns
    ]
    out = base[keep].copy()
    if persist and not out.empty:
        write_df(out, TABLE)
    return out
