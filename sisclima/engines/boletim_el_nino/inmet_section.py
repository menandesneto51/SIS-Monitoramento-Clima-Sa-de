# -*- coding: utf-8 -*-
"""Seção de alertas meteorológicos INMET para o boletim."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL
from sisclima.engines.boletim_el_nino.formatters import fmt_int, md_table


def _norm_severidade(nivel: str) -> str:
    n = str(nivel or "").lower().strip()
    mapping = {
        "verde": "Perigo potencial",
        "amarela": "Perigo potencial",
        "amarelo": "Perigo potencial",
        "laranja": "Perigo",
        "laranja_escuro": "Grande perigo",
        "vermelha": "Grande perigo",
        "vermelho": "Grande perigo",
    }
    return mapping.get(n, str(nivel or "—"))


def build_inmet_section(alertas: pd.DataFrame | None, *, consulta_em: datetime | None = None) -> dict[str, Any]:
    ts = consulta_em or datetime.now()
    consulta_pt = ts.strftime("%d/%m/%Y às %H:%M")

    if alertas is None:
        return {
            "disponivel": False,
            "status": "falha",
            "consulta_em": consulta_pt,
            "resumo_md": f"Consulta aos avisos do Instituto Nacional de Meteorologia (INMET) **indisponível nesta rodada**.\n\n"
            f"Consulta tentada em {consulta_pt}. Fonte: portal de alertas INMET.",
            "tabela_eventos": INDISPONIVEL,
        }

    df = alertas.copy()
    if df.empty:
        return {
            "disponivel": True,
            "status": "sem_alertas",
            "consulta_em": consulta_pt,
            "resumo_md": (
                f"Não foram identificados avisos meteorológicos vigentes do Instituto Nacional de Meteorologia (INMET) "
                f"para Mato Grosso na data/hora da consulta ({consulta_pt})."
            ),
            "tabela_eventos": "_Nenhum aviso vigente._",
            "resumo_severidade": [],
        }

    if "nivel_alerta" not in df.columns:
        df["nivel_alerta"] = "—"

    df["_sev"] = df["nivel_alerta"].map(_norm_severidade)
    resumo_rows: list[list[str]] = []
    for sev in ("Perigo potencial", "Perigo", "Grande perigo"):
        sub = df[df["_sev"] == sev]
        if sub.empty:
            continue
        mun = sub["municipio"].nunique() if "municipio" in sub.columns else len(sub)
        resumo_rows.append([sev, fmt_int(len(sub)), fmt_int(mun)])

    evento_rows: list[list[str]] = []
    for _, row in df.iterrows():
        vig = str(row.get("data_emissao", "—"))[:16]
        evento_rows.append(
            [
                str(row.get("evento") or "—"),
                _norm_severidade(str(row.get("nivel_alerta") or "")),
                vig,
                str(row.get("municipio") or "—"),
                str(row.get("descricao") or "—")[:120],
            ]
        )

    tab_sev = md_table(
        ["Severidade", "Alertas vigentes", "Municípios abrangidos"],
        resumo_rows,
        vazio="Sem recorte de severidade.",
    )
    tab_evt = md_table(
        ["Evento", "Severidade", "Vigência/emissão", "Municípios/área", "Orientação principal"],
        evento_rows,
    )

    return {
        "disponivel": True,
        "status": "ok",
        "consulta_em": consulta_pt,
        "resumo_md": tab_sev,
        "tabela_eventos": tab_evt,
        "n_alertas": len(df),
    }
