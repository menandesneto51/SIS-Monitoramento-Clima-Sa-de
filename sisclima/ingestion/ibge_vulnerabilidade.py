# -*- coding: utf-8 -*-
"""Vulnerabilidade demográfica municipal (IBGE Censo 2022) para MT.

Fontes públicas (sem VPN SES):
- Agregado 9514: população por idade → idosos ≥60 e crianças 0–4 / 0–9
- Agregado 9923: situação do domicílio → % rural
- Agregado 1301: área e densidade demográfica

Gera proxy operacional para `indice_vulnerabilidade_calor` e KPIs de
população vulnerável exposta. Não substitui cadastro de vulneráveis da APS.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from sisclima.core.config import APP_CONFIG, ROOT, as_bool, env
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols

log = get_logger(__name__)

IBGE_UF_MT = "51"
IBGE_LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
IBGE_AGREGADO = (
    "https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/periodos/{periodo}"
    "/variaveis/{variavel}?localidades=N6[{ids}]&classificacao={classif}"
)

# Idade (classificação 287) — faixas nível 1 usadas no composto
AGE_TOTAL = "100362"
AGE_0_4 = "93070"
AGE_5_9 = "93084"
AGE_60_PLUS = [
    "93095",  # 60-64
    "93096",  # 65-69
    "93097",  # 70-74
    "93098",  # 75-79
    "49108",  # 80-84
    "49109",  # 85-89
    "60040",  # 90-94
    "60041",  # 95-99
    "6653",   # 100+
]

# Situação do domicílio (classificação 1)
DOM_TOTAL = "6795"
DOM_URBANA = "1"
DOM_RURAL = "2"

CACHE_REL = Path("data/raw/ibge/vulnerabilidade_mt_censo2022.csv")
SEED_CANDIDATES = [
    ROOT / "data" / "input" / "vulnerabilidade_municipal_mt.csv",
    ROOT / "data" / "sample" / "vulnerabilidade_municipal_mt.csv",
    ROOT / CACHE_REL,
]


def _parse_series_value(raw) -> float:
    if raw is None or raw == "" or raw == "-":
        return np.nan
    try:
        return float(str(raw).replace(",", "."))
    except Exception:
        return np.nan


def _chunked(items: list[str], size: int = 40):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def fetch_municipio_ids(uf: str = IBGE_UF_MT, timeout: int = 60) -> list[str]:
    r = http_get(IBGE_LOCALIDADES.format(uf=uf), timeout=timeout, ssl_env_key="IBGE_SSL_VERIFY")
    r.raise_for_status()
    return [str(m["id"]) for m in r.json()]


def _fetch_classificado(
    tabela: str,
    periodo: str,
    variavel: str,
    classif_id: str,
    cat_ids: list[str],
    mun_ids: list[str],
    timeout: int = 120,
) -> pd.DataFrame:
    """Retorna long-form: cod_ibge, categoria_id, valor."""
    rows = []
    classif = f"{classif_id}[{','.join(cat_ids)}]"
    for batch in _chunked(mun_ids, 40):
        url = IBGE_AGREGADO.format(
            tabela=tabela,
            periodo=periodo,
            variavel=variavel,
            ids=",".join(batch),
            classif=classif,
        )
        r = http_get(url, timeout=timeout, ssl_env_key="IBGE_SSL_VERIFY")
        r.raise_for_status()
        payload = r.json()
        for bloco in payload:
            for resultado in bloco.get("resultados") or []:
                cats = resultado.get("classificacoes") or []
                cat_id = None
                for c in cats:
                    if str(c.get("id")) == str(classif_id):
                        cat_map = c.get("categoria") or {}
                        if cat_map:
                            cat_id = str(next(iter(cat_map.keys())))
                        break
                for serie in resultado.get("series") or []:
                    loc = (serie.get("localidade") or {}).get("id")
                    vals = serie.get("serie") or {}
                    val = _parse_series_value(vals.get(periodo) or next(iter(vals.values()), None))
                    rows.append({"cod_ibge": str(loc).zfill(7), "categoria_id": cat_id, "valor": val})
    return pd.DataFrame(rows)


def fetch_vulnerabilidade_censo_mt(timeout: int = 120) -> pd.DataFrame:
    """Baixa indicadores demográficos do Censo 2022 para os 142 municípios de MT."""
    mun_ids = fetch_municipio_ids()
    log.info("IBGE vulnerabilidade: %s municípios MT", len(mun_ids))

    age_cats = [AGE_TOTAL, AGE_0_4, AGE_5_9] + AGE_60_PLUS
    age = _fetch_classificado("9514", "2022", "93", "287", age_cats, mun_ids, timeout=timeout)
    if age.empty:
        return pd.DataFrame()

    pivot = age.pivot_table(index="cod_ibge", columns="categoria_id", values="valor", aggfunc="first")
    total = pivot.get(AGE_TOTAL)
    if total is None:
        return pd.DataFrame()

    idosos = pivot.reindex(columns=AGE_60_PLUS).sum(axis=1, min_count=1)
    c04 = pivot.get(AGE_0_4)
    c59 = pivot.get(AGE_5_9)
    criancas_0_9 = (c04.fillna(0) + c59.fillna(0)).where(c04.notna() | c59.notna())

    out = pd.DataFrame(
        {
            "cod_ibge": pivot.index.astype(str).str.zfill(7),
            "populacao_censo_2022": total.to_numpy(),
            "idosos_60mais": idosos.to_numpy(),
            "criancas_0_4": c04.to_numpy() if c04 is not None else np.nan,
            "criancas_0_9": criancas_0_9.to_numpy(),
        }
    )
    out["idosos_pct"] = (out["idosos_60mais"] / out["populacao_censo_2022"] * 100).round(2)
    out["criancas_0_4_pct"] = (out["criancas_0_4"] / out["populacao_censo_2022"] * 100).round(2)
    out["criancas_0_9_pct"] = (out["criancas_0_9"] / out["populacao_censo_2022"] * 100).round(2)

    # Rural
    try:
        rural = _fetch_classificado(
            "9923", "2022", "93", "1", [DOM_TOTAL, DOM_URBANA, DOM_RURAL], mun_ids, timeout=timeout
        )
        rp = rural.pivot_table(index="cod_ibge", columns="categoria_id", values="valor", aggfunc="first")
        rtot = rp.get(DOM_TOTAL)
        rr = rp.get(DOM_RURAL)
        if rtot is not None and rr is not None:
            tmp = pd.DataFrame(
                {
                    "cod_ibge": rp.index.astype(str).str.zfill(7),
                    "rural_pct": (rr / rtot * 100).round(2).to_numpy(),
                }
            )
            out = out.merge(tmp, on="cod_ibge", how="left")
    except Exception as exc:
        log.warning("IBGE rural (9923) indisponível: %s", exc)

    # Área territorial (IBGE 1301 — série oficial 2010; densidade recalculada com pop 2022)
    try:
        dens_rows = []
        for batch in _chunked(mun_ids, 40):
            url = (
                "https://servicodados.ibge.gov.br/api/v3/agregados/1301/periodos/2010/"
                f"variaveis/615|616?localidades=N6[{','.join(batch)}]"
            )
            r = http_get(url, timeout=timeout, ssl_env_key="IBGE_SSL_VERIFY")
            r.raise_for_status()
            for bloco in r.json():
                var_id = str(bloco.get("id"))
                for resultado in bloco.get("resultados") or []:
                    for serie in resultado.get("series") or []:
                        loc = (serie.get("localidade") or {}).get("id")
                        vals = serie.get("serie") or {}
                        val = _parse_series_value(vals.get("2010") or next(iter(vals.values()), None))
                        dens_rows.append({"cod_ibge": str(loc).zfill(7), "variavel": var_id, "valor": val})
        dens = pd.DataFrame(dens_rows)
        if not dens.empty:
            wide = dens.pivot_table(index="cod_ibge", columns="variavel", values="valor", aggfunc="first")
            tmp = pd.DataFrame({"cod_ibge": wide.index.astype(str).str.zfill(7)})
            if "615" in wide.columns:
                tmp["area_km2"] = wide["615"].to_numpy()
            out = out.merge(tmp, on="cod_ibge", how="left")
            if "area_km2" in out.columns:
                out["densidade"] = (out["populacao_censo_2022"] / out["area_km2"]).round(2)
    except Exception as exc:
        log.warning("IBGE área/densidade (1301) indisponível: %s", exc)

    out["fonte_vulnerabilidade"] = "IBGE_Censo_2022"
    out["atualizado_em"] = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    return normalize_cols(out)


def _cache_path() -> Path:
    path = ROOT / CACHE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_vulnerabilidade_municipal(force_refresh: bool | None = None) -> pd.DataFrame:
    """Carrega vulnerabilidade municipal (cache/CSV → API IBGE)."""
    if force_refresh is None:
        force_refresh = as_bool(env("REFRESH_IBGE_VULNERABILIDADE", "false"), False)

    if not force_refresh:
        for path in SEED_CANDIDATES:
            if path.exists():
                try:
                    df = normalize_cols(pd.read_csv(path, sep=None, engine="python"))
                    if "cod_ibge" in df.columns and len(df) >= 50:
                        df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
                        log.info("Vulnerabilidade carregada de %s (%s munis)", path, len(df))
                        return df
                except Exception as exc:
                    log.warning("Falha lendo %s: %s", path, exc)

    try:
        df = fetch_vulnerabilidade_censo_mt()
        if not df.empty:
            cache = _cache_path()
            df.to_csv(cache, index=False, encoding="utf-8-sig")
            seed = ROOT / "data" / "sample" / "vulnerabilidade_municipal_mt.csv"
            seed.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(seed, index=False, encoding="utf-8-sig")
            input_seed = ROOT / "data" / "input" / "vulnerabilidade_municipal_mt.csv"
            input_seed.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(input_seed, index=False, encoding="utf-8-sig")
            return df
    except Exception as exc:
        log.warning("Falha ao baixar vulnerabilidade IBGE: %s", exc)

    # Último recurso: sample antigo (poucos municípios)
    sample = APP_CONFIG.input_dir / "municipios_metadata.csv"
    if not sample.exists():
        sample = ROOT / "data" / "sample" / "municipios_metadata.csv"
    if sample.exists():
        df = normalize_cols(pd.read_csv(sample, sep=None, engine="python"))
        if "cod_ibge" in df.columns:
            df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
            return df
    return pd.DataFrame()
