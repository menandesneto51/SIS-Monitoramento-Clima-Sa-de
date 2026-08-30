# -*- coding: utf-8 -*-
"""Base histórica incremental (clima + saúde) — upsert por (cod_ibge, data).

O snapshot operacional continua com replace diário. Estas tabelas ``hist_*``
acumulam série para painel/boletim sem apagar o passado.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from sisclima.core.config import as_bool, env
from sisclima.core.db import (
    init_db,
    read_table,
    table_count,
    table_exists,
    upsert_df,
)
from sisclima.core.logging_utils import get_logger
from sisclima.utils.dates import now_iso

log = get_logger(__name__)

TABLE_CLIMA = "hist_clima_municipal_diario"
TABLE_SAUDE = "hist_saude_municipal_diario"
TABLE_WM = "etl_watermarks"
CONFLICT = ["cod_ibge", "data"]


def hist_enabled() -> bool:
    return as_bool(env("HIST_INCREMENTAL_ENABLED", "true"), True)


def bootstrap_on_empty() -> bool:
    return as_bool(env("HIST_BOOTSTRAP_ON_EMPTY", "true"), True)


def lookback_days() -> int:
    try:
        return max(1, int(env("HIST_LOOKBACK_DAYS", "14") or 14))
    except (TypeError, ValueError):
        return 14


def ensure_hist_schema() -> None:
    init_db()


def _norm_ibge(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.extract(r"(\d{6,7})", expand=False)
        .fillna("")
        .str.zfill(7)
    )


def _norm_data(s: pd.Series) -> pd.Series:
    dt = pd.to_datetime(s, errors="coerce")
    return dt.dt.strftime("%Y-%m-%d")


def _set_watermark(fonte: str, *, watermark_ts: str, status: str, n_rows: int) -> None:
    ensure_hist_schema()
    row = pd.DataFrame(
        [
            {
                "fonte": fonte,
                "watermark_ts": watermark_ts,
                "last_run_at": now_iso(),
                "last_status": status,
                "n_rows": int(n_rows),
            }
        ]
    )
    upsert_df(row, TABLE_WM, ["fonte"])


def _prepare_clima(met: pd.DataFrame, aq: pd.DataFrame | None = None) -> pd.DataFrame:
    if met is None or met.empty:
        return pd.DataFrame()
    m = met.copy()
    if "cod_ibge" not in m.columns or "data" not in m.columns:
        return pd.DataFrame()
    m["cod_ibge"] = _norm_ibge(m["cod_ibge"])
    m["data"] = _norm_data(m["data"])
    m = m[(m["cod_ibge"].str.len() == 7) & m["data"].notna() & (m["data"] != "NaT")]
    if m.empty:
        return pd.DataFrame()
    keep = [
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
            "fonte",
        )
        if c in m.columns
    ]
    out = m[keep].copy()
    # Agrega se houver duplicatas no snapshot
    num_cols = [c for c in out.columns if c not in {"cod_ibge", "data", "fonte"}]
    agg = {c: "mean" for c in num_cols}
    if "fonte" in out.columns:
        agg["fonte"] = "last"
    out = out.groupby(["cod_ibge", "data"], as_index=False).agg(agg)

    if aq is not None and not aq.empty and "cod_ibge" in aq.columns and "data" in aq.columns:
        a = aq.copy()
        a["cod_ibge"] = _norm_ibge(a["cod_ibge"])
        a["data"] = _norm_data(a["data"])
        a = a[(a["cod_ibge"].str.len() == 7) & a["data"].notna()]
        if "pm25_ugm3" in a.columns:
            ap = (
                a.groupby(["cod_ibge", "data"], as_index=False)["pm25_ugm3"]
                .mean()
            )
            out = out.merge(ap, on=["cod_ibge", "data"], how="left")
    if "pm25_ugm3" not in out.columns:
        out["pm25_ugm3"] = pd.NA
    out["atualizado_em"] = now_iso()
    if "fonte" not in out.columns:
        out["fonte"] = "operacional"
    cols = [
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
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    return out[cols]


def _prepare_saude(
    sivep: pd.DataFrame | None,
    arbo: pd.DataFrame | None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if sivep is not None and not sivep.empty and "cod_ibge" in sivep.columns and "data" in sivep.columns:
        s = sivep.copy()
        s["cod_ibge"] = _norm_ibge(s["cod_ibge"])
        s["data"] = _norm_data(s["data"])
        s = s[(s["cod_ibge"].str.len() == 7) & s["data"].notna()]
        if "casos_srag" in s.columns:
            sg = s.groupby(["cod_ibge", "data"], as_index=False)["casos_srag"].sum()
            frames.append(sg)
    if arbo is not None and not arbo.empty and "cod_ibge" in arbo.columns and "data" in arbo.columns:
        a = arbo.copy()
        a["cod_ibge"] = _norm_ibge(a["cod_ibge"])
        a["data"] = _norm_data(a["data"])
        a = a[(a["cod_ibge"].str.len() == 7) & a["data"].notna()]
        cols_map = {
            "casos_arbovirus": "casos_arbovirus_7d" if "casos_arbovirus_7d" in a.columns else "casos_arbovirus",
            "casos_dengue": "casos_dengue_7d" if "casos_dengue_7d" in a.columns else "casos_dengue",
            "casos_chikungunya": "casos_chikungunya_7d" if "casos_chikungunya_7d" in a.columns else "casos_chikungunya",
            "casos_zika": "casos_zika_7d" if "casos_zika_7d" in a.columns else "casos_zika",
        }
        use = {"cod_ibge", "data"}
        rename = {}
        for dest, src in cols_map.items():
            if src in a.columns:
                rename[src] = dest
                use.add(src)
        if len(use) > 2:
            ag = a[list(use)].rename(columns=rename)
            num = [c for c in ag.columns if c not in {"cod_ibge", "data"}]
            ag = ag.groupby(["cod_ibge", "data"], as_index=False)[num].sum()
            frames.append(ag)
    if not frames:
        return pd.DataFrame()
    out = frames[0]
    for fr in frames[1:]:
        out = out.merge(fr, on=["cod_ibge", "data"], how="outer")
    out["fonte"] = "operacional"
    out["atualizado_em"] = now_iso()
    for c in (
        "casos_srag",
        "casos_arbovirus",
        "casos_dengue",
        "casos_chikungunya",
        "casos_zika",
        "fonte",
        "atualizado_em",
    ):
        if c not in out.columns:
            out[c] = pd.NA
    return out[
        [
            "cod_ibge",
            "data",
            "casos_srag",
            "casos_arbovirus",
            "casos_dengue",
            "casos_chikungunya",
            "casos_zika",
            "fonte",
            "atualizado_em",
        ]
    ]


def upsert_clima_diario(df: pd.DataFrame) -> int:
    ensure_hist_schema()
    n = upsert_df(df, TABLE_CLIMA, CONFLICT)
    if n:
        wm = str(pd.to_datetime(df["data"], errors="coerce").max().date()) if "data" in df.columns else now_iso()
        _set_watermark("hist_clima", watermark_ts=wm, status="ok", n_rows=n)
    return n


def upsert_saude_diario(df: pd.DataFrame) -> int:
    ensure_hist_schema()
    n = upsert_df(df, TABLE_SAUDE, CONFLICT)
    if n:
        wm = str(pd.to_datetime(df["data"], errors="coerce").max().date()) if "data" in df.columns else now_iso()
        _set_watermark("hist_saude", watermark_ts=wm, status="ok", n_rows=n)
    return n


def bootstrap_from_operational() -> dict[str, Any]:
    """Carga inicial a partir das tabelas operacionais (sem backfill remoto)."""
    ensure_hist_schema()
    met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    aq = read_table("qualidade_ar_municipal") if table_exists("qualidade_ar_municipal") else pd.DataFrame()
    sivep = read_table("epi_sivep_srag") if table_exists("epi_sivep_srag") else pd.DataFrame()
    arbo = (
        read_table("epi_arboviroses_municipal")
        if table_exists("epi_arboviroses_municipal")
        else pd.DataFrame()
    )
    clima = _prepare_clima(met, aq)
    saude = _prepare_saude(sivep, arbo)
    n_c = upsert_clima_diario(clima) if not clima.empty else 0
    n_s = upsert_saude_diario(saude) if not saude.empty else 0
    log.info("Bootstrap histórico: clima=%s saude=%s", n_c, n_s)
    return {"clima": n_c, "saude": n_s, "ok": True}


def _filter_lookback(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty or "data" not in df.columns:
        return df
    cutoff = (pd.Timestamp.now().normalize() - pd.Timedelta(days=int(days))).strftime("%Y-%m-%d")
    d = _norm_data(df["data"])
    return df.loc[d >= cutoff].copy()


def append_from_daily_snapshot() -> dict[str, Any]:
    """Upsert da janela recente a partir do snapshot operacional da rodada."""
    if not hist_enabled():
        return {"ok": False, "motivo": "HIST_INCREMENTAL_ENABLED=false"}

    ensure_hist_schema()
    out: dict[str, Any] = {"ok": True, "bootstrapped": False}

    n_clima = table_count(TABLE_CLIMA) if table_exists(TABLE_CLIMA) else 0
    n_saude = table_count(TABLE_SAUDE) if table_exists(TABLE_SAUDE) else 0
    if bootstrap_on_empty() and n_clima == 0 and n_saude == 0:
        boot = bootstrap_from_operational()
        out["bootstrapped"] = True
        out["bootstrap"] = boot
        return out

    days = lookback_days()
    met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    aq = read_table("qualidade_ar_municipal") if table_exists("qualidade_ar_municipal") else pd.DataFrame()
    sivep = read_table("epi_sivep_srag") if table_exists("epi_sivep_srag") else pd.DataFrame()
    arbo = (
        read_table("epi_arboviroses_municipal")
        if table_exists("epi_arboviroses_municipal")
        else pd.DataFrame()
    )

    clima = _filter_lookback(_prepare_clima(met, aq), days)
    saude = _filter_lookback(_prepare_saude(sivep, arbo), days)
    n_c = upsert_clima_diario(clima) if not clima.empty else 0
    n_s = upsert_saude_diario(saude) if not saude.empty else 0
    out.update({"clima": n_c, "saude": n_s, "lookback_days": days})
    log.info("Histórico incremental: clima=%s saude=%s lookback=%sd", n_c, n_s, days)
    return out
