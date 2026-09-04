"""Ondas de calor no método GeoCalor / Nairn & Fawcett (EHF).

Definição (GeoCalor Fiocruz / LAGAS-UnB):
- Tmédia diária; T3d = média móvel de 3 dias; T30d = média dos 30 dias anteriores.
- EHIsig = T3d − P95(Tmédia local)
- EHIaccl = T3d − T30d
- EHF = EHIsig × max(1, EHIaccl)
- Evento: ≥ 3 dias consecutivos com EHF > 0
- Intensidade (sobre dias com EHF > 0 no município):
  baixa 0 < EHF ≤ EHF85; severa EHF85 < EHF ≤ 3×EHF85; extrema EHF > 3×EHF85
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

METODOLOGIA = "GeoCalor_EHF_NairnFawcett_3d"
MIN_DIAS_EVENTO = 3


def _ibge7(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)


def ensure_tmedia(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "tmedia" not in out.columns or out["tmedia"].isna().all():
        if {"tmax", "tmin"}.issubset(out.columns):
            out["tmedia"] = (
                pd.to_numeric(out["tmax"], errors="coerce")
                + pd.to_numeric(out["tmin"], errors="coerce")
            ) / 2.0
        else:
            out["tmedia"] = pd.to_numeric(out.get("tmedia"), errors="coerce")
    else:
        out["tmedia"] = pd.to_numeric(out["tmedia"], errors="coerce")
    return out


def compute_ehf_geocalor(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula EHI/EHF e classifica dias de onda (is_hw_day) por município."""
    if df is None or df.empty:
        return pd.DataFrame()

    out = ensure_tmedia(df)
    out["cod_ibge"] = _ibge7(out["cod_ibge"])
    out["data"] = pd.to_datetime(out["data"], errors="coerce")
    out = out.dropna(subset=["cod_ibge", "data", "tmedia"]).sort_values(["cod_ibge", "data"])

    frames = []
    for _cod, g in out.groupby("cod_ibge", sort=False):
        g = g.copy()
        t = g["tmedia"]
        t95 = float(t.quantile(0.95)) if t.notna().sum() else np.nan
        g["t95_tmedia"] = t95
        g["tmedia_3d"] = t.rolling(3, min_periods=3).mean()
        g["tmedia_30d_prev"] = t.shift(1).rolling(30, min_periods=15).mean()
        g["ehi_sig"] = g["tmedia_3d"] - t95
        g["ehi_accl"] = g["tmedia_3d"] - g["tmedia_30d_prev"]
        g["ehf"] = g["ehi_sig"] * np.maximum(1.0, g["ehi_accl"])
        pos = g.loc[g["ehf"] > 0, "ehf"]
        ehf85 = float(pos.quantile(0.85)) if len(pos) else np.nan
        g["ehf85"] = ehf85
        g["intensidade"] = _classificar_intensidade(g["ehf"], ehf85)
        g["is_hw_day"] = 0
        frames.append(g)

    daily = pd.concat(frames, ignore_index=True)
    daily = _marcar_dias_evento(daily)
    daily["data"] = daily["data"].dt.strftime("%Y-%m-%d")
    daily["atualizado_em"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return daily


def _classificar_intensidade(ehf: pd.Series, ehf85: float) -> pd.Series:
    out = pd.Series(index=ehf.index, dtype=object)
    out[:] = None
    pos = ehf > 0
    if not pos.any() or pd.isna(ehf85) or ehf85 <= 0:
        out.loc[pos] = "baixa"
        return out
    out.loc[pos & (ehf <= ehf85)] = "baixa"
    out.loc[pos & (ehf > ehf85) & (ehf <= 3 * ehf85)] = "severa"
    out.loc[pos & (ehf > 3 * ehf85)] = "extrema"
    return out


def _marcar_dias_evento(df: pd.DataFrame) -> pd.DataFrame:
    """is_hw_day = 1 só em sequências com EHF>0 de pelo menos 3 dias."""
    out = df.copy()
    flags = []
    for _cod, g in out.groupby("cod_ibge", sort=False):
        ehf_pos = (pd.to_numeric(g["ehf"], errors="coerce").fillna(0) > 0).to_numpy()
        n = len(ehf_pos)
        hw = np.zeros(n, dtype=int)
        i = 0
        while i < n:
            if not ehf_pos[i]:
                i += 1
                continue
            j = i
            while j < n and ehf_pos[j]:
                j += 1
            if (j - i) >= MIN_DIAS_EVENTO:
                hw[i:j] = 1
            i = j
        g = g.copy()
        g["is_hw_day"] = hw
        flags.append(g)
    return pd.concat(flags, ignore_index=True)


def eventos_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    """Catálogo de eventos (≥3 dias consecutivos com EHF>0)."""
    if daily is None or daily.empty:
        return pd.DataFrame()

    work = daily.copy()
    work["cod_ibge"] = _ibge7(work["cod_ibge"])
    work["data"] = pd.to_datetime(work["data"], errors="coerce")
    work["ehf"] = pd.to_numeric(work["ehf"], errors="coerce")
    work = work.sort_values(["cod_ibge", "data"])

    rows = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for cod, g in work.groupby("cod_ibge", sort=False):
        g = g.reset_index(drop=True)
        ehf_pos = (g["ehf"].fillna(0) > 0).to_numpy()
        n = len(g)
        i = 0
        mun = None
        if "municipio" in g.columns:
            mun = g["municipio"].dropna().astype(str)
            mun = mun.iloc[0] if len(mun) else None
        while i < n:
            if not ehf_pos[i]:
                i += 1
                continue
            j = i
            while j < n and ehf_pos[j]:
                j += 1
            dur = j - i
            if dur >= MIN_DIAS_EVENTO:
                bloco = g.iloc[i:j]
                ints = bloco["intensidade"].dropna().astype(str)
                if (ints == "extrema").any():
                    peak = "extrema"
                elif (ints == "severa").any():
                    peak = "severa"
                else:
                    peak = "baixa"
                rows.append(
                    {
                        "cod_ibge": str(cod).zfill(7),
                        "municipio": mun,
                        "data_inicio": bloco["data"].min().strftime("%Y-%m-%d"),
                        "data_fim": bloco["data"].max().strftime("%Y-%m-%d"),
                        "duracao_dias": int(dur),
                        "ehf_max": float(bloco["ehf"].max()),
                        "ehf_medio": float(bloco["ehf"].mean()),
                        "intensidade": peak,
                        "n_dias_baixa": int((ints == "baixa").sum()),
                        "n_dias_severa": int((ints == "severa").sum()),
                        "n_dias_extrema": int((ints == "extrema").sum()),
                        "metodologia": METODOLOGIA,
                        "fonte": str(bloco["fonte"].iloc[0]) if "fonte" in bloco.columns else "openmeteo_archive",
                        "atualizado_em": now,
                    }
                )
            i = j
    return pd.DataFrame(rows)


def colunas_diario_persistencia() -> list[str]:
    return [
        "cod_ibge",
        "data",
        "municipio",
        "tmax",
        "tmin",
        "tmedia",
        "umidade_media",
        "precipitacao_mm",
        "ehi_sig",
        "ehi_accl",
        "ehf",
        "is_hw_day",
        "intensidade",
        "fonte",
        "atualizado_em",
    ]
