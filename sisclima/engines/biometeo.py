from __future__ import annotations

import numpy as np
import pandas as pd

from sisclima.utils.municipios import ensure_municipality, municipality_cols


# ============================================================
# SIS MT CLIMA-SAÚDE
# Arquivo: sisclima/engines/biometeo.py
#
# Versão consolidada para substituir o arquivo existente.
#
# Objetivos:
# - Calcular indicadores biometeorológicos municipais.
# - Evitar risco_cumulativo_3d sempre zerado por limiar fixo alto.
# - Incorporar proxy operacional de onda de calor compatível com:
#   temperatura média diária, P95 local/proxy e >= 2 dias consecutivos.
#
# Observação metodológica:
# - O P95 climatológico ideal deve vir de base histórica municipal.
# - Se não houver coluna histórica de P95, o módulo usa proxy operacional
#   configurável para vigilância em tempo real, sem declarar climatologia real.
# ============================================================


def _is_empty(df: pd.DataFrame | None) -> bool:
    return df is None or df.empty


def _safe_series(df: pd.DataFrame, value=np.nan) -> pd.Series:
    return pd.Series([value] * len(df), index=df.index)


def _sort_municipal(df: pd.DataFrame, date_col: str = "data") -> pd.DataFrame:
    out = df.copy()
    mcols = municipality_cols(out)

    if date_col in out.columns:
        out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
        sort_cols = mcols + [date_col] if mcols else [date_col]
        out = out.sort_values(sort_cols)

    return out


def heat_index_celsius(temp_c: float, rh: float) -> float:
    """
    Heat Index NOAA aproximado em Celsius.
    Para temperaturas abaixo de ~26,7 °C, retorna a própria temperatura
    para evitar extrapolação indevida da fórmula.
    """
    if pd.isna(temp_c) or pd.isna(rh):
        return np.nan

    temp_c = float(temp_c)
    rh = float(rh)

    if temp_c < 26.7:
        return temp_c

    t = temp_c * 9 / 5 + 32

    hi_f = (
        -42.379
        + 2.04901523 * t
        + 10.14333127 * rh
        - 0.22475541 * t * rh
        - 0.00683783 * t * t
        - 0.05481717 * rh * rh
        + 0.00122874 * t * t * rh
        + 0.00085282 * t * rh * rh
        - 0.00000199 * t * t * rh * rh
    )

    return float((hi_f - 32) * 5 / 9)


def utci_proxy(
    temp_c: float,
    rh: float,
    wind_ms: float | None = None,
    radiation_wm2: float | None = None,
) -> float:
    """
    Proxy operacional de UTCI para semaforização.

    Não substitui UTCI formal com Tmrt. Serve como indicador operacional
    conservador para triagem municipal em tempo real.
    """
    if pd.isna(temp_c):
        return np.nan

    temp_c = float(temp_c)
    rh = 45 if pd.isna(rh) else float(rh)

    wind_ms = 1.0 if wind_ms is None or pd.isna(wind_ms) else max(float(wind_ms), 0.1)
    radiation_wm2 = 600 if radiation_wm2 is None or pd.isna(radiation_wm2) else float(radiation_wm2)

    humidity_penalty = max(0.0, rh - 40.0) * 0.04
    radiation_penalty = max(0.0, radiation_wm2 - 400.0) / 200.0 * 1.2
    wind_relief = min(3.0, wind_ms * 0.6)

    return float(temp_c + humidity_penalty + radiation_penalty - wind_relief)


def _rolling_by_municipio(
    out: pd.DataFrame,
    value_col: str,
    window: int,
    min_periods: int,
    func: str = "mean",
) -> pd.Series:
    mcols = municipality_cols(out)

    if value_col not in out.columns:
        return _safe_series(out)

    if mcols:
        grouped = out.groupby(mcols, group_keys=False)[value_col]
        if func == "median_expanding":
            return grouped.apply(lambda s: s.expanding(min_periods=min_periods).median())
        if func == "max":
            return grouped.apply(lambda s: s.rolling(window, min_periods=min_periods).max())
        if func == "sum":
            return grouped.apply(lambda s: s.rolling(window, min_periods=min_periods).sum())
        return grouped.apply(lambda s: s.rolling(window, min_periods=min_periods).mean())

    if func == "median_expanding":
        return out[value_col].expanding(min_periods=min_periods).median()
    if func == "max":
        return out[value_col].rolling(window, min_periods=min_periods).max()
    if func == "sum":
        return out[value_col].rolling(window, min_periods=min_periods).sum()

    return out[value_col].rolling(window, min_periods=min_periods).mean()


def _get_onda_cfg(settings: dict) -> dict:
    settings = settings or {}
    lim_calor = settings.get("limiares_calor", {}) or {}
    cfg = lim_calor.get("onda_calor", {}) or {}

    for k in [
        "min_dias",
        "tmedia_p95_fallback",
        "tmax_p95_fallback",
        "utci_alerta",
        "heat_index_alerta",
    ]:
        if k in lim_calor and k not in cfg:
            cfg[k] = lim_calor[k]

    return cfg


def _resolve_p95_tmedia(df: pd.DataFrame, settings: dict) -> tuple[pd.Series, pd.Series]:
    """
    Resolve limiar P95 de temperatura média diária.

    Prioridade:
    1. Colunas históricas municipais explícitas.
    2. Valor configurado em limiares_calor.onda_calor.tmedia_p95_fallback.
    3. Proxy operacional pela distribuição da própria previsão municipal.
    """
    cfg = _get_onda_cfg(settings)

    p95_candidates = [
        "tmedia_p95",
        "p95_tmedia",
        "p95_temp_media",
        "tmedia_p95_local",
        "p95_local_tmedia",
        "limiar_p95_tmedia",
    ]

    for c in p95_candidates:
        if c in df.columns:
            p95 = pd.to_numeric(df[c], errors="coerce")
            origem = pd.Series(["p95_historico_coluna"] * len(df), index=df.index)
            return p95, origem

    fallback = cfg.get("tmedia_p95_fallback", None)

    if fallback is not None:
        p95 = pd.Series([float(fallback)] * len(df), index=df.index)
        origem = pd.Series(["p95_proxy_configurado"] * len(df), index=df.index)
        return p95, origem

    # Proxy operacional: quantil 70 da previsão municipal, com piso 27,5 °C.
    # Esse proxy detecta persistência relativa em tempo real, mas não deve ser
    # interpretado como climatologia 1981-2010.
    if "tmedia" not in df.columns:
        p95 = pd.Series([28.0] * len(df), index=df.index)
        origem = pd.Series(["p95_proxy_padrao_sem_tmedia"] * len(df), index=df.index)
        return p95, origem

    mcols = municipality_cols(df)

    if mcols:
        q = (
            df.groupby(mcols, group_keys=False)["tmedia"]
            .transform(lambda s: max(27.5, float(pd.to_numeric(s, errors="coerce").quantile(0.70))))
        )
    else:
        qval = max(27.5, float(pd.to_numeric(df["tmedia"], errors="coerce").quantile(0.70)))
        q = pd.Series([qval] * len(df), index=df.index)

    origem = pd.Series(["p95_proxy_previsao_q70"] * len(df), index=df.index)
    return q, origem


def _consecutive_run_lengths(flag: pd.Series) -> pd.Series:
    vals = []
    run = 0

    for v in flag.fillna(False).astype(bool).tolist():
        if v:
            run += 1
        else:
            run = 0
        vals.append(run)

    return pd.Series(vals, index=flag.index)


def _mark_heatwave_events(df: pd.DataFrame, min_days: int = 2) -> pd.DataFrame:
    out = df.copy()
    mcols = municipality_cols(out)

    if "dia_acima_p95_tmedia" not in out.columns:
        out["dia_acima_p95_tmedia"] = False

    if mcols:
        out["duracao_onda_calor_dias"] = (
            out.groupby(mcols, group_keys=False)["dia_acima_p95_tmedia"]
            .apply(_consecutive_run_lengths)
        )
    else:
        out["duracao_onda_calor_dias"] = _consecutive_run_lengths(out["dia_acima_p95_tmedia"])

    out["onda_calor_p95_2d"] = (out["duracao_onda_calor_dias"] >= min_days).astype(int)

    inicio = out["dia_acima_p95_tmedia"].astype(bool) & (out["duracao_onda_calor_dias"] == 1)

    if mcols:
        out["_inicio_evento_onda"] = inicio.astype(int)
        out["evento_onda_calor_id"] = (
            out.groupby(mcols, group_keys=False)["_inicio_evento_onda"]
            .cumsum()
            .where(out["dia_acima_p95_tmedia"].astype(bool), 0)
        )
        out = out.drop(columns=["_inicio_evento_onda"], errors="ignore")
    else:
        out["evento_onda_calor_id"] = inicio.astype(int).cumsum().where(out["dia_acima_p95_tmedia"].astype(bool), 0)

    return out


def compute_ehf_adapted(
    df: pd.DataFrame,
    date_col: str = "data",
    tmean_col: str = "tmedia",
    ref_col: str = "tmedia_ref",
) -> pd.DataFrame:
    """
    EHF* municipalizado:
    (Tmedia_3d - Tref_hist/proxy) + (Tmedia_3d - Tmedia_30d/proxy).
    """
    if _is_empty(df):
        return df

    out = ensure_municipality(df)
    out = _sort_municipal(out, date_col=date_col)

    if tmean_col not in out.columns:
        if {"tmax", "tmin"}.issubset(out.columns):
            out[tmean_col] = (
                pd.to_numeric(out["tmax"], errors="coerce")
                + pd.to_numeric(out["tmin"], errors="coerce")
            ) / 2
        else:
            out[tmean_col] = pd.to_numeric(out.get("temperatura", np.nan), errors="coerce")

    if ref_col not in out.columns:
        out[ref_col] = _rolling_by_municipio(out, tmean_col, 30, 3, func="median_expanding")

    out["tmedia_3d"] = _rolling_by_municipio(out, tmean_col, 3, 1)
    out["tmedia_30d"] = _rolling_by_municipio(out, tmean_col, 30, 3)

    out["ehf_adaptado"] = (
        (out["tmedia_3d"] - pd.to_numeric(out[ref_col], errors="coerce"))
        + (out["tmedia_3d"] - out["tmedia_30d"])
    )

    if date_col in out.columns:
        out[date_col] = pd.to_datetime(out[date_col], errors="coerce").dt.date.astype(str)

    return out


def add_heatwave_p95_indicators(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """
    Adiciona indicadores operacionais de onda de calor:
    - limiar_p95_tmedia;
    - dia_acima_p95_tmedia;
    - duracao_onda_calor_dias;
    - onda_calor_p95_2d;
    - intensidade_onda_calor;
    - p95_tmedia_origem.
    """
    if _is_empty(df):
        return df

    out = ensure_municipality(df)
    out = _sort_municipal(out, date_col="data")

    cfg = _get_onda_cfg(settings)
    min_days = int(cfg.get("min_dias", 2))

    if "tmedia" not in out.columns:
        if {"tmax", "tmin"}.issubset(out.columns):
            out["tmedia"] = (
                pd.to_numeric(out["tmax"], errors="coerce")
                + pd.to_numeric(out["tmin"], errors="coerce")
            ) / 2
        else:
            out["tmedia"] = pd.to_numeric(out.get("temperatura", np.nan), errors="coerce")

    limiar, origem = _resolve_p95_tmedia(out, settings)

    out["limiar_p95_tmedia"] = pd.to_numeric(limiar, errors="coerce")
    out["p95_tmedia_origem"] = origem
    out["excesso_tmedia_p95"] = np.maximum(0, out["tmedia"] - out["limiar_p95_tmedia"])
    out["dia_acima_p95_tmedia"] = out["excesso_tmedia_p95"] > 0

    out = _mark_heatwave_events(out, min_days=min_days)

    out["intensidade_onda_calor"] = np.where(
        out["onda_calor_p95_2d"] > 0,
        out["excesso_tmedia_p95"],
        0,
    )

    out["severidade_onda_calor"] = 0
    out.loc[out["onda_calor_p95_2d"].astype(int) > 0, "severidade_onda_calor"] = 1
    out.loc[out["intensidade_onda_calor"] >= 1.0, "severidade_onda_calor"] = 2
    out.loc[out["intensidade_onda_calor"] >= 2.0, "severidade_onda_calor"] = 3
    out.loc[out["intensidade_onda_calor"] >= 3.0, "severidade_onda_calor"] = 4

    if "data" in out.columns:
        out["data"] = pd.to_datetime(out["data"], errors="coerce").dt.date.astype(str)

    return out


def cumulative_heat_risk(
    df: pd.DataFrame,
    t_umbral: float = 39,
    factor_col: str | None = None,
    settings: dict | None = None,
) -> pd.DataFrame:
    """
    Risco cumulativo de calor em 3 dias.

    Componentes:
    - excesso de Tmax acima de t_umbral;
    - excesso de UTCI proxy acima de 32;
    - excesso de Heat Index acima de 32;
    - persistência de onda de calor P95 >= 2 dias;
    - EHF adaptado positivo.
    """
    if _is_empty(df):
        return df

    out = ensure_municipality(df)
    out = _sort_municipal(out, date_col="data")

    cfg = _get_onda_cfg(settings or {})
    utci_alerta = float(cfg.get("utci_alerta", 32))
    heat_index_alerta = float(cfg.get("heat_index_alerta", 32))

    out["tmax"] = pd.to_numeric(out.get("tmax"), errors="coerce")
    out["utci_proxy"] = pd.to_numeric(out.get("utci_proxy"), errors="coerce")
    out["heat_index"] = pd.to_numeric(out.get("heat_index"), errors="coerce")
    out["ehf_adaptado"] = pd.to_numeric(out.get("ehf_adaptado"), errors="coerce")

    if factor_col and factor_col in out.columns:
        fr = pd.to_numeric(out[factor_col], errors="coerce").fillna(1)
    else:
        fr = pd.Series(1.0, index=out.index)

    excesso_tmax = np.maximum(0, out["tmax"] - float(t_umbral))
    excesso_utci = np.maximum(0, out["utci_proxy"] - utci_alerta)
    excesso_hi = np.maximum(0, out["heat_index"] - heat_index_alerta) * 0.25
    excesso_p95 = pd.to_numeric(out.get("excesso_tmedia_p95", 0), errors="coerce").fillna(0)
    persistencia = pd.to_numeric(out.get("onda_calor_p95_2d", 0), errors="coerce").fillna(0) * 1.5
    ehf_pos = np.maximum(0, out["ehf_adaptado"].fillna(0)) * 0.5

    out["risco_calor_diario"] = (
        excesso_tmax.fillna(0)
        + excesso_utci.fillna(0)
        + excesso_hi.fillna(0)
        + excesso_p95.fillna(0)
        + persistencia.fillna(0)
        + ehf_pos.fillna(0)
    ) * fr

    mcols = municipality_cols(out)

    if mcols:
        out["risco_cumulativo_3d"] = (
            out.groupby(mcols, group_keys=False)["risco_calor_diario"]
            .apply(lambda s: s.rolling(3, min_periods=1).sum())
        )
    else:
        out["risco_cumulativo_3d"] = out["risco_calor_diario"].rolling(3, min_periods=1).sum()

    return out


def add_biometeo_indicators(met: pd.DataFrame, settings: dict) -> pd.DataFrame:
    if _is_empty(met):
        return met

    df = ensure_municipality(met)
    df = _sort_municipal(df, date_col="data")

    for c in ["tmax", "tmin", "umidade_media", "vento_max", "radiacao", "lat", "lon"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "tmedia" not in df.columns and {"tmax", "tmin"}.issubset(df.columns):
        df["tmedia"] = (df["tmax"] + df["tmin"]) / 2

    df["heat_index"] = df.apply(
        lambda r: heat_index_celsius(r.get("tmax", np.nan), r.get("umidade_media", np.nan)),
        axis=1,
    )

    df["utci_proxy"] = df.apply(
        lambda r: utci_proxy(
            r.get("tmax", np.nan),
            r.get("umidade_media", np.nan),
            r.get("vento_max", np.nan),
            r.get("radiacao", np.nan),
        ),
        axis=1,
    )

    df = add_heatwave_p95_indicators(df, settings)
    df = compute_ehf_adapted(df)

    t_umbral = (
        settings.get("limiares_calor", {})
        .get("risco_cumulativo", {})
        .get("t_umbral", 39)
    )

    df = cumulative_heat_risk(df, t_umbral=t_umbral, settings=settings)

    if "data" in df.columns:
        df["data"] = pd.to_datetime(df["data"], errors="coerce").dt.date.astype(str)

    return df
