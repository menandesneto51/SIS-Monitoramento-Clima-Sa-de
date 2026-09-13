# -*- coding: utf-8 -*-
"""Agregados CNES para mapas de equipamentos e profissionais (sem PII)."""
from __future__ import annotations

import re

import pandas as pd

from sisclima.core.db import read_table, table_exists, write_df
from sisclima.core.logging_utils import get_logger
from sisclima.utils.io import normalize_cols

log = get_logger(__name__)

TABLE_EQ_TIPO = "epi_cnes_equipamentos_por_tipo"
TABLE_PROF_OCUP = "epi_cnes_profissionais_por_ocupacao"

_PII_FORBIDDEN = re.compile(
    r"(^nome$|_nome$|nome_|cpf|cns|rg\b|registro_conselho|conselho_numero|profissional_nome|pessoa_nome)",
    re.I,
)


def grupo_ocupacao_cbo(codigo: object) -> str:
    """Agrupa CBO em famílias legíveis (sem expor indivíduo)."""
    raw = re.sub(r"\D", "", str(codigo or ""))
    if not raw or raw in {"0", "SEM_CBO"}:
        return "Sem CBO / não informado"
    # Famílias CBO 2002 (prefixos)
    if raw.startswith("2251") or raw.startswith("2252") or raw.startswith("2253"):
        return "Médicos"
    if raw.startswith("2235") or raw.startswith("2231"):
        return "Enfermagem (nível superior)"
    if raw.startswith("3222") or raw.startswith("3221"):
        return "Técnicos / auxiliares de enfermagem"
    if raw.startswith("5151"):
        return "ACS / agentes comunitários"
    if raw.startswith("2232"):
        return "Odontologia"
    if raw.startswith("2234") or raw.startswith("2255"):
        return "Farmácia"
    if raw.startswith("2236") or raw.startswith("2237"):
        return "Fisioterapia / fono / TO"
    if raw.startswith("2515") or raw.startswith("2516"):
        return "Psicologia / serviço social"
    if raw.startswith("1312"):
        return "Gestão em saúde"
    if raw.startswith("3224") or raw.startswith("3241"):
        return "Técnicos laboratoriais / diagnóstico"
    if raw.startswith("516"):
        return "Apoio / serviços gerais saúde"
    return "Outras ocupações de saúde"


def assert_sem_pii(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    bad = [c for c in df.columns if _PII_FORBIDDEN.search(str(c))]
    if bad:
        raise ValueError(f"Colunas com risco de PII bloqueadas: {bad}")


def _ibge(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d{6,7})", expand=False)


def prepare_equipamentos_por_tipo(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "cod_ibge",
                "municipio",
                "equipamento_grupo",
                "equipamento_tipo",
                "equipamentos_existentes",
                "equipamentos_em_uso",
                "estabelecimentos",
            ]
        )
    out = normalize_cols(df.copy())
    assert_sem_pii(out)
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = _ibge(out["cod_ibge"])
    for c in ("equipamentos_existentes", "equipamentos_em_uso", "estabelecimentos"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    if "equipamento_grupo" not in out.columns:
        out["equipamento_grupo"] = "Sem grupo"
    if "equipamento_tipo" not in out.columns:
        out["equipamento_tipo"] = "Sem tipo"
    blob = (
        out["equipamento_grupo"].astype(str) + " " + out["equipamento_tipo"].astype(str)
    ).str.upper()
    out["flag_nebulizacao"] = blob.str.contains("NEBUL", na=False)
    return out


def prepare_profissionais_por_ocupacao(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "cod_ibge",
                "municipio",
                "ocupacao_codigo",
                "grupo_ocupacao",
                "profissionais_qtd",
                "estabelecimentos_com_ocupacao",
                "horas_ocupacao",
            ]
        )
    out = normalize_cols(df.copy())
    assert_sem_pii(out)
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = _ibge(out["cod_ibge"])
    if "ocupacao_codigo" not in out.columns:
        out["ocupacao_codigo"] = "SEM_CBO"
    out["grupo_ocupacao"] = out["ocupacao_codigo"].map(grupo_ocupacao_cbo)
    for c in ("profissionais_qtd", "estabelecimentos_com_ocupacao", "horas_ocupacao"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    return out


def pivot_equipamentos_municipio(df: pd.DataFrame) -> pd.DataFrame:
    """Totais municipais (inclui nebulização) para coroplético."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return pd.DataFrame(columns=["cod_ibge", "equipamentos_total", "equipamentos_nebulizacao"])
    work = prepare_equipamentos_por_tipo(df)
    tot = work.groupby("cod_ibge", as_index=False).agg(
        equipamentos_total=("equipamentos_existentes", "sum"),
        municipio=("municipio", "first") if "municipio" in work.columns else ("cod_ibge", "first"),
    )
    neb = (
        work.loc[work["flag_nebulizacao"]]
        .groupby("cod_ibge", as_index=False)["equipamentos_existentes"]
        .sum()
        .rename(columns={"equipamentos_existentes": "equipamentos_nebulizacao"})
    )
    out = tot.merge(neb, on="cod_ibge", how="left")
    out["equipamentos_nebulizacao"] = pd.to_numeric(out["equipamentos_nebulizacao"], errors="coerce").fillna(0)
    return out


def pivot_profissionais_municipio(df: pd.DataFrame, *, grupo: str | None = None) -> pd.DataFrame:
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return pd.DataFrame(columns=["cod_ibge", "profissionais_qtd", "grupo_ocupacao"])
    work = prepare_profissionais_por_ocupacao(df)
    if grupo and grupo != "Todas":
        work = work[work["grupo_ocupacao"] == grupo]
    g = work.groupby("cod_ibge", as_index=False).agg(
        profissionais_qtd=("profissionais_qtd", "sum"),
        municipio=("municipio", "first") if "municipio" in work.columns else ("cod_ibge", "first"),
    )
    if grupo and grupo != "Todas":
        g["grupo_ocupacao"] = grupo
    return g


def load_or_fetch_equipamentos_tipo(*, try_dw: bool = False, persist: bool = False) -> pd.DataFrame:
    if table_exists(TABLE_EQ_TIPO):
        cached = read_table(TABLE_EQ_TIPO)
        if cached is not None and not cached.empty:
            return prepare_equipamentos_por_tipo(cached)
    if not try_dw:
        return prepare_equipamentos_por_tipo(None)
    try:
        from sisclima.ingestion.dw_sources import load_dw_cnes_equipamentos_por_tipo

        raw = load_dw_cnes_equipamentos_por_tipo()
        out = prepare_equipamentos_por_tipo(raw)
        if persist and not out.empty:
            write_df(out, TABLE_EQ_TIPO)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("CNES equipamentos por tipo indisponível: %s", exc)
        return prepare_equipamentos_por_tipo(None)


def load_or_fetch_profissionais_ocupacao(*, try_dw: bool = False, persist: bool = False) -> pd.DataFrame:
    if table_exists(TABLE_PROF_OCUP):
        cached = read_table(TABLE_PROF_OCUP)
        if cached is not None and not cached.empty:
            return prepare_profissionais_por_ocupacao(cached)
    if not try_dw:
        return prepare_profissionais_por_ocupacao(None)
    try:
        from sisclima.ingestion.dw_sources import load_dw_cnes_profissionais_por_ocupacao

        raw = load_dw_cnes_profissionais_por_ocupacao()
        out = prepare_profissionais_por_ocupacao(raw)
        if persist and not out.empty:
            write_df(out, TABLE_PROF_OCUP)
        return out
    except Exception as exc:  # noqa: BLE001
        log.warning("CNES profissionais por ocupação indisponível: %s", exc)
        return prepare_profissionais_por_ocupacao(None)
