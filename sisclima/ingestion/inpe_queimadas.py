# -*- coding: utf-8 -*-
"""Focos de queimadas INPE (BDQueimadas) — CSV diário aberto.

Fonte: https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil/
Agrega focos por município (IBGE) para MT em janelas 24h / 7d.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from io import StringIO

import pandas as pd

from sisclima.core.config import as_bool, env
from sisclima.core.http_client import http_get
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DEFAULT_BASE = (
    "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/diario/Brasil"
)


def _estado_mt_mask(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip().str.upper()
    # Evita capturar "MATO GROSSO DO SUL"
    return s.eq("MATO GROSSO") | s.eq("MT")


def _fetch_daily_csv(day: date, base_url: str) -> pd.DataFrame:
    url = f"{base_url.rstrip('/')}/focos_diario_br_{day.strftime('%Y%m%d')}.csv"
    try:
        r = http_get(url, timeout=60, ssl_env_key="INPE_QUEIMADAS_SSL_VERIFY")
        if r.status_code == 404:
            return pd.DataFrame()
        r.raise_for_status()
        text = r.content.decode("utf-8", errors="replace")
        try:
            df = pd.read_csv(StringIO(text))
        except Exception:
            df = pd.read_csv(StringIO(r.content.decode("latin-1", errors="replace")))
        if df.empty:
            return df
        df["_data_arquivo"] = day.isoformat()
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("INPE queimadas %s falhou: %s", day.isoformat(), exc)
        return pd.DataFrame()


def fetch_focos_brutos(days: int = 7) -> pd.DataFrame:
    """Baixa CSVs diários dos últimos `days` e filtra Mato Grosso."""
    if not as_bool(env("USE_INPE_QUEIMADAS", "true"), True):
        return pd.DataFrame()
    base = env("INPE_QUEIMADAS_BASE_URL", DEFAULT_BASE) or DEFAULT_BASE
    days = max(1, int(days or 7))
    frames: list[pd.DataFrame] = []
    today = date.today()
    for i in range(days + 1):  # +1: arquivo do dia às vezes atrasa
        day = today - timedelta(days=i)
        part = _fetch_daily_csv(day, base)
        if part.empty:
            continue
        if "estado" in part.columns:
            part = part.loc[_estado_mt_mask(part["estado"])].copy()
        elif "estado_id" in part.columns:
            part = part.loc[pd.to_numeric(part["estado_id"], errors="coerce") == 51].copy()
        if not part.empty:
            frames.append(part)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # Dedup por id de foco quando existir
    if "id" in out.columns:
        out = out.drop_duplicates(subset=["id"], keep="last")
    return out


def aggregate_focos_municipais(focos: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    """Agrega focos por município IBGE (24h e janela de N dias)."""
    if focos is None or focos.empty:
        return pd.DataFrame()

    df = focos.copy()
    if "municipio_id" not in df.columns and "cod_ibge" not in df.columns:
        return pd.DataFrame()

    df["cod_ibge"] = (
        df["municipio_id"] if "municipio_id" in df.columns else df["cod_ibge"]
    ).astype(str).str.extract(r"(\d{7})", expand=False)
    df = df.dropna(subset=["cod_ibge"])

    if "data_hora_gmt" in df.columns:
        df["data_foco"] = pd.to_datetime(df["data_hora_gmt"], errors="coerce")
    elif "_data_arquivo" in df.columns:
        df["data_foco"] = pd.to_datetime(df["_data_arquivo"], errors="coerce")
    else:
        df["data_foco"] = pd.NaT

    ref = pd.Timestamp(datetime.now().date())
    cut_24h = ref - pd.Timedelta(days=1)
    cut_7d = ref - pd.Timedelta(days=max(1, int(window_days)))

    in_24h = df["data_foco"].isna() | (df["data_foco"] >= cut_24h)
    in_7d = df["data_foco"].isna() | (df["data_foco"] >= cut_7d)

    base = df[["cod_ibge"]].drop_duplicates("cod_ibge")
    if "municipio" in df.columns:
        nomes = df.groupby("cod_ibge", as_index=False)["municipio"].first()
        base = base.merge(nomes, on="cod_ibge", how="left")
    else:
        base["municipio"] = None

    c24 = (
        df.loc[in_24h]
        .groupby("cod_ibge", as_index=False)
        .size()
        .rename(columns={"size": "focos_queimadas_24h"})
    )
    c7 = (
        df.loc[in_7d]
        .groupby("cod_ibge", as_index=False)
        .size()
        .rename(columns={"size": "focos_queimadas_7d"})
    )
    snap = base.merge(c24, on="cod_ibge", how="left").merge(c7, on="cod_ibge", how="left")
    snap["focos_queimadas_24h"] = pd.to_numeric(snap["focos_queimadas_24h"], errors="coerce").fillna(0).astype(int)
    snap["focos_queimadas_7d"] = pd.to_numeric(snap["focos_queimadas_7d"], errors="coerce").fillna(0).astype(int)

    df7 = df.loc[in_7d].copy()
    if not df7.empty:
        df7["_frp"] = pd.to_numeric(df7["frp"], errors="coerce") if "frp" in df7.columns else float("nan")
        df7["_rf"] = pd.to_numeric(df7["risco_fogo"], errors="coerce") if "risco_fogo" in df7.columns else float("nan")
        df7["_ds"] = (
            pd.to_numeric(df7["numero_dias_sem_chuva"], errors="coerce")
            if "numero_dias_sem_chuva" in df7.columns
            else float("nan")
        )
        frp7 = df7.groupby("cod_ibge", as_index=False).agg(
            frp_queimadas_7d=("_frp", "sum"),
            frp_queimadas_max=("_frp", "max"),
            risco_fogo_medio=("_rf", "mean"),
            dias_sem_chuva_max=("_ds", "max"),
        )
        snap = snap.merge(frp7, on="cod_ibge", how="left")
    else:
        snap["frp_queimadas_7d"] = 0.0
        snap["frp_queimadas_max"] = 0.0
        snap["risco_fogo_medio"] = float("nan")
        snap["dias_sem_chuva_max"] = float("nan")

    # Semáforo operacional de focos (independente de PM2,5)
    n7 = pd.to_numeric(snap["focos_queimadas_7d"], errors="coerce").fillna(0)
    snap["nivel_queimadas"] = "verde"
    snap.loc[n7 >= 5, "nivel_queimadas"] = "amarela"
    snap.loc[n7 >= 20, "nivel_queimadas"] = "laranja"
    snap.loc[n7 >= 50, "nivel_queimadas"] = "vermelha"
    snap.loc[n7 >= 120, "nivel_queimadas"] = "roxa"

    snap["fonte"] = "INPE_BDQueimadas_csv_diario"
    snap["data_referencia"] = ref.date().isoformat()
    snap["data_processamento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snap["uf"] = "MT"
    return snap


def load_queimadas_municipais(days: int | None = None) -> pd.DataFrame:
    """API de alto nível: brutos → agregado municipal."""
    if days is None:
        try:
            days = int(env("INPE_QUEIMADAS_DAYS", "7") or 7)
        except Exception:
            days = 7
    brutos = fetch_focos_brutos(days=days)
    if brutos.empty:
        return pd.DataFrame()
    return aggregate_focos_municipais(brutos, window_days=days)
