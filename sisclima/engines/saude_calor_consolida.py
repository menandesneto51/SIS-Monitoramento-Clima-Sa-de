# -*- coding: utf-8 -*-
"""
Consolida monitoramento saúde-calor para o painel (tabelas v6).

Fontes operacionais (quando DW estiver offline):
  - epi_sinan_agravos
  - epi_sim_obitos_calor
  - lab_lacen_gal
  - epi_sivep_srag
  - resumo_municipal_atual (IBGE 7 dígitos + regional)

Quando o DW estiver online, tenta enriquecer SIM por grupo CID e GAL por exame.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table, write_df
from sisclima.core.logging_utils import get_logger
from sisclima.engines.epidemiology import (
    _build_cid_text,
    _classify_cid_group,
    _normalize_cod_ibge,
    _to_number,
    _to_text,
)

log = get_logger(__name__)

DICIONARIO_BASE = [
    {
        "fonte": "SINAN",
        "base_dw": "VW_SINAN_* / epi_sinan_agravos",
        "agravo_monitorado": "Arboviroses (Dengue, Zika, Chikungunya e correlatas)",
        "grupo_agravo_calor": "arbovirose",
    },
    {
        "fonte": "SINAN",
        "base_dw": "VW_SINAN_NOTIFICACAOINDIVIDUAL / intoxicação",
        "agravo_monitorado": "Intoxicação exógena e demais agravos sensíveis",
        "grupo_agravo_calor": "outros_sinan",
    },
    {
        "fonte": "SIM",
        "base_dw": "dbo.SIM / epi_sim_obitos_calor",
        "agravo_monitorado": "Óbitos com CID sensível ao calor (T67, X30, cardio, resp, renal)",
        "grupo_agravo_calor": "obitos_sensivel_calor",
    },
    {
        "fonte": "GAL/LACEN",
        "base_dw": "VW_GAL / lab_lacen_gal",
        "agravo_monitorado": "Taxa de positividade laboratorial (janela recente)",
        "grupo_agravo_calor": "laboratorio",
    },
    {
        "fonte": "SIVEP",
        "base_dw": "SIVEP-Gripe / epi_sivep_srag",
        "agravo_monitorado": "SRAG — casos, UTI e óbitos",
        "grupo_agravo_calor": "respiratorio_srag",
    },
]


def _muni_lookup() -> pd.DataFrame:
    resumo = read_table("resumo_municipal_atual")
    if resumo.empty or "cod_ibge" not in resumo.columns:
        return pd.DataFrame(columns=["cod_ibge", "cod6", "municipio", "regional_saude"])
    out = resumo[["cod_ibge"]].copy()
    out["cod_ibge"] = _normalize_cod_ibge(out["cod_ibge"])
    out["cod6"] = out["cod_ibge"].str[:6]
    if "municipio" in resumo.columns:
        out["municipio"] = resumo["municipio"].astype(str).values
    else:
        out["municipio"] = ""
    if "regional_saude" in resumo.columns:
        out["regional_saude"] = resumo["regional_saude"].astype(str).values
    else:
        out["regional_saude"] = ""
    return out.drop_duplicates("cod_ibge")


def _map_ibge(df: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    raw = _normalize_cod_ibge(out["cod_ibge"]) if "cod_ibge" in out.columns else pd.Series([""] * len(out), index=out.index)
    out["cod6"] = raw.str[:6]
    if lookup.empty:
        out["cod_ibge"] = raw
        if "regional_saude" not in out.columns:
            out["regional_saude"] = ""
        return out

    by6 = lookup.drop_duplicates("cod6")[["cod_ibge", "cod6", "municipio", "regional_saude"]].rename(
        columns={
            "cod_ibge": "cod_ibge_7",
            "municipio": "municipio_ref",
            "regional_saude": "regional_ref",
        }
    )
    merged = out.merge(by6, on="cod6", how="left")
    merged["cod_ibge"] = merged["cod_ibge_7"].fillna(raw)
    if "municipio" not in merged.columns:
        merged["municipio"] = merged["municipio_ref"]
    else:
        merged["municipio"] = merged["municipio"].astype(str).where(
            merged["municipio"].astype(str).str.strip().ne("") & merged["municipio"].notna(),
            merged["municipio_ref"],
        )
    merged["regional_saude"] = merged["regional_ref"]
    return merged.drop(columns=["cod6", "cod_ibge_7", "municipio_ref", "regional_ref"], errors="ignore")


def build_dicionario() -> pd.DataFrame:
    return pd.DataFrame(DICIONARIO_BASE)


def build_gal_tables(lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Positividade municipal + série estadual mensal."""
    gal = read_table("lab_lacen_gal")
    if gal.empty:
        return (
            pd.DataFrame(columns=["cod_ibge", "agravo_exame", "testes", "positivos", "positividade_pct"]),
            pd.DataFrame(columns=["mes", "agravo_exame", "testes", "positivos", "positividade_pct"]),
        )

    g = _map_ibge(gal, lookup)
    g["testes"] = _to_number(g.get("testes", 0), 0)
    g["positivos"] = _to_number(g.get("positivos", 0), 0)
    g["agravo_exame"] = "GAL/LACEN (todos os exames)"
    mun = (
        g.groupby(["cod_ibge", "agravo_exame"], as_index=False)
        .agg(testes=("testes", "sum"), positivos=("positivos", "sum"))
    )
    mun["positividade_pct"] = np.where(mun["testes"] > 0, mun["positivos"] / mun["testes"] * 100.0, 0.0)

    g["data"] = pd.to_datetime(g.get("data"), errors="coerce")
    g["mes"] = g["data"].dt.strftime("%Y-%m")
    serie = (
        g.dropna(subset=["mes"])
        .groupby(["mes", "agravo_exame"], as_index=False)
        .agg(testes=("testes", "sum"), positivos=("positivos", "sum"))
    )
    serie["positividade_pct"] = np.where(serie["testes"] > 0, serie["positivos"] / serie["testes"] * 100.0, 0.0)
    return mun, serie


def build_sim_tables(lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Óbitos SIM por grupo.

    Sem CID bruto no operacional, usa grupos derivados:
      - sensivel_calor_filtro_dw (todos os óbitos já filtrados pelo SQL do DW)
      - calor_suspeitos (subconjunto marcado no pipeline, se > 0)
    """
    sim = read_table("epi_sim_obitos_calor")
    empty_mun = pd.DataFrame(columns=["cod_ibge", "grupo_obito_calor", "obitos", "municipio", "regional_saude"])
    empty_serie = pd.DataFrame(columns=["mes", "grupo_obito_calor", "obitos"])
    if sim.empty:
        return empty_mun, empty_serie

    s = _map_ibge(sim, lookup)
    s["obitos_total"] = _to_number(s.get("obitos_total", 0), 0)
    s["obitos_calor_suspeitos"] = _to_number(s.get("obitos_calor_suspeitos", 0), 0)
    s["data"] = pd.to_datetime(s.get("data"), errors="coerce")

    base = s[["cod_ibge", "municipio", "regional_saude", "data"]].copy()
    total = base.copy()
    total["grupo_obito_calor"] = "sensivel_calor_filtro_dw"
    total["obitos"] = s["obitos_total"].values
    parts = [total]
    if float(s["obitos_calor_suspeitos"].sum()) > 0:
        calor = base.copy()
        calor["grupo_obito_calor"] = "calor_direto_ou_metabolico"
        calor["obitos"] = s["obitos_calor_suspeitos"].values
        parts.append(calor.loc[calor["obitos"] > 0])
    long = pd.concat(parts, ignore_index=True)
    if long.empty:
        return empty_mun, empty_serie

    mun = (
        long.groupby(["cod_ibge", "grupo_obito_calor"], as_index=False)
        .agg(
            obitos=("obitos", "sum"),
            municipio=("municipio", "first"),
            regional_saude=("regional_saude", "first"),
        )
    )
    long["mes"] = pd.to_datetime(long["data"], errors="coerce").dt.strftime("%Y-%m")
    serie = (
        long.dropna(subset=["mes"])
        .groupby(["mes", "grupo_obito_calor"], as_index=False)
        .agg(obitos=("obitos", "sum"))
    )
    return mun, serie


def build_sim_from_dw_raw(sim_raw: pd.DataFrame, lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    if sim_raw is None or sim_raw.empty:
        return None
    out = sim_raw.copy()
    if "cod_ibge" not in out.columns:
        for c in ("cod_ibge_residencia", "CodigoMunicipioResidencia"):
            if c in out.columns:
                out["cod_ibge"] = out[c]
                break
    if "municipio" not in out.columns:
        for c in ("municipio_residencia", "MunicipioResidencia"):
            if c in out.columns:
                out["municipio"] = out[c]
                break
    out = _map_ibge(out, lookup)
    cid_group = _classify_cid_group(_build_cid_text(out))
    n = _to_number(out["numero_obitos"], 1) if "numero_obitos" in out.columns else pd.Series(1, index=out.index)
    if "NumeroObitos" in out.columns:
        n = _to_number(out["NumeroObitos"], 1)
    tmp = pd.DataFrame(
        {
            "cod_ibge": out["cod_ibge"],
            "municipio": out.get("municipio", ""),
            "regional_saude": out.get("regional_saude", ""),
            "data": pd.to_datetime(out.get("data", out.get("data_obito")), errors="coerce"),
            "grupo_obito_calor": cid_group.values,
            "obitos": n.values,
        }
    )
    mun = tmp.groupby(["cod_ibge", "grupo_obito_calor"], as_index=False).agg(
        obitos=("obitos", "sum"),
        municipio=("municipio", "first"),
        regional_saude=("regional_saude", "first"),
    )
    tmp["mes"] = tmp["data"].dt.strftime("%Y-%m")
    serie = tmp.dropna(subset=["mes"]).groupby(["mes", "grupo_obito_calor"], as_index=False).agg(obitos=("obitos", "sum"))
    return mun, serie


def build_saude_calor(lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Consolida eventos municipais e série estadual por fonte/grupo."""
    parts: list[pd.DataFrame] = []

    sinan = read_table("epi_sinan_agravos")
    if not sinan.empty:
        s = _map_ibge(sinan, lookup)
        s["eventos"] = _to_number(s.get("notificacoes", 1), 1)
        s["fonte"] = "SINAN"
        s["grupo_agravo_calor"] = _to_text(s.get("grupo_agravo", "outros")).replace({"": "outros"})
        agravo_txt = s["agravo"].astype(str) if "agravo" in s.columns else pd.Series([""] * len(s), index=s.index)
        mask = s["grupo_agravo_calor"].eq("arbovirose") | agravo_txt.str.contains(
            "INTOXIC|DESIDR|GOLPE DE CALOR|INTERMA|RABICO|PECONH", case=False, na=False
        )
        s = s.loc[mask] if mask.any() else s
        for col in ("municipio", "regional_saude"):
            if col not in s.columns:
                s[col] = ""
        parts.append(s[["cod_ibge", "municipio", "regional_saude", "data", "fonte", "grupo_agravo_calor", "eventos"]])

    sim = read_table("epi_sim_obitos_calor")
    if not sim.empty:
        s = _map_ibge(sim, lookup)
        s["eventos"] = _to_number(s.get("obitos_total", 0), 0)
        s["fonte"] = "SIM"
        s["grupo_agravo_calor"] = "obitos_sensivel_calor"
        parts.append(s[["cod_ibge", "municipio", "regional_saude", "data", "fonte", "grupo_agravo_calor", "eventos"]])

    gal = read_table("lab_lacen_gal")
    if not gal.empty:
        s = _map_ibge(gal, lookup)
        s["eventos"] = _to_number(s.get("positivos", 0), 0)
        s["fonte"] = "GAL/LACEN"
        s["grupo_agravo_calor"] = "positivos_laboratorio"
        parts.append(s[["cod_ibge", "municipio", "regional_saude", "data", "fonte", "grupo_agravo_calor", "eventos"]])

    sivep = read_table("epi_sivep_srag")
    if not sivep.empty:
        s = _map_ibge(sivep, lookup)
        s["eventos"] = _to_number(s.get("casos_srag", 0), 0)
        s["fonte"] = "SIVEP"
        s["grupo_agravo_calor"] = "srag"
        parts.append(s[["cod_ibge", "municipio", "regional_saude", "data", "fonte", "grupo_agravo_calor", "eventos"]])

    if not parts:
        return (
            pd.DataFrame(columns=["cod_ibge", "municipio", "regional_saude", "fonte", "grupo_agravo_calor", "eventos"]),
            pd.DataFrame(columns=["mes", "fonte", "grupo_agravo_calor", "eventos"]),
        )

    all_ev = pd.concat(parts, ignore_index=True, sort=False)
    all_ev["eventos"] = _to_number(all_ev["eventos"], 0)
    all_ev["data"] = pd.to_datetime(all_ev["data"], errors="coerce")

    mun = (
        all_ev.groupby(["cod_ibge", "fonte", "grupo_agravo_calor"], as_index=False)
        .agg(
            eventos=("eventos", "sum"),
            municipio=("municipio", "first"),
            regional_saude=("regional_saude", "first"),
        )
        .sort_values("eventos", ascending=False)
    )

    all_ev["mes"] = all_ev["data"].dt.strftime("%Y-%m")
    serie = (
        all_ev.dropna(subset=["mes"])
        .groupby(["mes", "fonte", "grupo_agravo_calor"], as_index=False)
        .agg(eventos=("eventos", "sum"))
        .sort_values(["mes", "fonte"])
    )
    return mun, serie


def build_geocalor_placeholder(lookup: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Gera status/RR placeholder no Postgres quando não há série diária completa."""
    from datetime import datetime

    motivo = (
        "Sem série diária geocalor_model_input_diario (isHW × desfechos). "
        "Status gravado para a aba permanecer funcional. "
        "Quando o DW estiver online, rode calcular_geocalor_cardioresp_v11_12.py com input diário."
    )
    rows = []
    base = lookup if not lookup.empty else pd.DataFrame([{"cod_ibge": "5103403", "municipio": "Cuiabá", "regional_saude": "Cuiabá"}])
    outcomes = {
        "internacoes_cardio": "Internações cardiovasculares",
        "internacoes_resp": "Internações respiratórias",
        "obitos_cardio": "Óbitos cardiovasculares",
        "obitos_resp": "Óbitos respiratórios",
    }
    # Limita a amostra estadual para não explodir memória: top 20 + Cuiabá
    sample = base.head(20).copy()
    if "5103403" not in set(sample["cod_ibge"].astype(str)):
        cui = base[base["cod_ibge"].astype(str) == "5103403"]
        if not cui.empty:
            sample = pd.concat([sample, cui], ignore_index=True)
    for _, r in sample.iterrows():
        for outcome, label in outcomes.items():
            for lag in range(8):
                rows.append(
                    {
                        "cod_ibge": r.get("cod_ibge"),
                        "municipio": r.get("municipio", ""),
                        "regional_saude": r.get("regional_saude", ""),
                        "desfecho": outcome,
                        "desfecho_label": label,
                        "lag": lag,
                        "rr": np.nan,
                        "rr_ic95_inf": np.nan,
                        "rr_ic95_sup": np.nan,
                        "metodo": "placeholder_sem_serie_diaria",
                        "status_modelagem": "insuficiente_dados_diarios",
                        "detalhe": motivo,
                    }
                )
    rr = pd.DataFrame(rows)
    status = pd.DataFrame(
        [
            {
                "data_execucao": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "fonte": "operacional_postgres",
                "status": "insuficiente_dados_diarios",
                "detalhe": motivo,
            }
        ]
    )
    return rr, status


def run_saude_calor_consolidation(*, include_geocalor: bool = True, try_dw: bool = False) -> dict[str, Any]:
    lookup = _muni_lookup()
    summary: dict[str, Any] = {"ok": True}

    dic = build_dicionario()
    write_df(dic, "dicionario_monitoramento_saude_v6", if_exists="replace")
    summary["dicionario"] = len(dic)

    sim_mun, sim_serie = build_sim_tables(lookup)
    summary["sim_fonte"] = "operacional"
    if try_dw:
        try:
            from sisclima.ingestion.dw_sources import load_dw_sim_obitos

            raw = load_dw_sim_obitos()
            rich = build_sim_from_dw_raw(raw, lookup)
            if rich is not None:
                sim_mun, sim_serie = rich
                summary["sim_fonte"] = "dw"
        except Exception as exc:  # noqa: BLE001
            summary["sim_fonte"] = f"operacional ({exc.__class__.__name__})"

    write_df(sim_mun, "sim_obitos_calor_municipal_v6", if_exists="replace")
    write_df(sim_serie, "sim_obitos_calor_estado_serie_v6", if_exists="replace")
    summary["sim_mun"] = len(sim_mun)
    summary["sim_serie"] = len(sim_serie)

    gal_mun, gal_serie = build_gal_tables(lookup)
    write_df(gal_mun, "gal_positividade_municipal_v6", if_exists="replace")
    write_df(gal_serie, "gal_positividade_estado_serie_v6", if_exists="replace")
    summary["gal_mun"] = len(gal_mun)
    summary["gal_serie"] = len(gal_serie)

    saude_mun, saude_serie = build_saude_calor(lookup)
    write_df(saude_mun, "saude_calor_municipio", if_exists="replace")
    write_df(saude_serie, "saude_calor_serie_estado", if_exists="replace")
    summary["saude_mun"] = len(saude_mun)
    summary["saude_serie"] = len(saude_serie)

    if include_geocalor:
        rr, status = build_geocalor_placeholder(lookup)
        write_df(rr, "geocalor_cardioresp_rr_municipal_v11_12", if_exists="replace")
        write_df(status, "geocalor_status_modelagem_v11_12", if_exists="replace")
        summary["geocalor_rr"] = len(rr)
        summary["geocalor_status"] = status.iloc[0]["status"] if not status.empty else "—"

    log.info("Monitoramento saúde-calor consolidado: %s", summary)
    return summary
