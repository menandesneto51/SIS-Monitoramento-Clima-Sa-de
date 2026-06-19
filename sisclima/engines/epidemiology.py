from __future__ import annotations

import re
import numpy as np
import pandas as pd


# ============================================================
# SIS MT CLIMA-SAÚDE
# Arquivo: sisclima/engines/epidemiology.py
#
# Versão consolidada para substituir o arquivo existente.
#
# Ajustes principais:
# - Remove dependência de group_cols/ensure_municipality em bases instáveis.
# - Evita erro "Grouper for 'municipio' not 1-dimensional".
# - Padroniza chaves: data, cod_ibge, municipio.
# - Filtra Mato Grosso quando houver cod_ibge iniciando por 51.
# - Classifica grupos de causas sensíveis ao calor:
#   calor direto, desidratação/metabólico, cardiovascular,
#   respiratório, renal/geniturinário e outros.
# ============================================================


def _is_empty(df: pd.DataFrame | None) -> bool:
    return df is None or df.empty


def _dedup_columns(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame()
    return df.loc[:, ~df.columns.duplicated()].copy()


def _as_series(
    df: pd.DataFrame,
    candidates: list[str] | tuple[str, ...],
    default: str | int | float = "",
) -> pd.Series:
    for c in candidates:
        if c in df.columns:
            v = df[c]
            if isinstance(v, pd.DataFrame):
                v = v.iloc[:, 0]
            return v
    return pd.Series([default] * len(df), index=df.index)


def _to_date_str(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce").dt.date.astype(str)
    return out.replace({"NaT": "", "nan": "", "None": "", "<NA>": ""})


def _to_number(s: pd.Series, default: float = 0) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(default)


def _to_text(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .replace({"nan": "", "None": "", "NaT": "", "<NA>": ""})
        .str.strip()
    )


def _normalize_cod_ibge(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
        .replace({"nan": "", "None": "", "NaT": "", "<NA>": ""})
    )


def _strip_accents(s: pd.Series) -> pd.Series:
    try:
        return (
            s.astype(str)
            .str.normalize("NFKD")
            .str.encode("ascii", errors="ignore")
            .str.decode("utf-8")
        )
    except Exception:
        return s.astype(str)


def _filter_mt(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return df

    cod = _normalize_cod_ibge(df["cod_ibge"])
    mask_mt = cod.str.startswith("51")

    if mask_mt.any():
        return df.loc[mask_mt].copy()

    return df


def _standard_keys(
    df: pd.DataFrame,
    date_candidates: list[str] | tuple[str, ...],
    cod_candidates: list[str] | tuple[str, ...],
    municipio_candidates: list[str] | tuple[str, ...],
) -> pd.DataFrame:
    out = _dedup_columns(df)

    data = _as_series(out, date_candidates, "")
    cod = _as_series(out, cod_candidates, "")
    mun = _as_series(out, municipio_candidates, "")

    clean = pd.DataFrame(
        {
            "data": _to_date_str(data),
            "cod_ibge": _normalize_cod_ibge(cod),
            "municipio": _to_text(mun),
        },
        index=out.index,
    )

    return _filter_mt(clean)


def _group_keys(df: pd.DataFrame, extras: list[str] | tuple[str, ...] | None = None) -> list[str]:
    extras = extras or []
    keys: list[str] = []

    for c in ["data", "cod_ibge", "municipio"] + list(extras):
        if c in df.columns and c not in keys:
            keys.append(c)

    return keys


def _municipality_key(df: pd.DataFrame) -> list[str]:
    if "cod_ibge" in df.columns:
        return ["cod_ibge"]
    if "municipio" in df.columns:
        return ["municipio"]
    return []


# ------------------------------------------------------------
# CID e grupos sensíveis ao calor
# ------------------------------------------------------------

def _classify_cid_group(text: pd.Series) -> pd.Series:
    txt = _strip_accents(text).str.upper()
    grupo = pd.Series(["outros"] * len(txt), index=txt.index)

    grupo.loc[txt.str.contains(r"\b(?:T67|X30)\b", regex=True, na=False)] = "calor_direto"
    grupo.loc[txt.str.contains(r"\b(?:E86|E87)\b", regex=True, na=False)] = "desidratacao_metabolico"
    grupo.loc[txt.str.contains(r"\bI[0-9]{2}\b", regex=True, na=False)] = "cardiovascular"
    grupo.loc[txt.str.contains(r"\bJ[0-9]{2}\b", regex=True, na=False)] = "respiratorio"
    grupo.loc[txt.str.contains(r"\bN[0-9]{2}\b", regex=True, na=False)] = "renal_geniturinario"
    grupo.loc[txt.str.contains(r"\b(?:E10|E11|E12|E13|E14)\b", regex=True, na=False)] = "endocrino_metabolico"

    return grupo


def _build_cid_text(out: pd.DataFrame) -> pd.Series:
    cid_text = pd.Series([""] * len(out), index=out.index)

    for c in [
        "cid",
        "causa_basica",
        "cid10_causa_basica",
        "cid10_3c",
        "capitulo_cid10",
        "linha_a",
        "linha_b",
        "linha_c",
        "linha_d",
        "diagnostico",
        "diagnostico_principal",
        "codigo_diagnostico_principal",
        "DiagnosticoPrincipal",
        "CodigoDiagnosticoPrincipal",
        "CausaBasica",
        "CausaCid103C",
        "CausaCid10Capitulo",
        "LinhaA",
        "LinhaB",
        "LinhaC",
        "LinhaD",
    ]:
        if c in out.columns:
            cid_text = cid_text + " " + out[c].astype(str)

    return cid_text


# ------------------------------------------------------------
# Séries temporais
# ------------------------------------------------------------

def zscore_series(s: pd.Series, window: int = 28) -> pd.Series:
    s = _to_number(s, 0)
    min_periods = max(7, window // 4)
    mean = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std().replace(0, np.nan)
    return (s - mean) / sd


def ewma(s: pd.Series, alpha: float = 0.3) -> pd.Series:
    return _to_number(s, 0).ewm(alpha=alpha, adjust=False).mean()


def simple_cusum(s: pd.Series, target: float | None = None, k: float = 0.5) -> pd.Series:
    x = _to_number(s, 0)
    target = float(target if target is not None else x.median())
    vals = []
    c = 0.0
    for v in x:
        c = max(0.0, c + (float(v) - target - k))
        vals.append(c)
    return pd.Series(vals, index=s.index)


def _apply_by_municipio(g: pd.DataFrame, value_col: str, prefix: str = "pressao") -> pd.DataFrame:
    if g is None or g.empty:
        return g

    g = g.copy()
    sort_cols = [c for c in ["cod_ibge", "municipio", "data"] if c in g.columns]
    if sort_cols:
        g = g.sort_values(sort_cols)

    mcols = _municipality_key(g)

    if prefix == "pressao":
        zcol = "zscore_pressao"
        ewcol = "ewma_pressao"
        ccol = "cusum_pressao"
    else:
        zcol = f"zscore_{prefix}"
        ewcol = f"ewma_{prefix}"
        ccol = f"cusum_{prefix}"

    if mcols:
        g[zcol] = g.groupby(mcols, group_keys=False)[value_col].transform(lambda s: zscore_series(s).fillna(0))
        g[ewcol] = g.groupby(mcols, group_keys=False)[value_col].transform(lambda s: ewma(s))
        g[ccol] = g.groupby(mcols, group_keys=False)[value_col].transform(lambda s: simple_cusum(s))
    else:
        g[zcol] = zscore_series(g[value_col]).fillna(0)
        g[ewcol] = ewma(g[value_col])
        g[ccol] = simple_cusum(g[value_col])

    return g


# ------------------------------------------------------------
# Pressão assistencial / morbidade hospitalar
# ------------------------------------------------------------

def pressure_assistencial(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "data",
        "cod_ibge",
        "municipio",
        "atendimentos_total",
        "atendimentos_calor",
        "pressao_calor_pct",
        "zscore_pressao",
        "ewma_pressao",
        "cusum_pressao",
    ]

    if _is_empty(df):
        return pd.DataFrame(columns=columns)

    out = _dedup_columns(df)
    keys = _standard_keys(
        out,
        date_candidates=["data", "data_atendimento", "data_internacao", "data_notificacao", "DataAtendimento", "DataInternacao"],
        cod_candidates=["cod_ibge", "cod_ibge_residencia", "cod_ibge_ocorrencia", "CodigoMunicipioResidencia", "CodigoMunicipioOcorrencia"],
        municipio_candidates=["municipio", "municipio_residencia", "municipio_ocorrencia", "MunicipioResidencia", "MunicipioOcorrencia"],
    )
    out = out.loc[keys.index].copy()

    total = _as_series(out, ["atendimentos_total", "total", "numero_atendimentos", "numero_internacoes", "NumeroInternacoes", "internacoes"], 1)
    total = _to_number(total, 1)

    if "atendimentos_calor" in out.columns:
        calor = _to_number(out["atendimentos_calor"], 0)
    else:
        cid_group = _classify_cid_group(_build_cid_text(out))
        flag_calor = cid_group.isin([
            "calor_direto",
            "desidratacao_metabolico",
            "cardiovascular",
            "respiratorio",
            "renal_geniturinario",
            "endocrino_metabolico",
        ]).astype(int)
        calor = total * flag_calor

    clean = keys.copy()
    clean["atendimentos_total"] = total.loc[clean.index].values
    clean["atendimentos_calor"] = _to_number(calor.loc[clean.index], 0).values

    group = _group_keys(clean)
    if not group:
        return pd.DataFrame(columns=columns)

    g = clean.groupby(group, as_index=False).agg(
        atendimentos_total=("atendimentos_total", "sum"),
        atendimentos_calor=("atendimentos_calor", "sum"),
    )
    g["pressao_calor_pct"] = np.where(g["atendimentos_total"] > 0, g["atendimentos_calor"] / g["atendimentos_total"] * 100, 0)
    g = _apply_by_municipio(g, "pressao_calor_pct", prefix="pressao")

    for c in columns:
        if c not in g.columns:
            g[c] = 0 if c not in ["data", "cod_ibge", "municipio"] else ""
    return g[columns]


# ------------------------------------------------------------
# SIVEP / SRAG
# ------------------------------------------------------------

def sivep_summary(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["data", "cod_ibge", "municipio", "casos_srag", "uti", "obitos", "letalidade_pct", "zscore_srag"]
    if _is_empty(df):
        return pd.DataFrame(columns=columns)

    out = _dedup_columns(df)
    keys = _standard_keys(
        out,
        date_candidates=["data", "data_notificacao", "dt_notific", "data_internacao", "DT_NOTIFIC", "DT_INTERNA"],
        cod_candidates=["cod_ibge", "cod_ibge_residencia", "cod_mun_res", "CO_MUN_RES", "CodigoMunicipioResidencia"],
        municipio_candidates=["municipio", "municipio_residencia", "mun_res", "MunicipioResidencia"],
    )
    out = out.loc[keys.index].copy()

    uti = _to_number(_as_series(out, ["uti", "foi_internado_uti", "FoiInternadoEmUTI", "UTI"], 0), 0)
    if "obito" in out.columns:
        obito = _to_number(out["obito"], 0)
    elif "evolucao" in out.columns:
        obito = _strip_accents(out["evolucao"]).str.lower().str.contains("obito", na=False).astype(int)
    elif "EvolucaoClinica" in out.columns:
        obito = _strip_accents(out["EvolucaoClinica"]).str.lower().str.contains("obito", na=False).astype(int)
    else:
        obito = pd.Series([0] * len(out), index=out.index)

    clean = keys.copy()
    clean["uti"] = uti.loc[clean.index].values
    clean["obito"] = _to_number(obito.loc[clean.index], 0).values

    g = clean.groupby(_group_keys(clean), as_index=False).agg(casos_srag=("data", "size"), uti=("uti", "sum"), obitos=("obito", "sum"))
    g["letalidade_pct"] = np.where(g["casos_srag"] > 0, g["obitos"] / g["casos_srag"] * 100, 0)

    mcols = _municipality_key(g)
    if mcols:
        g = g.sort_values(mcols + ["data"])
        g["zscore_srag"] = g.groupby(mcols, group_keys=False)["casos_srag"].transform(lambda s: zscore_series(s).fillna(0))
    else:
        g["zscore_srag"] = zscore_series(g["casos_srag"]).fillna(0)

    for c in columns:
        if c not in g.columns:
            g[c] = 0 if c not in ["data", "cod_ibge", "municipio"] else ""
    return g[columns]


# ------------------------------------------------------------
# GAL / LACEN
# ------------------------------------------------------------

def lacen_summary(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["data", "cod_ibge", "municipio", "testes", "positivos", "positividade_pct", "zscore_positividade"]
    if _is_empty(df):
        return pd.DataFrame(columns=columns)

    out = _dedup_columns(df)
    keys = _standard_keys(
        out,
        date_candidates=["data", "data_resultado", "data_liberacao", "data_coleta", "data_referencia", "Data_Liberacao_dt", "Data_Coleta_dt"],
        cod_candidates=["cod_ibge", "cod_ibge_residencia", "IBGE_Municipio_Residencia_Paciente", "cod_ibge_solicitante"],
        municipio_candidates=["municipio", "municipio_residencia", "Municipio_Residencia_Paciente", "municipio_solicitante"],
    )
    out = out.loc[keys.index].copy()

    resultado_cols = [
        c for c in out.columns
        if c.lower().startswith("resultado") or c.lower().startswith("campo_resultado") or c.lower() in ["observacao_resultado", "status_exame", "resultado"]
    ]

    if "positivo" in out.columns:
        positivo = _to_number(out["positivo"], 0)
    elif resultado_cols:
        texto = pd.Series([""] * len(out), index=out.index)
        for c in resultado_cols:
            texto = texto + " " + out[c].astype(str)
        texto = _strip_accents(texto).str.lower()
        negativo = texto.str.contains(r"nao detect|nao reag|negativo|indetect|not detect", regex=True, na=False)
        positivo_flag = texto.str.contains(r"positivo|reagente|detectado|detectavel|detected", regex=True, na=False)
        positivo = (positivo_flag & ~negativo).astype(int)
    else:
        positivo = pd.Series([0] * len(out), index=out.index)

    clean = keys.copy()
    clean["positivo"] = _to_number(positivo.loc[clean.index], 0).values

    g = clean.groupby(_group_keys(clean), as_index=False).agg(testes=("data", "size"), positivos=("positivo", "sum"))
    g["positividade_pct"] = np.where(g["testes"] > 0, g["positivos"] / g["testes"] * 100, 0)

    mcols = _municipality_key(g)
    if mcols:
        g = g.sort_values(mcols + ["data"])
        g["zscore_positividade"] = g.groupby(mcols, group_keys=False)["positividade_pct"].transform(lambda s: zscore_series(s).fillna(0))
    else:
        g["zscore_positividade"] = zscore_series(g["positividade_pct"]).fillna(0)

    for c in columns:
        if c not in g.columns:
            g[c] = 0 if c not in ["data", "cod_ibge", "municipio"] else ""
    return g[columns]


# ------------------------------------------------------------
# SINAN
# ------------------------------------------------------------

def sinan_summary(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["data", "cod_ibge", "municipio", "agravo", "notificacoes"]
    if _is_empty(df):
        return pd.DataFrame(columns=columns)

    out = _dedup_columns(df)
    keys = _standard_keys(
        out,
        date_candidates=["data", "data_notificacao", "data_primeiros_sintomas", "DataNotificacao", "DataPrimeirosSintomas"],
        cod_candidates=["cod_ibge", "cod_ibge_residencia", "cod_ibge_notificacao", "CodigoMunicipioResidencia", "CodigoMunicipioNotificacao"],
        municipio_candidates=["municipio", "municipio_residencia", "municipio_notificacao", "MunicipioResidencia", "MunicipioNotificacao"],
    )
    out = out.loc[keys.index].copy()

    agravo = _as_series(out, ["agravo", "Agravo", "fonte_sinan"], "SINAN")
    agravo = _to_text(agravo).replace({"": "SINAN", "nan": "SINAN", "None": "SINAN", "NaT": "SINAN"})

    clean = keys.copy()
    clean["agravo"] = agravo.loc[clean.index].values

    g = clean.groupby(_group_keys(clean, extras=["agravo"]), as_index=False).size().rename(columns={"size": "notificacoes"})
    for c in columns:
        if c not in g.columns:
            g[c] = 0 if c == "notificacoes" else ""
    return g[columns]


# ------------------------------------------------------------
# SIM — óbitos associados ao calor
# ------------------------------------------------------------

def sim_heat_deaths(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["data", "cod_ibge", "municipio", "obitos_total", "obitos_calor_suspeitos"]
    if _is_empty(df):
        return pd.DataFrame(columns=columns)

    out = _dedup_columns(df)
    keys = _standard_keys(
        out,
        date_candidates=["data", "data_obito", "DataObito"],
        cod_candidates=["cod_ibge", "cod_ibge_residencia", "cod_ibge_ocorrencia", "CodigoMunicipioResidencia", "CodigoMunicipioOcorrencia"],
        municipio_candidates=["municipio", "municipio_residencia", "municipio_ocorrencia", "MunicipioResidencia", "MunicipioOcorrencia"],
    )
    out = out.loc[keys.index].copy()

    numero_obitos = _to_number(_as_series(out, ["numero_obitos", "NumeroObitos"], 1), 1)
    cid_group = _classify_cid_group(_build_cid_text(out))
    heat_flag = cid_group.isin([
        "calor_direto",
        "desidratacao_metabolico",
        "cardiovascular",
        "respiratorio",
        "renal_geniturinario",
        "endocrino_metabolico",
    ]).astype(int)

    clean = keys.copy()
    clean["numero_obitos"] = numero_obitos.loc[clean.index].values
    clean["obito_calor_suspeito"] = clean["numero_obitos"] * heat_flag.loc[clean.index].values

    g = clean.groupby(_group_keys(clean), as_index=False).agg(
        obitos_total=("numero_obitos", "sum"),
        obitos_calor_suspeitos=("obito_calor_suspeito", "sum"),
    )

    for c in columns:
        if c not in g.columns:
            g[c] = 0 if c not in ["data", "cod_ibge", "municipio"] else ""
    return g[columns]

