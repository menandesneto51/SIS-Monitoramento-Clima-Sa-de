# -*- coding: utf-8 -*-
"""Governança de frescor e completude das fontes do SIS.

Produz `fonte_frescor_estado`: idade do dado (dias), status e cobertura
municipal por fonte — para a sala de situação CIEVS priorizar coleta.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

# Limiares operacionais (dias desde a última observação / referência)
THRESHOLDS = {
    "ok_max": 2,
    "atrasado_max": 7,
}

# Catálogo de fontes monitoradas no painel
FONTES: list[dict[str, Any]] = [
    {
        "fonte_id": "openmeteo_met",
        "fonte_nome": "Open-Meteo / biometeo",
        "tabela": "met_biometeo",
        "date_cols": ["data"],
        "ibge": True,
        "tipo": "operacional",
        "ok_max": 2,
        "atrasado_max": 5,
    },
    {
        "fonte_id": "resumo_municipal",
        "fonte_nome": "Resumo municipal (rodada)",
        "tabela": "resumo_municipal_atual",
        "date_cols": ["data_referencia", "data"],
        "ibge": True,
        "tipo": "operacional",
        "ok_max": 2,
        "atrasado_max": 5,
    },
    {
        "fonte_id": "queimadas_inpe",
        "fonte_nome": "Queimadas INPE",
        "tabela": "queimadas_focos_municipal",
        "date_cols": ["data_referencia", "data_processamento"],
        "ibge": True,
        "tipo": "operacional",
        "ok_max": 2,
        "atrasado_max": 4,
    },
    {
        "fonte_id": "qualidade_ar",
        "fonte_nome": "Qualidade do ar (CAMS)",
        "tabela": "qualidade_ar_municipal",
        "date_cols": ["data"],
        "ibge": True,
        "tipo": "operacional",
        "ok_max": 2,
        "atrasado_max": 5,
    },
    {
        "fonte_id": "sisreg",
        "fonte_nome": "SISREG (filas)",
        "tabela": "ops_sisreg_municipio",
        "date_cols": ["data_referencia", "atualizado_em"],
        "ibge": True,
        "tipo": "assistencial",
        "ok_max": 3,
        "atrasado_max": 10,
    },
    {
        "fonte_id": "sivep",
        "fonte_nome": "SIVEP-SRAG",
        "tabela": "epi_sivep_srag",
        "date_cols": ["data"],
        "ibge": True,
        "tipo": "epidemiologico",
        "ok_max": 7,
        "atrasado_max": 21,
    },
    {
        "fonte_id": "arboviroses",
        "fonte_nome": "Arboviroses (SINAN)",
        "tabela": "epi_arboviroses_municipal",
        "date_cols": ["data"],
        "ibge": True,
        "tipo": "epidemiologico",
        "ok_max": 7,
        "atrasado_max": 21,
    },
    {
        "fonte_id": "wash_censo",
        "fonte_nome": "WASH (Censo IBGE 2022)",
        "tabela": "wash_municipal",
        "date_cols": ["atualizado_em"],
        "ibge": True,
        "tipo": "estrutural",
        "ok_max": 365,
        "atrasado_max": 800,
        "estrutural": True,
    },
    {
        "fonte_id": "vulnerabilidade_ibge",
        "fonte_nome": "Vulnerabilidade demográfica (IBGE)",
        "tabela": "geo_vulnerabilidade_municipal",
        "date_cols": ["atualizado_em"],
        "ibge": True,
        "tipo": "estrutural",
        "ok_max": 365,
        "atrasado_max": 800,
        "estrutural": True,
    },
    {
        "fonte_id": "predicao_7d",
        "fonte_nome": "Predição calor 7d",
        "tabela": "predicao_calor_7d_municipal_v6",
        "date_cols": ["data_processamento", "data_referencia"],
        "ibge": True,
        "tipo": "derivado",
        "ok_max": 2,
        "atrasado_max": 5,
        "fallback_resumo": True,
    },
    {
        "fonte_id": "predicao_14d",
        "fonte_nome": "Predição calor 14d",
        "tabela": "predicao_calor_14d_municipal",
        "date_cols": ["data_processamento", "data_referencia"],
        "ibge": True,
        "tipo": "derivado",
        "ok_max": 2,
        "atrasado_max": 5,
        "fallback_resumo": True,
    },
]


def _parse_dates(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=False)


def _status(idade: float | None, ok_max: int, atrasado_max: int, *, estrutural: bool = False, vazia: bool = False) -> str:
    if vazia:
        return "sem_dado"
    if idade is None or (isinstance(idade, float) and np.isnan(idade)):
        return "sem_dado"
    if estrutural:
        return "estrutural"
    if idade <= ok_max:
        return "ok"
    if idade <= atrasado_max:
        return "atrasado"
    return "critico"


def _inspect_table(cfg: dict[str, Any], ref_now: pd.Timestamp) -> dict[str, Any]:
    table = cfg["tabela"]
    df = read_table(table)
    out: dict[str, Any] = {
        "fonte_id": cfg["fonte_id"],
        "fonte_nome": cfg["fonte_nome"],
        "tabela": table,
        "tipo": cfg.get("tipo", "—"),
        "registros": int(len(df)) if df is not None else 0,
        "municipios_com_dado": 0,
        "cobertura_mun_pct": 0.0,
        "data_mais_recente": None,
        "idade_dias": None,
        "status_frescor": "sem_dado",
        "observacao": "",
    }
    if df is None or df.empty:
        out["observacao"] = "Tabela vazia ou ausente nesta rodada"
        out["status_frescor"] = "sem_dado"
        return out

    date_cols = [c for c in cfg.get("date_cols") or [] if c in df.columns]
    last = None
    if date_cols:
        candidates = []
        for c in date_cols:
            s = _parse_dates(df[c]).dropna()
            if not s.empty:
                candidates.append(s.max())
        if candidates:
            last = max(candidates)
    if last is None and cfg.get("fallback_resumo"):
        # derivados sem timestamp: herdam frescor do resumo
        resumo = read_table("resumo_municipal_atual")
        for c in ("data_referencia", "data"):
            if resumo is not None and not resumo.empty and c in resumo.columns:
                s = _parse_dates(resumo[c]).dropna()
                if not s.empty:
                    last = s.max()
                    out["observacao"] = "Timestamp herdado do resumo municipal"
                    break

    if last is not None:
        # normaliza timezone-naive
        if getattr(last, "tzinfo", None) is not None:
            last = last.tz_localize(None)
        idade = float((ref_now.normalize() - pd.Timestamp(last).normalize()).days)
        out["data_mais_recente"] = pd.Timestamp(last).strftime("%Y-%m-%d")
        out["idade_dias"] = max(0.0, idade)
    else:
        out["observacao"] = out["observacao"] or "Sem coluna de data reconhecida"
        out["idade_dias"] = None

    if cfg.get("ibge") and "cod_ibge" in df.columns:
        munis = df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].dropna().nunique()
        out["municipios_com_dado"] = int(munis)
        # 142 munis MT como referência operacional
        out["cobertura_mun_pct"] = round(min(100.0, munis / 142.0 * 100.0), 1)

    out["status_frescor"] = _status(
        out["idade_dias"],
        int(cfg.get("ok_max", THRESHOLDS["ok_max"])),
        int(cfg.get("atrasado_max", THRESHOLDS["atrasado_max"])),
        estrutural=bool(cfg.get("estrutural")),
        vazia=False if out["registros"] else True,
    )
    if out["status_frescor"] == "estrutural" and not out["observacao"]:
        out["observacao"] = "Fonte estrutural (Censo) — não exige atualização diária"
    return out


def build_fonte_freshness(ref_now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Monta painel estadual de frescor por fonte."""
    now = ref_now or pd.Timestamp.now()
    if getattr(now, "tzinfo", None) is not None:
        now = now.tz_localize(None)
    rows = [_inspect_table(cfg, now) for cfg in FONTES]
    out = pd.DataFrame(rows)
    out["avaliado_em"] = now.strftime("%Y-%m-%d %H:%M:%S")
    # Ordena: críticos primeiro, depois atrasados, sem dado, ok, estrutural
    order = {"critico": 0, "atrasado": 1, "sem_dado": 2, "ok": 3, "estrutural": 4}
    out["_ord"] = out["status_frescor"].map(order).fillna(9)
    out = out.sort_values(["_ord", "idade_dias"], ascending=[True, False]).drop(columns=["_ord"])
    return out.reset_index(drop=True)


def summarize_freshness(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty:
        return {"n_fontes": 0, "n_ok": 0, "n_atrasado": 0, "n_critico": 0, "n_sem_dado": 0, "n_estrutural": 0}
    vc = df["status_frescor"].value_counts().to_dict()
    return {
        "n_fontes": int(len(df)),
        "n_ok": int(vc.get("ok", 0)),
        "n_atrasado": int(vc.get("atrasado", 0)),
        "n_critico": int(vc.get("critico", 0)),
        "n_sem_dado": int(vc.get("sem_dado", 0)),
        "n_estrutural": int(vc.get("estrutural", 0)),
        "pior_fonte": str(df.iloc[0]["fonte_nome"]) if len(df) else "—",
        "pior_status": str(df.iloc[0]["status_frescor"]) if len(df) else "—",
    }
