# -*- coding: utf-8 -*-
"""Agregação de agravos epidemiológicos (DW/operacional) para o boletim El Niño."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from sisclima.core.config import ROOT
from sisclima.core.db import read_table
from sisclima.core.logging_utils import get_logger
from sisclima.engines.epidemiology import (
    ARBOVIRUS_CANONICAL,
    _build_cid_text,
    _classify_cid_group,
    _strip_accents,
    _to_number,
)

log = get_logger(__name__)

CATALOG_PATH = ROOT / "config" / "monitoramento_agravos_el_nino.yaml"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or CATALOG_PATH
    try:
        if not target.exists():
            return {}
        data = yaml.safe_load(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("Catálogo de agravos El Niño indisponível: %s", exc)
        return {}


def _janela_dias(catalog: dict[str, Any]) -> int:
    janelas = catalog.get("janelas") or {}
    return int(janelas.get("operacional_dias", 7) or 7)


def _parse_dates(df: pd.DataFrame) -> pd.Series:
    for col in ("data", "data_notificacao", "data_obito", "data_sintomas", "data_atendimento"):
        if col in df.columns:
            dt = pd.to_datetime(df[col], errors="coerce")
            if dt.notna().any():
                return dt
    return pd.Series([pd.NaT] * len(df), index=df.index)


def _filter_window(df: pd.DataFrame, ref: date, dias: int) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    dt = _parse_dates(out)
    ini = pd.Timestamp(ref - timedelta(days=dias - 1))
    fim = pd.Timestamp(ref)
    if dt.notna().any():
        mask = dt.notna() & (dt >= ini) & (dt <= fim)
        filtered = out.loc[mask].copy()
        if not filtered.empty:
            return filtered
    if {"ano_internacao", "mes_internacao"}.issubset(out.columns):
        y = pd.to_numeric(out["ano_internacao"], errors="coerce")
        m = pd.to_numeric(out["mes_internacao"], errors="coerce")
        month_start = pd.to_datetime({"year": y, "month": m, "day": 1}, errors="coerce")
        month_end = month_start + pd.offsets.MonthEnd(0)
        mask = month_start.notna() & (month_end >= ini) & (month_start <= fim)
        return out.loc[mask].copy()
    return pd.DataFrame()


def _sum_col(df: pd.DataFrame, col: str, default: float = 1.0) -> int:
    if df.empty or col not in df.columns:
        return int(len(df)) if not df.empty else 0
    return int(round(float(_to_number(df[col], default).fillna(default).sum())))


def _text_blob(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=str)
    parts = []
    for c in cols:
        if c in df.columns:
            parts.append(df[c].astype(str))
    if not parts:
        # fallback: todas colunas object/string
        obj_cols = [c for c in df.columns if df[c].dtype == object]
        for c in obj_cols:
            parts.append(df[c].astype(str))
    if not parts:
        return pd.Series([""] * len(df), index=df.index)
    blob = parts[0]
    for p in parts[1:]:
        blob = blob + " " + p
    return _strip_accents(blob).str.lower()


def _match_patterns(text: pd.Series, patterns: list[str]) -> pd.Series:
    if text.empty:
        return pd.Series(dtype=bool)
    out = pd.Series([False] * len(text), index=text.index)
    for pat in patterns:
        try:
            out = out | text.str.contains(pat, regex=False, na=False)
        except Exception:
            continue
    return out


def _count_intoxicacao_fumaca(
    sinan: pd.DataFrame,
    intox_raw: pd.DataFrame | None,
    catalog: dict[str, Any],
    ref: date,
    dias: int,
) -> dict[str, Any]:
    bloco = (catalog.get("blocos") or {}).get("intoxicacao_fumaca") or {}
    patterns = list(bloco.get("filtros_texto") or [])
    agent_cols = list(bloco.get("colunas_agente") or [])

    base = intox_raw if intox_raw is not None and not intox_raw.empty else sinan
    if base.empty:
        return {
            "notificacoes_intox_total_7d": 0,
            "notificacoes_fumaca_7d": 0,
            "fonte": "indisponivel",
            "view_dw": bloco.get("view_dw"),
        }

    w = _filter_window(base, ref, dias)
    if "agravo" in w.columns:
        mask_intox = w["agravo"].astype(str).str.contains("INTOXIC|Intoxicacao|Intoxicação", case=False, na=False)
        if "fonte_sinan" in w.columns:
            mask_intox = mask_intox | w["fonte_sinan"].astype(str).str.contains("INTOXIC", case=False, na=False)
        w_intox = w.loc[mask_intox] if mask_intox.any() else w
    else:
        w_intox = w

    blob = _text_blob(w_intox, agent_cols)
    mask_fumaca = _match_patterns(blob, patterns)
    n_total = len(w_intox)
    n_fumaca = int(mask_fumaca.sum()) if len(w_intox) else 0

    return {
        "notificacoes_intox_total_7d": n_total,
        "notificacoes_fumaca_7d": n_fumaca,
        "fonte": "dw" if intox_raw is not None and not intox_raw.empty else "epi_sinan_agravos",
        "view_dw": bloco.get("view_dw"),
    }


def _count_sivep_alergico_dda(sivep_raw: pd.DataFrame, catalog: dict[str, Any], ref: date, dias: int) -> dict[str, Any]:
    bloco = (catalog.get("blocos") or {}).get("sivep_resp_alergico_dda") or {}
    regexes = [str(r) for r in (bloco.get("cids_regex") or [])]

    if sivep_raw is None or sivep_raw.empty:
        w = _filter_window(read_table("epi_sivep_srag"), ref, dias)
        return {
            "casos_srag_7d": _sum_col(w, "casos_srag"),
            "casos_alergico_dda_7d": None,
            "fonte": "epi_sivep_srag",
            "cid_disponivel": False,
            "nota": bloco.get("nota"),
        }

    w = _filter_window(sivep_raw, ref, dias)
    cid_text = _build_cid_text(w).str.upper()
    mask = pd.Series([False] * len(w), index=w.index)
    for rx in regexes:
        try:
            mask = mask | cid_text.str.contains(rx, regex=True, na=False)
        except re.error:
            continue

    n_srag = len(w)
    n_filtro = int(mask.sum()) if cid_text.str.strip().ne("").any() else None
    return {
        "casos_srag_7d": n_srag,
        "casos_alergico_dda_7d": n_filtro,
        "fonte": "sivep_local",
        "cid_disponivel": bool(cid_text.str.strip().ne("").any()),
        "nota": bloco.get("nota"),
    }


def _count_arboviroses(catalog: dict[str, Any], ref: date, dias: int) -> dict[str, Any]:
    bloco = (catalog.get("blocos") or {}).get("arboviroses") or {}
    alvo = {str(a) for a in (bloco.get("agravos") or ["Dengue", "Chikungunya"])}

    arbo_mun = read_table("epi_arboviroses_municipal")
    sinan = read_table("epi_sinan_agravos")

    if not arbo_mun.empty:
        w = arbo_mun.copy()
        if "casos_dengue_7d" in w.columns or "casos_chikungunya_7d" in w.columns:
            return {
                "dengue_7d": int(round(float(_to_number(w.get("casos_dengue_7d"), 0).sum()))),
                "chikungunya_7d": int(round(float(_to_number(w.get("casos_chikungunya_7d"), 0).sum()))),
                "municipios_com_casos_7d": int((_to_number(w.get("casos_arbovirus_7d"), 0) > 0).sum()),
                "fonte": "epi_arboviroses_municipal",
                "views_dw": bloco.get("views_dw"),
            }
        if "agravo" in w.columns and "casos_7d" in w.columns:
            w = w[w["agravo"].astype(str).isin(alvo)]
            return {
                "dengue_7d": int(round(float(_to_number(w.loc[w["agravo"] == "Dengue", "casos_7d"], 0).sum()))),
                "chikungunya_7d": int(round(float(_to_number(w.loc[w["agravo"] == "Chikungunya", "casos_7d"], 0).sum()))),
                "municipios_com_casos_7d": int((_to_number(w.get("casos_7d", 0), 0) > 0).sum()),
                "fonte": "epi_arboviroses_municipal",
                "views_dw": bloco.get("views_dw"),
            }

    if not sinan.empty and "agravo" in sinan.columns:
        w = _filter_window(sinan, ref, dias)
        if w.empty or "agravo" not in w.columns:
            return {
                "dengue_7d": None,
                "chikungunya_7d": None,
                "municipios_com_casos_7d": None,
                "fonte": "indisponivel",
                "views_dw": bloco.get("views_dw"),
            }
        w = w[w["agravo"].astype(str).isin(alvo | set(ARBOVIRUS_CANONICAL))]
        g = w.groupby("agravo", as_index=False)["notificacoes"].sum() if "notificacoes" in w.columns else pd.DataFrame()
        dengue = int(round(float(g.loc[g["agravo"] == "Dengue", "notificacoes"].sum()))) if not g.empty else 0
        chik = int(round(float(g.loc[g["agravo"] == "Chikungunya", "notificacoes"].sum()))) if not g.empty else 0
        return {
            "dengue_7d": dengue,
            "chikungunya_7d": chik,
            "municipios_com_casos_7d": int(w["cod_ibge"].nunique()) if "cod_ibge" in w.columns else 0,
            "fonte": "epi_sinan_agravos",
            "views_dw": bloco.get("views_dw"),
        }

    return {
        "dengue_7d": 0,
        "chikungunya_7d": 0,
        "municipios_com_casos_7d": 0,
        "fonte": "indisponivel",
        "views_dw": bloco.get("views_dw"),
    }


def _count_internacao_hospitalar(intern: pd.DataFrame, ref: date, dias: int) -> dict[str, Any]:
    base = {
        "fonte": "indisponivel",
        "view_dw": "VW_INTERNACAO",
        "fonte_label": "IndicaSUS/DW",
    }
    if intern is None or intern.empty:
        return {
            **base,
            "internacoes_total_7d": None,
            "grupos_7d": {},
            "status": "indisponivel",
        }

    data_max = None
    if "data" in intern.columns and intern["data"].notna().any():
        data_max = str(pd.to_datetime(intern["data"], errors="coerce").max())[:10]

    w = _filter_window(intern, ref, dias)
    if w.empty:
        # Fallback: último mês com dados no DW (competência), rotulado explicitamente
        mes_ref = None
        if "data" in intern.columns and intern["data"].notna().any():
            ultimo = pd.to_datetime(intern["data"], errors="coerce").max()
            if pd.notna(ultimo):
                mes_ref = ultimo.date().replace(day=1)
                ini = pd.Timestamp(mes_ref)
                fim = ini + pd.offsets.MonthEnd(0)
                dt = pd.to_datetime(intern["data"], errors="coerce")
                w = intern.loc[dt.notna() & (dt >= ini) & (dt <= fim)].copy()

        if w.empty:
            return {
                **base,
                "internacoes_total_7d": None,
                "grupos_7d": {},
                "status": "sem_dados_na_janela",
                "data_maxima_disponivel": data_max,
                "nota": "Sem internações na janela operacional; base DW pode estar defasada em relação à data de referência.",
            }

        col_n = "numero_internacoes" if "numero_internacoes" in w.columns else None
        w["_n"] = _to_number(w[col_n], 1) if col_n else 1
        grupos: dict[str, int] = {}
        if "grupo_internacao_clima" in w.columns:
            g = w.groupby("grupo_internacao_clima", as_index=False)["_n"].sum()
            grupos = {
                str(row["grupo_internacao_clima"]): int(round(float(row["_n"])))
                for _, row in g.iterrows()
            }
        return {
            "internacoes_total_7d": None,
            "internacoes_ultimo_mes_dw": int(round(float(w["_n"].sum()))),
            "grupos_ultimo_mes_dw": grupos,
            "grupos_7d": {},
            "mes_competencia_dw": str(mes_ref)[:7] if mes_ref else data_max,
            "status": "mes_competencia",
            "data_maxima_disponivel": data_max,
            "fonte": "dw",
            "view_dw": "VW_INTERNACAO",
            "fonte_label": "IndicaSUS/DW",
            "nota": "Janela de 7 dias sem registros; exibido último mês competência disponível no DW.",
        }

    col_n = "numero_internacoes" if "numero_internacoes" in w.columns else None
    if col_n:
        w["_n"] = _to_number(w[col_n], 1)
    else:
        w["_n"] = 1
    grupos = {}
    if "grupo_internacao_clima" in w.columns:
        g = w.groupby("grupo_internacao_clima", as_index=False)["_n"].sum()
        grupos = {
            str(row["grupo_internacao_clima"]): int(round(float(row["_n"])))
            for _, row in g.iterrows()
        }
    return {
        "internacoes_total_7d": int(round(float(w["_n"].sum()))),
        "grupos_7d": grupos,
        "data_maxima_disponivel": data_max,
        "status": "ok",
        "fonte": "dw",
        "view_dw": "VW_INTERNACAO",
        "fonte_label": "IndicaSUS/DW",
    }


def _count_sinan_extras(extras: pd.DataFrame, ref: date, dias: int) -> dict[str, Any]:
    if extras is None or extras.empty:
        return {"por_agravo_7d": {}, "fonte": "indisponivel"}
    w = _filter_window(extras, ref, dias)
    col_n = "numero_casos" if "numero_casos" in w.columns else None
    if col_n:
        w["_n"] = _to_number(w[col_n], 1)
    else:
        w["_n"] = 1
    if "agravo" not in w.columns:
        return {"por_agravo_7d": {}, "fonte": "dw"}
    g = w.groupby("agravo", as_index=False)["_n"].sum()
    return {
        "por_agravo_7d": {
            str(row["agravo"]): int(round(float(row["_n"])))
            for _, row in g.iterrows()
        },
        "fonte": "dw",
    }


def _count_desidratacao_calor(
    catalog: dict[str, Any],
    ref: date,
    dias: int,
    intern: pd.DataFrame | None = None,
    *,
    try_dw: bool = True,
) -> dict[str, Any]:
    bloco = (catalog.get("blocos") or {}).get("onda_calor_desidratacao") or {}
    cids = [str(c).upper() for c in (bloco.get("cids_desidratacao") or ["E86", "E87", "T67", "X30"])]

    sinan = read_table("epi_sinan_agravos")
    pressao = read_table("epi_pressao_assistencial")
    sim = read_table("epi_sim_obitos_calor")

    n_sinan = 0
    if not sinan.empty:
        w = _filter_window(sinan, ref, dias)
        if "agravo" in w.columns:
            agr = _strip_accents(w["agravo"].astype(str)).str.upper()
            mask = agr.str.contains("DESIDRAT|GOLPE DE CALOR|CALOR", regex=True, na=False)
            n_sinan = int(_to_number(w.loc[mask, "notificacoes"], 1).sum()) if mask.any() else 0

    n_atend = 0
    if not pressao.empty:
        w = _filter_window(pressao, ref, dias)
        n_atend = _sum_col(w, "atendimentos_calor")

    n_obitos_desid = 0
    sim_raw = pd.DataFrame()
    if try_dw:
        try:
            from sisclima.ingestion.dw_sources import load_dw_sim_obitos

            sim_raw = load_dw_sim_obitos()
        except Exception:
            sim_raw = pd.DataFrame()

    sim_base = sim_raw if sim_raw is not None and not sim_raw.empty else sim
    if sim_base is not None and not sim_base.empty:
        w = _filter_window(sim_base, ref, dias)
        cid = _build_cid_text(w).str.upper()
        mask = pd.Series([False] * len(w), index=w.index)
        for c in cids:
            mask = mask | cid.str.contains(rf"\b{re.escape(c)}", regex=True, na=False)
        if mask.any():
            col = "numero_obitos" if "numero_obitos" in w.columns else "obitos_total"
            n_obitos_desid = _sum_col(w.loc[mask], col)
        elif "obitos_calor_suspeitos" in w.columns:
            n_obitos_desid = _sum_col(w, "obitos_calor_suspeitos")

    n_intern_desid = 0
    if intern is not None and not intern.empty and "grupo_internacao_clima" in intern.columns:
        w = _filter_window(intern, ref, dias)
        if not w.empty:
            mask = w["grupo_internacao_clima"].astype(str).eq("desidratacao_calor")
            col = "numero_internacoes" if "numero_internacoes" in w.columns else None
            n_intern_desid = _sum_col(w.loc[mask], col) if col else int(mask.sum())

    return {
        "notificacoes_desidratacao_7d": n_sinan,
        "atendimentos_calor_7d": n_atend,
        "internacoes_desidratacao_7d": n_intern_desid,
        "obitos_desidratacao_calor_7d": n_obitos_desid,
        "fonte_sinan": "epi_sinan_agravos",
        "fonte_atendimentos": "epi_pressao_assistencial",
        "fonte_sim": "dw" if sim_raw is not None and not sim_raw.empty else "epi_sim_obitos_calor",
    }


def _count_obitos_cardiovascular(
    catalog: dict[str, Any], ref: date, dias: int, *, try_dw: bool = True
) -> dict[str, Any]:
    bloco = (catalog.get("blocos") or {}).get("mortalidade_cardiovascular") or {}
    sim = read_table("epi_sim_obitos_calor")
    sim_raw = pd.DataFrame()
    if try_dw:
        try:
            from sisclima.ingestion.dw_sources import load_dw_sim_obitos

            sim_raw = load_dw_sim_obitos()
        except Exception:
            pass

    base = sim_raw if not sim_raw.empty else sim
    if base.empty:
        return {
            "obitos_cardiovascular_7d": 0,
            "obitos_total_sim_7d": 0,
            "fonte": "indisponivel",
            "view_dw": bloco.get("view_dw"),
        }

    w = _filter_window(base, ref, dias)
    cid_group = _classify_cid_group(_build_cid_text(w))
    mask_cardio = cid_group.eq("cardiovascular")
    col = "numero_obitos" if "numero_obitos" in w.columns else "obitos_total"
    if not mask_cardio.any() and col in w.columns:
        # fallback: todos óbitos já filtrados pelo SQL do DW incluem I*
        mask_cardio = _build_cid_text(w).str.upper().str.contains(r"\bI", regex=True, na=False)

    return {
        "obitos_cardiovascular_7d": _sum_col(w.loc[mask_cardio], col) if mask_cardio.any() else 0,
        "obitos_total_sim_7d": _sum_col(w, col),
        "fonte": "dw" if not sim_raw.empty else "epi_sim_obitos_calor",
        "view_dw": bloco.get("view_dw"),
    }


def _fontes_pendentes(catalog: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for key, bloco in (catalog.get("blocos") or {}).items():
        if not isinstance(bloco, dict):
            continue
        if str(bloco.get("status", "")).startswith("pendente"):
            out.append(
                {
                    "id": key,
                    "titulo": str(bloco.get("titulo") or key),
                    "status": str(bloco.get("status")),
                    "view_dw_sugerida": str(bloco.get("view_dw_sugerida") or "—"),
                }
            )
    return out


def aggregate_agravos_el_nino(
    *,
    ref: date | None = None,
    catalog: dict[str, Any] | None = None,
    try_dw: bool = True,
) -> dict[str, Any]:
    """Consolida indicadores epidemiológicos para a seção 8 do boletim."""
    cat = catalog or load_catalog()
    hoje = ref or date.today()
    dias = _janela_dias(cat)

    sinan = read_table("epi_sinan_agravos")
    intox_raw = pd.DataFrame()
    intern_raw = pd.DataFrame()
    sinan_extras = pd.DataFrame()
    if try_dw:
        try:
            from sisclima.ingestion.dw_sources import (
                load_dw_indicasus_internacao,
                load_dw_sinan_agravos_extras_clima,
                load_dw_sinan_intoxicacao_detalhe,
            )

            intox_raw = load_dw_sinan_intoxicacao_detalhe()
            intern_raw = load_dw_indicasus_internacao()
            sinan_extras = load_dw_sinan_agravos_extras_clima()
        except Exception as exc:  # noqa: BLE001
            log.debug("Carga DW agravos El Niño: %s", exc)

    if intern_raw.empty:
        intern_raw = read_table("epi_indicasus_internacao_cid")

    sivep_raw = pd.DataFrame()
    try:
        from sisclima.ingestion.sivep_local import load_sivep_local

        sivep_raw = load_sivep_local()
    except Exception:
        pass

    return {
        "janela_dias": dias,
        "data_referencia": hoje.isoformat(),
        "intoxicacao_fumaca": _count_intoxicacao_fumaca(sinan, intox_raw, cat, hoje, dias),
        "sivep_alergico_dda": _count_sivep_alergico_dda(sivep_raw, cat, hoje, dias),
        "internacao_indicasus": _count_internacao_hospitalar(intern_raw, hoje, dias),
        "sinan_extras_clima": _count_sinan_extras(sinan_extras, hoje, dias),
        "arboviroses_dw": _count_arboviroses(cat, hoje, dias),
        "onda_calor_desidratacao": _count_desidratacao_calor(cat, hoje, dias, intern_raw, try_dw=try_dw),
        "mortalidade_cardiovascular": _count_obitos_cardiovascular(cat, hoje, dias, try_dw=try_dw),
        "fontes_pendentes": _fontes_pendentes(cat),
        "views_dw_catalogo": (cat.get("blocos") or {}).get("sinan_extras_clima", {}).get("views_dw"),
    }


def merge_agravos_monitorados(
    base: dict[str, Any],
    dw: dict[str, Any] | None,
) -> dict[str, Any]:
    """Mescla snapshot municipal (base) com blocos DW."""
    out = dict(base or {})
    if not dw:
        out["dw_epidemiologia"] = {"status": "indisponivel"}
        return out

    out["dw_epidemiologia"] = dw
    # Enriquece arboviroses com dados DW quando disponíveis
    arbo_dw = dw.get("arboviroses_dw") or {}
    if arbo_dw.get("fonte") != "indisponivel":
        blk = out.get("arboviroses_contexto_estiagem") or {}
        blk["dengue_7d_dw"] = arbo_dw.get("dengue_7d")
        blk["chikungunya_7d_dw"] = arbo_dw.get("chikungunya_7d")
        blk["fonte_dw"] = arbo_dw.get("fonte")
        out["arboviroses_contexto_estiagem"] = blk
    return out
