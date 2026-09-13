# -*- coding: utf-8 -*-
"""Frescor da aba Sazonalidade / OR — OR ao vivo + sazonalidade/lags atualizados.

Garante que a aba não fique presa a tabelas vazias ou defasadas do último enrich.
Inclui cobertura climática Open-Meteo + Copernicus/CAMS.
Não altera ``nivel`` operacional.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from sisclima.core.logging_utils import get_logger
from sisclima.engines.clima_exposicoes import (
    CLIMA_ROTULOS,
    available_climate_cols,
    climate_coverage_report,
    ensure_amplitude_termica,
)

log = get_logger(__name__)

SAZ_TABLES = (
    "sazonalidade_indice_mensal_v1",
    "sazonalidade_heatmap_semana_ano_v1",
    "sazonalidade_perfil_semana_epi_v1",
    "sazonalidade_picos_v1",
    "clima_desfecho_lags_v1",
    "sazonalidade_clima_cobertura_v1",
)
OR_TABLE = "analise_clima_saude_odds_ratio_v1"


def _parse_proc(df: pd.DataFrame | None) -> datetime | None:
    if df is None or df.empty or "data_processamento" not in df.columns:
        return None
    ts = pd.to_datetime(df["data_processamento"], errors="coerce").dropna()
    if ts.empty:
        return None
    val = ts.max().to_pydatetime()
    if val.tzinfo is not None:
        val = val.replace(tzinfo=None)
    return val


def _stale(df: pd.DataFrame | None, *, max_age_hours: float = 24.0) -> bool:
    if df is None or df.empty:
        return True
    proc = _parse_proc(df)
    if proc is None:
        return True
    return proc < datetime.now() - timedelta(hours=max_age_hours)


def _lags_missing_climate(lags: pd.DataFrame | None, expected: list[str]) -> bool:
    """True se a tabela de lags não cobre exposições climáticas disponíveis nas fontes."""
    if not expected:
        return False
    if lags is None or lags.empty or "exposicao" not in lags.columns:
        return True
    present = {str(x) for x in lags["exposicao"].dropna().unique().tolist()}
    # exige pelo menos as principais quando disponíveis
    criticas = [
        c
        for c in (
            "tmax",
            "tmin",
            "umidade_media",
            "precipitacao_mm",
            "pm25_ugm3",
            "pm10_ugm3",
            "iq_ar_score",
            "utci_proxy",
        )
        if c in expected
    ]
    if not criticas:
        return False
    missing = [c for c in criticas if c not in present]
    return len(missing) > 0


def refresh_odds_live(resumo: pd.DataFrame | None, *, persist: bool = False) -> pd.DataFrame:
    """Recalcula OR ecológico a partir do resumo atual (sempre fresco)."""
    from sisclima.engines.odds_ratio import compute_climate_health_ors

    if resumo is None or resumo.empty:
        return pd.DataFrame()
    work = ensure_amplitude_termica(resumo)
    odds = compute_climate_health_ors(work)
    if persist and not odds.empty:
        try:
            from sisclima.core.db import write_df

            write_df(odds, OR_TABLE)
        except Exception as exc:  # noqa: BLE001
            log.warning("Persistência OR fresco falhou: %s", exc)
    return odds


def refresh_seasonality_pack(
    *,
    force: bool = False,
    max_age_hours: float = 24.0,
    persist: bool = True,
) -> dict[str, pd.DataFrame]:
    """Recomputa índices sazonais/lags se vazios, defasados ou sem cobertura climática."""
    from sisclima.core.db import read_table, table_exists, write_df
    from sisclima.engines.seasonality import compute_seasonality_outputs

    current: dict[str, pd.DataFrame] = {}
    for t in SAZ_TABLES:
        current[t] = read_table(t) if table_exists(t) else pd.DataFrame()

    met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    aq = (
        read_table("qualidade_ar_municipal")
        if table_exists("qualidade_ar_municipal")
        else pd.DataFrame()
    )
    expected = available_climate_cols(met) + [
        c for c in available_climate_cols(aq) if c not in available_climate_cols(met)
    ]
    if "tmax" in (met.columns if met is not None else []) and "tmin" in (met.columns if met is not None else []):
        if "amplitude_termica" not in expected:
            expected.append("amplitude_termica")

    need = force or any(_stale(current[t], max_age_hours=max_age_hours) for t in SAZ_TABLES)
    if current["sazonalidade_indice_mensal_v1"].empty or current["sazonalidade_heatmap_semana_ano_v1"].empty:
        need = True
    if _lags_missing_climate(current.get("clima_desfecho_lags_v1"), expected):
        need = True
        log.info("Frescor sazonalidade: lags sem cobertura climática completa — recomputando")
    if not need:
        return current

    sivep = read_table("epi_sivep_srag") if table_exists("epi_sivep_srag") else pd.DataFrame()
    arbo = (
        read_table("epi_arboviroses_municipal")
        if table_exists("epi_arboviroses_municipal")
        else pd.DataFrame()
    )
    press = (
        read_table("epi_pressao_assistencial")
        if table_exists("epi_pressao_assistencial")
        else pd.DataFrame()
    )
    occ = (
        read_table("hospital_ocupacao_municipio")
        if table_exists("hospital_ocupacao_municipio")
        else pd.DataFrame()
    )
    if met is None or met.empty:
        log.warning("Frescor sazonalidade: met_biometeo vazio — mantém tabelas atuais")
        return current

    try:
        saz = compute_seasonality_outputs(met, sivep, arbo, press, occ, qualidade_ar=aq)
    except Exception as exc:  # noqa: BLE001
        log.warning("Frescor sazonalidade falhou: %s", exc)
        return current

    if persist:
        for tname, frame in saz.items():
            try:
                write_df(frame if frame is not None else pd.DataFrame(), tname)
            except Exception as exc:  # noqa: BLE001
                log.warning("Persistência %s falhou: %s", tname, exc)
    return saz


def load_sazonalidade_fresco(
    resumo: pd.DataFrame | None,
    *,
    persist: bool = True,
    max_age_hours: float = 24.0,
) -> dict[str, Any]:
    """Pacote pronto para a aba: OR vivo + sazonalidade/lags frescos + meta."""
    from sisclima.core.db import read_table, table_exists

    odds = refresh_odds_live(resumo, persist=persist)
    saz = refresh_seasonality_pack(force=False, max_age_hours=max_age_hours, persist=persist)

    def _get(name: str) -> pd.DataFrame:
        if name in saz and saz[name] is not None and not saz[name].empty:
            return saz[name]
        return read_table(name) if table_exists(name) else pd.DataFrame()

    met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    aq = (
        read_table("qualidade_ar_municipal")
        if table_exists("qualidade_ar_municipal")
        else pd.DataFrame()
    )
    cobertura_rep = climate_coverage_report(met, aq)

    pack = {
        "odds": odds if odds is not None else pd.DataFrame(),
        "mensal": _get("sazonalidade_indice_mensal_v1"),
        "heatmap": _get("sazonalidade_heatmap_semana_ano_v1"),
        "perfil": _get("sazonalidade_perfil_semana_epi_v1"),
        "picos": _get("sazonalidade_picos_v1"),
        "lags": _get("clima_desfecho_lags_v1"),
        "cobertura": _get("sazonalidade_clima_cobertura_v1"),
        "cobertura_fontes": cobertura_rep,
    }
    n_sig = 0
    if not pack["odds"].empty and "significativo_005" in pack["odds"].columns:
        n_sig = int(pd.to_numeric(pack["odds"]["significativo_005"], errors="coerce").fillna(0).astype(int).sum())
    n_lag_sig = 0
    if not pack["lags"].empty and "significativo_005" in pack["lags"].columns:
        n_lag_sig = int(pd.to_numeric(pack["lags"]["significativo_005"], errors="coerce").fillna(0).astype(int).sum())

    lag_expos = (
        sorted({str(x) for x in pack["lags"]["exposicao"].dropna().unique()})
        if not pack["lags"].empty and "exposicao" in pack["lags"].columns
        else []
    )
    pack["meta"] = {
        "or_n": int(len(pack["odds"])),
        "or_sig": n_sig,
        "lag_sig": n_lag_sig,
        "or_proc": _parse_proc(pack["odds"]),
        "saz_proc": _parse_proc(pack["lags"]) or _parse_proc(pack["mensal"]),
        "clima_n": int(cobertura_rep.get("n_disponiveis") or 0),
        "clima_catalogo": int(cobertura_rep.get("n_catalogo") or 0),
        "lag_exposicoes": lag_expos,
        "lag_exposicoes_rotulos": [CLIMA_ROTULOS.get(c, c) for c in lag_expos],
        "ok": bool(
            not pack["odds"].empty
            or not pack["mensal"].empty
            or not pack["heatmap"].empty
        ),
    }
    return pack
