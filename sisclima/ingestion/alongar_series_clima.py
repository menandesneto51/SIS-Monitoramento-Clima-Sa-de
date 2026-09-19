# -*- coding: utf-8 -*-
"""Alongar séries climáticas para sazonalidade/lags (Open-Meteo Archive + AQ).

Preenche ``hist_clima_municipal_diario`` com umidade/chuva/T e estende
``qualidade_ar_municipal`` com PM/IQA (~92 dias via air-quality API).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.config import SETTINGS, as_bool, env
from sisclima.core.db import read_table, table_exists, write_df
from sisclima.core.logging_utils import get_logger
from sisclima.engines.air_quality import add_air_quality_indicators

log = get_logger(__name__)


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(env(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


def _municipios_geo() -> pd.DataFrame:
    for src in ("resumo_municipal_atual", "geo_vulnerabilidade_municipal", "met_biometeo"):
        if not table_exists(src):
            continue
        df = read_table(src)
        if df is None or df.empty:
            continue
        if not {"lat", "lon"}.issubset(df.columns):
            continue
        cols = [c for c in ("cod_ibge", "municipio", "lat", "lon") if c in df.columns]
        out = df[cols].dropna(subset=["lat", "lon"]).copy()
        if "cod_ibge" in out.columns:
            out["cod_ibge"] = (
                out["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
            )
            out = out[out["cod_ibge"].str.len() == 7].drop_duplicates("cod_ibge")
        if not out.empty:
            return out
    return pd.DataFrame()


def _archive_to_hist(archive: pd.DataFrame) -> pd.DataFrame:
    if archive is None or archive.empty:
        return pd.DataFrame()
    from sisclima.ingestion.historico_incremental import _prepare_clima

    # Archive não traz AQ; _prepare_clima aceita aq vazio
    return _prepare_clima(archive, pd.DataFrame())


def alongar_clima_archive(*, dias: int | None = None, max_municipios: int | None = None) -> dict[str, Any]:
    """Backfill Open-Meteo Archive → hist_clima (T, umidade, precipitação)."""
    from sisclima.ingestion.historico_incremental import upsert_clima_diario
    from sisclima.ingestion.openmeteo_archive import fetch_openmeteo_archive_municipios

    # ~5 anos civis: necessário para comparar o mesmo período (MM-DD) em vários anos.
    dias = int(dias) if dias is not None else _int_env("SERIES_ALONGAR_CLIMA_DIAS", 1826)
    mun = _municipios_geo()
    if mun.empty:
        return {"ok": False, "motivo": "sem municípios com lat/lon"}
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=dias - 1)
    log.info("Alongar clima archive: %s–%s · %s municípios", start, end, len(mun))
    arch = fetch_openmeteo_archive_municipios(
        mun,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        max_municipios=max_municipios,
    )
    if arch.empty:
        return {"ok": False, "motivo": "archive vazio", "dias": dias}
    if "precipitacao_mm" in arch.columns:
        arch["chuva_mm"] = arch["precipitacao_mm"]
    clima = _archive_to_hist(arch)
    n = upsert_clima_diario(clima) if not clima.empty else 0
    return {
        "ok": n > 0,
        "fonte": "openmeteo_archive",
        "dias_solicitados": dias,
        "linhas_archive": int(len(arch)),
        "upsert_hist": int(n),
        "municipios": int(arch["cod_ibge"].nunique()) if "cod_ibge" in arch.columns else 0,
        "inicio": start.isoformat(),
        "fim": end.isoformat(),
    }


def alongar_qualidade_ar(*, dias: int | None = None, max_municipios: int | None = None) -> dict[str, Any]:
    """Backfill Open-Meteo Air Quality → qualidade_ar_municipal (+ série estadual)."""
    from sisclima.ingestion.openmeteo_air_quality import fetch_openmeteo_air_quality_municipal

    dias = int(dias) if dias is not None else _int_env("SERIES_ALONGAR_AQ_DIAS", 92)
    # API open-meteo AQ: past_days tipicamente até 92
    dias = min(92, max(7, dias))
    mun = _municipios_geo()
    if mun.empty:
        return {"ok": False, "motivo": "sem municípios com lat/lon"}
    if max_municipios:
        mun = mun.head(int(max_municipios))
    log.info("Alongar AQ Open-Meteo: past_days=%s · %s municípios", dias, len(mun))
    aq_raw = fetch_openmeteo_air_quality_municipal(mun, past_days=dias)
    if aq_raw is None or aq_raw.empty:
        return {"ok": False, "motivo": "aq vazio", "dias": dias}

    aq = add_air_quality_indicators(aq_raw, SETTINGS)
    # Mescla com snapshot existente (não apagar datas que a nova carga não trouxe)
    prev = read_table("qualidade_ar_municipal") if table_exists("qualidade_ar_municipal") else pd.DataFrame()
    if prev is not None and not prev.empty:
        both = pd.concat([prev, aq], ignore_index=True)
        if {"cod_ibge", "data"}.issubset(both.columns):
            both["cod_ibge"] = both["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
            both["data"] = pd.to_datetime(both["data"], errors="coerce").dt.strftime("%Y-%m-%d")
            both = both.dropna(subset=["cod_ibge", "data"])
            both = both.drop_duplicates(["cod_ibge", "data"], keep="last")
        aq = both
    write_df(aq, "qualidade_ar_municipal")

    # Não faz upsert AQ→hist com linhas “só PM” (apagaria Tmáx no SQLite REPLACE).
    # A sazonalidade já funde qualidade_ar_municipal na série diária.

    # Série estadual
    if "data" in aq.columns and "pm25_ugm3" in aq.columns:
        tmp = aq.copy()
        tmp["data"] = pd.to_datetime(tmp["data"], errors="coerce").dt.strftime("%Y-%m-%d")
        aggs: dict[str, str] = {"pm25_ugm3": "mean"}
        for c in ("pm10_ugm3", "o3_ugm3", "no2_ugm3", "iq_ar_score", "indice_qualidade_ar_operacional"):
            if c in tmp.columns:
                aggs[c] = "mean"
        estado = tmp.dropna(subset=["data"]).groupby("data", as_index=False).agg(aggs)
        write_df(estado, "qualidade_ar_estado_serie_v6")

    return {
        "ok": True,
        "fonte": "openmeteo_air_quality",
        "dias": dias,
        "linhas_aq": int(len(aq)),
        "municipios": int(aq["cod_ibge"].nunique()) if "cod_ibge" in aq.columns else 0,
        "dias_unicos": int(pd.to_datetime(aq["data"], errors="coerce").dt.normalize().nunique())
        if "data" in aq.columns
        else 0,
    }


def completar_derivados_hist_clima(
    *,
    max_municipios: int | None = None,
) -> dict[str, Any]:
    """
    Completa UTCI proxy, heat index e risco cumulativo 3d em hist_clima.

    Open-Meteo Archive não entrega UTCI/risco; deriva a partir de tmax + umidade
    (vento/radiação com defaults operacionais do utci_proxy).
    """
    from sisclima.ingestion.historico_incremental import upsert_clima_diario
    from sisclima.utils.dates import now_iso

    if not table_exists("hist_clima_municipal_diario"):
        return {"ok": False, "motivo": "hist_ausente"}

    hist = read_table("hist_clima_municipal_diario")
    if hist is None or hist.empty:
        return {"ok": False, "motivo": "hist_vazio"}

    df = hist.copy()
    df["cod_ibge"] = df["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["cod_ibge", "data"])
    for c in ("tmax", "tmin", "umidade_media", "utci_proxy", "risco_cumulativo_3d", "pm25_ugm3"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if max_municipios:
        keep = sorted(df["cod_ibge"].dropna().unique().tolist())[: int(max_municipios)]
        df = df[df["cod_ibge"].isin(keep)].copy()

    t_umbral = float(
        ((SETTINGS.get("limiares_calor") or {}).get("risco_cumulativo") or {}).get("t_umbral", 39)
    )
    utci_alerta = float(
        ((SETTINGS.get("limiares_calor") or {}).get("onda_calor") or {}).get("utci_alerta", 38)
    )
    hi_alerta = float(
        ((SETTINGS.get("limiares_calor") or {}).get("onda_calor") or {}).get("heat_index_alerta", 40)
    )

    if "utci_proxy" not in df.columns:
        df["utci_proxy"] = np.nan
    need_utci = df["utci_proxy"].isna()

    # Vectorizado com defaults (vento 1 m/s, radiação 600 W/m²) — mesmo contrato do utci_proxy
    tmax = pd.to_numeric(df["tmax"], errors="coerce")
    rh = pd.to_numeric(df.get("umidade_media"), errors="coerce").fillna(45.0)
    humidity_penalty = np.maximum(0.0, rh.to_numpy(dtype=float) - 40.0) * 0.04
    radiation_penalty = max(0.0, 600.0 - 400.0) / 200.0 * 1.2
    wind_relief = min(3.0, 1.0 * 0.6)
    utci_arr = tmax.to_numpy(dtype=float) + humidity_penalty + radiation_penalty - wind_relief
    df.loc[need_utci, "utci_proxy"] = utci_arr[need_utci.to_numpy()]

    # Heat index vetorizado (Rothfusz em °C) — só para o termo de risco
    t_f = tmax.to_numpy(dtype=float) * 9.0 / 5.0 + 32.0
    rh_a = rh.to_numpy(dtype=float)
    hi_f = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh_a
        - 0.22475541 * t_f * rh_a
        - 0.00683783 * t_f * t_f
        - 0.05481717 * rh_a * rh_a
        + 0.00122874 * t_f * t_f * rh_a
        + 0.00085282 * t_f * rh_a * rh_a
        - 0.00000199 * t_f * t_f * rh_a * rh_a
    )
    hi_c = (hi_f - 32.0) * 5.0 / 9.0
    # abaixo de ~26.7°C o HI oficial = T; espelha heat_index_celsius
    hi_c = np.where(np.isnan(tmax.to_numpy(dtype=float)), np.nan, np.where(t_f < 80.0, tmax.to_numpy(dtype=float), hi_c))

    # risco diário simplificado + cumulativo 3d (sem EHF histórico — conservador)
    excesso_tmax = np.maximum(0.0, np.nan_to_num(tmax.to_numpy(dtype=float), nan=0.0) - t_umbral)
    excesso_utci = np.maximum(
        0.0,
        np.nan_to_num(pd.to_numeric(df["utci_proxy"], errors="coerce").to_numpy(dtype=float), nan=0.0)
        - utci_alerta,
    )
    excesso_hi = np.maximum(0.0, np.nan_to_num(hi_c, nan=0.0) - hi_alerta) * 0.25
    df["risco_calor_diario"] = excesso_tmax + excesso_utci + excesso_hi
    df = df.sort_values(["cod_ibge", "data"])
    df["risco_cumulativo_3d"] = (
        df.groupby("cod_ibge", group_keys=False)["risco_calor_diario"]
        .transform(lambda s: s.rolling(3, min_periods=1).sum())
    )

    # Enriquecer PM2.5 a partir de qualidade_ar_municipal
    n_pm_fill = 0
    if table_exists("qualidade_ar_municipal"):
        aq = read_table("qualidade_ar_municipal")
        if aq is not None and not aq.empty and "pm25_ugm3" in aq.columns:
            aq = aq.copy()
            aq["cod_ibge"] = aq["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
            aq["data"] = pd.to_datetime(aq["data"], errors="coerce").dt.strftime("%Y-%m-%d")
            aq["pm25_ugm3"] = pd.to_numeric(aq["pm25_ugm3"], errors="coerce")
            aq = aq.dropna(subset=["cod_ibge", "data", "pm25_ugm3"]).drop_duplicates(
                ["cod_ibge", "data"], keep="last"
            )
            if "pm25_ugm3" not in df.columns:
                df["pm25_ugm3"] = np.nan
            else:
                df["pm25_ugm3"] = pd.to_numeric(df["pm25_ugm3"], errors="coerce")
            before = int(df["pm25_ugm3"].notna().sum())
            df["_d"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m-%d")
            m = df.merge(
                aq[["cod_ibge", "data", "pm25_ugm3"]].rename(
                    columns={"data": "_d", "pm25_ugm3": "pm25_aq"}
                ),
                on=["cod_ibge", "_d"],
                how="left",
            )
            fill_mask = m["pm25_ugm3"].isna() & m["pm25_aq"].notna()
            m.loc[fill_mask, "pm25_ugm3"] = m.loc[fill_mask, "pm25_aq"]
            df["pm25_ugm3"] = m["pm25_ugm3"].values
            n_pm_fill = int(df["pm25_ugm3"].notna().sum()) - before
            df = df.drop(columns=["_d"], errors="ignore")

    df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["fonte"] = df.get("fonte", pd.Series(["derivado_hist"] * len(df))).fillna("derivado_hist")
    df["atualizado_em"] = now_iso()
    cols = [
        c
        for c in (
            "cod_ibge",
            "data",
            "tmax",
            "tmin",
            "utci_proxy",
            "umidade_media",
            "precipitacao_mm",
            "risco_cumulativo_3d",
            "pm25_ugm3",
            "fonte",
            "atualizado_em",
        )
        if c in df.columns
    ]
    n_up = upsert_clima_diario(df[cols])
    n = len(df)
    return {
        "ok": n_up > 0,
        "linhas": n,
        "upsert": int(n_up),
        "utci_pct": round(100.0 * float(df["utci_proxy"].notna().mean()), 1) if n else 0.0,
        "risco_pct": round(100.0 * float(df["risco_cumulativo_3d"].notna().mean()), 1) if n else 0.0,
        "pm25_pct": (
            round(100.0 * float(pd.to_numeric(df.get("pm25_ugm3"), errors="coerce").notna().mean()), 1)
            if n and "pm25_ugm3" in df.columns
            else 0.0
        ),
        "pm25_preenchidos_aq": n_pm_fill,
        "t_umbral": t_umbral,
        "utci_alerta": utci_alerta,
        "nota": "UTCI/risco derivados do archive; PM2.5 via qualidade_ar_municipal (~92d API).",
    }


def alongar_series_clima_saude(
    *,
    dias_clima: int | None = None,
    dias_aq: int | None = None,
    max_municipios: int | None = None,
    skip_archive: bool = False,
    skip_aq: bool = False,
    completar_derivados: bool = True,
) -> dict[str, Any]:
    """Executa alongamento clima + AQ, completa derivados e reporta cobertura."""
    out: dict[str, Any] = {"ok": True}
    if not skip_archive and as_bool(env("USE_OPENMETEO", "true"), True):
        out["clima"] = alongar_clima_archive(dias=dias_clima, max_municipios=max_municipios)
    else:
        out["clima"] = {"ok": False, "motivo": "skip_archive"}
    if not skip_aq and as_bool(env("USE_OPENMETEO_AQ", "true"), True):
        out["aq"] = alongar_qualidade_ar(dias=dias_aq, max_municipios=max_municipios)
    else:
        out["aq"] = {"ok": False, "motivo": "skip_aq"}
    if completar_derivados:
        out["derivados"] = completar_derivados_hist_clima(max_municipios=max_municipios)
    out["ok"] = bool(
        (out.get("clima") or {}).get("ok")
        or (out.get("aq") or {}).get("ok")
        or (out.get("derivados") or {}).get("ok")
    )
    return out


def load_met_alongado_para_sazonalidade() -> pd.DataFrame:
    """Une hist_clima (longo) com met_biometeo (derivados recentes) para sazonalidade."""
    hist = read_table("hist_clima_municipal_diario") if table_exists("hist_clima_municipal_diario") else pd.DataFrame()
    met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    frames: list[pd.DataFrame] = []
    if hist is not None and not hist.empty:
        frames.append(hist)
    if met is not None and not met.empty:
        frames.append(met)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True, sort=False)
    if "cod_ibge" in out.columns and "data" in out.columns:
        out["cod_ibge"] = out["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)
        out["data"] = pd.to_datetime(out["data"], errors="coerce")
        out = out.dropna(subset=["cod_ibge", "data"])
        # Preferir met_biometeo (última ocorrência no concat) nos derivados
        out = out.sort_values("data").drop_duplicates(["cod_ibge", "data"], keep="last")
    return out


if __name__ == "__main__":
    import json

    print(json.dumps(alongar_series_clima_saude(), ensure_ascii=False, indent=2, default=str))
