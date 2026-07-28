from __future__ import annotations

import numpy as np
import pandas as pd

from sisclima.utils.municipios import ensure_municipality, group_cols


# ============================================================
# SIS MT CLIMA-SAÚDE
# Arquivo: sisclima/engines/hospital.py
#
# Objetivo:
# - Tratar capacidade instalada CNES/IndicaSUS mesmo sem ocupação real.
# - Evitar que leitos_sus/leitos_existentes virem leitos_total = 0.
# - Agregar capacidade municipal por tipo de leito preservando ocupação
#   como indisponível quando leitos_ocupados/taxa_ocupacao não existirem.
# ============================================================


CAPACITY_UNIT_COLS = [
    "data",
    "cod_ibge",
    "municipio",
    "cnes",
    "unidade",
    "tipo_leito",
    "especialidade",
    "leitos_existentes",
    "leitos_sus",
    "leitos_ocupados",
    "leitos_livres",
    "taxa_ocupacao",
    "fonte",
    "leitos_total",
    "ocupacao_pct",
    "nivel_ocupacao",
]

CAPACITY_AGG_COLS = [
    "data",
    "cod_ibge",
    "municipio",
    "tipo_leito",
    "leitos_total",
    "leitos_ocupados",
    "leitos_livres",
    "ocupacao_pct",
]


def _empty_unit() -> pd.DataFrame:
    return pd.DataFrame(columns=CAPACITY_UNIT_COLS)


def _empty_agg() -> pd.DataFrame:
    return pd.DataFrame(columns=CAPACITY_AGG_COLS)


def _num(s, default=np.nan) -> pd.Series:
    try:
        return pd.to_numeric(s, errors="coerce")
    except Exception:
        return pd.Series(default)


def _first_numeric_col(df: pd.DataFrame, cols: list[str], default=np.nan) -> pd.Series:
    """
    Retorna a primeira coluna numérica existente com algum valor não nulo.
    Se nenhuma existir, retorna série default.
    """
    for c in cols:
        if c in df.columns:
            v = pd.to_numeric(df[c], errors="coerce")
            if v.notna().any():
                return v
    return pd.Series([default] * len(df), index=df.index)


def _normalize_date(out: pd.DataFrame) -> pd.DataFrame:
    if "data" not in out.columns:
        if "data_referencia" in out.columns:
            out["data"] = out["data_referencia"]
        else:
            out["data"] = pd.Timestamp.today().date().isoformat()

    original = out["data"].astype(str)
    parsed = pd.to_datetime(out["data"], errors="coerce")

    # Se todas as datas falharem, preserva texto original para não zerar agrupamento.
    # Exemplo observado: "2026-ev-01".
    if parsed.notna().any():
        out["data"] = parsed.dt.date.astype(str)
        out.loc[parsed.isna(), "data"] = original.loc[parsed.isna()]
    else:
        out["data"] = original

    return out


def _normalize_bed_type(out: pd.DataFrame) -> pd.DataFrame:
    if "tipo_leito" not in out.columns:
        out["tipo_leito"] = "GERAL"

    out["tipo_leito"] = (
        out["tipo_leito"]
        .fillna("GERAL")
        .astype(str)
        .str.strip()
        .replace({"": "GERAL", "None": "GERAL", "nan": "GERAL"})
    )

    if "unidade" not in out.columns:
        out["unidade"] = "NAO_INFORMADA"

    out["unidade"] = (
        out["unidade"]
        .fillna("NAO_INFORMADA")
        .astype(str)
        .str.strip()
        .replace({"": "NAO_INFORMADA", "None": "NAO_INFORMADA", "nan": "NAO_INFORMADA"})
    )

    if "especialidade" not in out.columns:
        out["especialidade"] = None

    if "fonte" not in out.columns:
        out["fonte"] = None

    if "cnes" not in out.columns:
        out["cnes"] = None

    return out


def _classify_occupancy(ocupacao_pct: pd.Series) -> pd.Series:
    occ = pd.to_numeric(ocupacao_pct, errors="coerce")
    nivel = pd.Series(["indisponivel"] * len(occ), index=occ.index, dtype="object")

    nivel.loc[occ.notna() & (occ <= 75)] = "verde"
    nivel.loc[occ.notna() & (occ > 75) & (occ <= 85)] = "amarela"
    nivel.loc[occ.notna() & (occ > 85) & (occ <= 95)] = "laranja"
    nivel.loc[occ.notna() & (occ > 95) & (occ <= 100)] = "vermelha"
    nivel.loc[occ.notna() & (occ > 100)] = "roxa"

    return nivel


def hospital_capacity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza capacidade hospitalar por unidade.

    Regras principais:
    - leitos_total prioriza leitos_total; se ausente, usa leitos_sus;
      se ausente, usa leitos_existentes.
    - leitos_ocupados não é forçado para 0 quando indisponível.
    - ocupacao_pct só é calculada quando existe ocupação real ou taxa_ocupacao.
    """
    if df is None or df.empty:
        return _empty_unit()

    out = ensure_municipality(df.copy())
    out = _normalize_date(out)
    out = _normalize_bed_type(out)

    for c in ["leitos_existentes", "leitos_sus", "leitos_total", "leitos_ocupados", "leitos_livres", "taxa_ocupacao"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    # Capacidade instalada: prioriza SUS, depois existentes.
    if "leitos_total" in out.columns and pd.to_numeric(out["leitos_total"], errors="coerce").notna().any():
        out["leitos_total"] = pd.to_numeric(out["leitos_total"], errors="coerce")
    else:
        out["leitos_total"] = _first_numeric_col(out, ["leitos_sus", "leitos_existentes"], default=np.nan)

    # Ocupação real: preservar NaN se fonte não trouxer ocupados.
    if "leitos_ocupados" in out.columns:
        out["leitos_ocupados"] = pd.to_numeric(out["leitos_ocupados"], errors="coerce")
    else:
        out["leitos_ocupados"] = np.nan

    # Livres só pode ser calculado se ocupação existir; senão preservar indisponível.
    if "leitos_livres" in out.columns:
        livres_original = pd.to_numeric(out["leitos_livres"], errors="coerce")
    else:
        livres_original = pd.Series([np.nan] * len(out), index=out.index)

    calculado = out["leitos_total"] - out["leitos_ocupados"]
    out["leitos_livres"] = np.where(livres_original.notna(), livres_original, calculado)
    out.loc[out["leitos_ocupados"].isna(), "leitos_livres"] = np.nan

    # Ocupação percentual: usa taxa_ocupacao se existir; senão calcula.
    if "taxa_ocupacao" in out.columns:
        taxa = pd.to_numeric(out["taxa_ocupacao"], errors="coerce")
    else:
        taxa = pd.Series([np.nan] * len(out), index=out.index)

    calculada = np.where(
        (out["leitos_total"] > 0) & out["leitos_ocupados"].notna(),
        out["leitos_ocupados"] / out["leitos_total"] * 100,
        np.nan,
    )

    out["ocupacao_pct"] = np.where(taxa.notna(), taxa, calculada)
    out["nivel_ocupacao"] = _classify_occupancy(out["ocupacao_pct"])

    for c in CAPACITY_UNIT_COLS:
        if c not in out.columns:
            out[c] = np.nan

    return out[CAPACITY_UNIT_COLS].copy()


def aggregate_capacity(cap: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega capacidade municipal por tipo de leito.

    Não descarta linhas por ausência de ocupação. Quando leitos_ocupados está
    totalmente ausente em um grupo, mantém ocupação como NaN.
    """
    if cap is None or cap.empty:
        return _empty_agg()

    out = cap.copy()
    out = ensure_municipality(out)
    out = _normalize_date(out)
    out = _normalize_bed_type(out)

    for c in ["leitos_total", "leitos_ocupados", "leitos_livres", "ocupacao_pct"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    if "leitos_total" not in out.columns or out["leitos_total"].isna().all():
        out["leitos_total"] = _first_numeric_col(out, ["leitos_sus", "leitos_existentes"], default=np.nan)

    if "leitos_ocupados" not in out.columns:
        out["leitos_ocupados"] = np.nan

    cols = group_cols(out, extras=["tipo_leito"])

    # Fallback defensivo se group_cols retornar estrutura inesperada.
    if not cols:
        cols = [c for c in ["data", "cod_ibge", "municipio", "tipo_leito"] if c in out.columns]

    if not cols:
        return _empty_agg()

    g = (
        out.groupby(cols, as_index=False, dropna=False)
        .agg(
            leitos_total=("leitos_total", lambda s: pd.to_numeric(s, errors="coerce").sum(min_count=1)),
            leitos_ocupados=("leitos_ocupados", lambda s: pd.to_numeric(s, errors="coerce").sum(min_count=1)),
        )
    )

    g["leitos_livres"] = g["leitos_total"] - g["leitos_ocupados"]
    g.loc[g["leitos_ocupados"].isna(), "leitos_livres"] = np.nan

    g["ocupacao_pct"] = np.where(
        (g["leitos_total"] > 0) & g["leitos_ocupados"].notna(),
        g["leitos_ocupados"] / g["leitos_total"] * 100,
        np.nan,
    )

    for c in CAPACITY_AGG_COLS:
        if c not in g.columns:
            g[c] = np.nan

    return g[CAPACITY_AGG_COLS].copy()
