# -*- coding: utf-8 -*-
"""Indicadores WASH municipais (IBGE Censo 2022) para MT.

Fontes públicas (sem VPN SES / SNIS interativo):
- Agregado 6803: ligação à rede geral de água
- Agregado 6804: água canalizada no domicílio
- Agregado 6805: tipo de esgotamento sanitário

Produz cobertura/déficit domiciliar para o risco AdaptaSUS `wash`.
SAN (insegurança alimentar) permanece lacuna até fonte SES/SISVAN.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from sisclima.core.config import ROOT, as_bool, env
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

# 6803 — ligação à rede geral de água
AGUA_CLASS = "1821"
AGUA_TOTAL = "72129"
AGUA_REDE_PRINCIPAL = "72144"
AGUA_SEM_REDE = "72153"

# 6804 — canalização
CANAL_CLASS = "1817"
CANAL_TOTAL = "72125"
CANAL_DENTRO = "72126"
CANAL_SEM = "72128"

# 6805 — esgotamento
ESG_CLASS = "11558"
ESG_TOTAL = "46292"
ESG_REDE = "46290"  # rede geral/pluvial ou fossa ligada à rede
ESG_FOSSA_NAO_REDE = "72112"
ESG_RUDIMENTAR = "72113"
ESG_VALA = "92858"
ESG_CORPO_DAGUA = "72114"
ESG_OUTRA = "72115"
ESG_SEM_BANHEIRO = "92861"

CACHE_REL = Path("data/raw/ibge/wash_mt_censo2022.csv")
SEED_CANDIDATES = [
    ROOT / "data" / "input" / "wash_municipal_mt.csv",
    ROOT / "data" / "sample" / "wash_municipal_mt.csv",
    ROOT / CACHE_REL,
]


def _parse_series_value(raw) -> float:
    if raw is None or raw == "" or raw == "-" or raw == "...":
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
    classif_id: str,
    cat_ids: list[str],
    mun_ids: list[str],
    *,
    periodo: str = "2022",
    variavel: str = "381",
    timeout: int = 120,
) -> pd.DataFrame:
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
        for bloco in r.json():
            for resultado in bloco.get("resultados") or []:
                cat_id = None
                for c in resultado.get("classificacoes") or []:
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


def _pct(num: pd.Series, den: pd.Series) -> pd.Series:
    den_safe = den.replace(0, np.nan)
    return (num / den_safe * 100.0).round(2)


def fetch_wash_censo_mt(timeout: int = 120) -> pd.DataFrame:
    """Baixa indicadores WASH do Censo 2022 para municípios de MT."""
    mun_ids = fetch_municipio_ids()
    log.info("IBGE WASH: %s municípios MT", len(mun_ids))

    agua = _fetch_classificado(
        "6803",
        AGUA_CLASS,
        [AGUA_TOTAL, AGUA_REDE_PRINCIPAL, AGUA_SEM_REDE],
        mun_ids,
        timeout=timeout,
    )
    canal = _fetch_classificado(
        "6804",
        CANAL_CLASS,
        [CANAL_TOTAL, CANAL_DENTRO, CANAL_SEM],
        mun_ids,
        timeout=timeout,
    )
    esg = _fetch_classificado(
        "6805",
        ESG_CLASS,
        [
            ESG_TOTAL,
            ESG_REDE,
            ESG_FOSSA_NAO_REDE,
            ESG_RUDIMENTAR,
            ESG_VALA,
            ESG_CORPO_DAGUA,
            ESG_OUTRA,
            ESG_SEM_BANHEIRO,
        ],
        mun_ids,
        timeout=timeout,
    )
    if agua.empty and esg.empty:
        return pd.DataFrame()

    def _pivot(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        return df.pivot_table(index="cod_ibge", columns="categoria_id", values="valor", aggfunc="first")

    pa = _pivot(agua)
    pc = _pivot(canal)
    pe = _pivot(esg)

    codes = sorted(set(pa.index.astype(str)) | set(pc.index.astype(str)) | set(pe.index.astype(str)))
    out = pd.DataFrame({"cod_ibge": [c.zfill(7) for c in codes]})

    if not pa.empty:
        pa.index = pa.index.astype(str).str.zfill(7)
        tot = pa.reindex(out["cod_ibge"])[AGUA_TOTAL] if AGUA_TOTAL in pa.columns else pd.Series(np.nan, index=out.index)
        rede = pa.reindex(out["cod_ibge"])[AGUA_REDE_PRINCIPAL] if AGUA_REDE_PRINCIPAL in pa.columns else pd.Series(np.nan, index=out.index)
        sem = pa.reindex(out["cod_ibge"])[AGUA_SEM_REDE] if AGUA_SEM_REDE in pa.columns else pd.Series(np.nan, index=out.index)
        out["domicilios_total_agua"] = tot.to_numpy()
        out["domicilios_rede_agua"] = rede.to_numpy()
        out["domicilios_sem_rede_agua"] = sem.to_numpy()
        out["cobertura_rede_agua_pct"] = _pct(rede, tot).to_numpy()
        out["deficit_rede_agua_pct"] = _pct(sem, tot).to_numpy()

    if not pc.empty:
        pc.index = pc.index.astype(str).str.zfill(7)
        tot = pc.reindex(out["cod_ibge"])[CANAL_TOTAL] if CANAL_TOTAL in pc.columns else pd.Series(np.nan, index=out.index)
        dentro = pc.reindex(out["cod_ibge"])[CANAL_DENTRO] if CANAL_DENTRO in pc.columns else pd.Series(np.nan, index=out.index)
        sem = pc.reindex(out["cod_ibge"])[CANAL_SEM] if CANAL_SEM in pc.columns else pd.Series(np.nan, index=out.index)
        out["cobertura_agua_canalizada_pct"] = _pct(dentro, tot).to_numpy()
        out["deficit_agua_canalizada_pct"] = _pct(sem, tot).to_numpy()

    if not pe.empty:
        pe.index = pe.index.astype(str).str.zfill(7)
        tot = pe.reindex(out["cod_ibge"])[ESG_TOTAL] if ESG_TOTAL in pe.columns else pd.Series(np.nan, index=out.index)
        rede = pe.reindex(out["cod_ibge"])[ESG_REDE] if ESG_REDE in pe.columns else pd.Series(np.nan, index=out.index)
        inadequado_cols = [c for c in [ESG_RUDIMENTAR, ESG_VALA, ESG_CORPO_DAGUA, ESG_SEM_BANHEIRO] if c in pe.columns]
        inadequado = pe.reindex(out["cod_ibge"])[inadequado_cols].sum(axis=1, min_count=1) if inadequado_cols else pd.Series(np.nan, index=out.index)
        out["domicilios_total_esgoto"] = tot.to_numpy()
        out["domicilios_esgoto_rede"] = rede.to_numpy()
        out["cobertura_esgoto_rede_pct"] = _pct(rede, tot).to_numpy()
        out["deficit_esgoto_inadequado_pct"] = _pct(inadequado, tot).to_numpy()

    # Score sintético de déficit WASH 0–100 (maior = pior acesso)
    d_agua = pd.to_numeric(out.get("deficit_rede_agua_pct"), errors="coerce")
    d_canal = pd.to_numeric(out.get("deficit_agua_canalizada_pct"), errors="coerce")
    d_esg = pd.to_numeric(out.get("deficit_esgoto_inadequado_pct"), errors="coerce")
    # Preferir déficit de rede; canalização reforça; esgoto tem peso alto em eventos de chuva/estiagem
    parts = []
    w = []
    if d_agua.notna().any():
        parts.append(d_agua.fillna(d_agua.median()))
        w.append(0.35)
    if d_canal.notna().any():
        parts.append(d_canal.fillna(d_canal.median()))
        w.append(0.20)
    if d_esg.notna().any():
        parts.append(d_esg.fillna(d_esg.median()))
        w.append(0.45)
    if parts:
        w = np.array(w, dtype=float)
        w = w / w.sum()
        mat = np.column_stack([p.to_numpy(dtype=float) for p in parts])
        out["indice_deficit_wash"] = (mat * w).sum(axis=1).clip(0, 100).round(1)
    else:
        out["indice_deficit_wash"] = np.nan

    out["fonte_wash"] = "IBGE_Censo_2022"
    out["atualizado_em"] = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    # Remove linhas totalmente vazias (município novo sem Censo)
    metric_cols = [c for c in out.columns if c.endswith("_pct") or c == "indice_deficit_wash"]
    if metric_cols:
        out = out.dropna(subset=metric_cols, how="all").reset_index(drop=True)
    return normalize_cols(out)


def _cache_path() -> Path:
    path = ROOT / CACHE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_wash_municipal(force_refresh: bool | None = None) -> pd.DataFrame:
    """Carrega WASH municipal (CSV seed/cache → API IBGE)."""
    if force_refresh is None:
        force_refresh = as_bool(env("REFRESH_IBGE_WASH", "false"), False)

    if not force_refresh:
        for path in SEED_CANDIDATES:
            if path.exists():
                try:
                    df = normalize_cols(pd.read_csv(path, sep=None, engine="python"))
                    if "cod_ibge" in df.columns and len(df) >= 50:
                        df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
                        log.info("WASH carregado de %s (%s munis)", path, len(df))
                        return df
                except Exception as exc:
                    log.warning("Falha lendo %s: %s", path, exc)

    try:
        df = fetch_wash_censo_mt()
        if not df.empty:
            cache = _cache_path()
            df.to_csv(cache, index=False, encoding="utf-8-sig")
            seed = ROOT / "data" / "sample" / "wash_municipal_mt.csv"
            seed.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(seed, index=False, encoding="utf-8-sig")
            input_seed = ROOT / "data" / "input" / "wash_municipal_mt.csv"
            input_seed.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(input_seed, index=False, encoding="utf-8-sig")
            return df
    except Exception as exc:
        log.warning("Falha ao baixar WASH IBGE: %s", exc)
    return pd.DataFrame()
