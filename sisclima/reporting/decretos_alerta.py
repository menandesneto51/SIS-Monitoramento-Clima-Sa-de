# -*- coding: utf-8 -*-
"""Atos oficiais (decretos/portarias) para alerta SES e boletim da Sala.

Fonte prioritária: lista curada VALIDADOS (humano).
Complemento: top da tabela iomat_decretos_emergencia (score alto, fonte IOMAT).
Disclaimer: sinal normativo ≠ ativação automática do plano / alerta.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DISCLAIMER = (
    "Sinal normativo (atos oficiais) ≠ ativação automática do Plano El Niño "
    "nem substituição do alerta operacional climática–saúde."
)

# Lista curada (docs/apresentacoes/Decretos_Emergencia_ARARAS_VALIDADOS_2026-08-21.md)
ATOS_VALIDADOS: list[dict[str, str]] = [
    {
        "escopo": "estadual",
        "titulo": "Decreto n.º 2.015/2026 (28/04/2026)",
        "ementa": "Emergência ambiental, período proibitivo de queimadas e Sala de Situação ambiental.",
        "link": "https://www.iomat.mt.gov.br/portal/edicoes/download/19059",
        "municipio": "",
    },
    {
        "escopo": "estadual",
        "titulo": "Portaria n.º 0590/2026/GBSES",
        "ementa": "Institui a Sala de Situação em Saúde (El Niño 2026–2027 e extremos climáticos).",
        "link": "https://www.iomat.mt.gov.br/portal/edicoes/download/19279",
        "municipio": "",
    },
    {
        "escopo": "estadual",
        "titulo": "IN conjunta SEMA/CBM-MT n.º 03/2026",
        "ementa": "Aceiros no Pantanal durante a emergência ambiental do Decreto 2.015/2026.",
        "link": "https://www.iomat.mt.gov.br/portal/edicoes/download/19279",
        "municipio": "",
    },
    {
        "escopo": "municipal",
        "titulo": "Várzea Grande — Decreto n.º 76/2026",
        "ementa": "SE por estiagem (COBRADE 1.4.1.1.0), 180 dias.",
        "link": "https://amm.diariomunicipal.org/publicacao/1881872/",
        "municipio": "Várzea Grande",
    },
    {
        "escopo": "municipal",
        "titulo": "Jangada — Decreto n.º 010/2026",
        "ementa": "SE por incêndios florestais/queimadas (COBRADE 1.4.1.3.2).",
        "link": "https://amm.diariomunicipal.org/publicacao/1894424/",
        "municipio": "Jangada",
    },
]

_VALIDADOS_MD = ROOT / "docs" / "apresentacoes" / "Decretos_Emergencia_ARARAS_VALIDADOS_2026-08-21.md"


def _atos_iomat_db(limit: int = 5) -> list[dict[str, str]]:
    if not table_exists("iomat_decretos_emergencia"):
        return []
    try:
        df = read_table("iomat_decretos_emergencia")
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao ler iomat_decretos_emergencia: %s", exc)
        return []
    if df is None or df.empty:
        return []
    work = df.copy()
    if "fonte" in work.columns:
        work = work[work["fonte"].astype(str).str.upper().eq("IOMAT")]
    if work.empty:
        return []
    if "score_relevancia" in work.columns:
        work["score_relevancia"] = pd.to_numeric(work["score_relevancia"], errors="coerce")
        work = work.sort_values("score_relevancia", ascending=False)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in work.head(max(limit * 3, 15)).iterrows():
        titulo = str(row.get("titulo") or "").strip()
        if not titulo or titulo.casefold() in seen:
            continue
        seen.add(titulo.casefold())
        mun = str(row.get("municipios_mencionados") or "").strip()
        if mun.lower() in {"nan", "none"}:
            mun = ""
        out.append(
            {
                "escopo": "iomat",
                "titulo": titulo[:120],
                "ementa": str(row.get("tags") or row.get("trecho") or "")[:160],
                "link": str(row.get("url") or "").strip(),
                "municipio": mun,
            }
        )
        if len(out) >= limit:
            break
    return out


def listar_atos_para_alerta(*, max_validados: int = 5, max_iomat: int = 3) -> dict[str, Any]:
    """Retorna atos curados + amostra IOMAT recente."""
    validados = ATOS_VALIDADOS[:max_validados]
    iomat = _atos_iomat_db(limit=max_iomat)
    # Evitar duplicar portaria/decreto já curados por título parcial
    keys = {a["titulo"][:40].casefold() for a in validados}
    iomat_filt = [a for a in iomat if a["titulo"][:40].casefold() not in keys]
    return {
        "disponivel": True,
        "disclaimer": DISCLAIMER,
        "validados": validados,
        "iomat_recente": iomat_filt[:max_iomat],
        "fonte_curada": str(_VALIDADOS_MD.name) if _VALIDADOS_MD.exists() else "ATOS_VALIDADOS",
        "n_iomat_tabela": (
            int(len(read_table("iomat_decretos_emergencia")))
            if table_exists("iomat_decretos_emergencia")
            else 0
        ),
    }


def bloco_decretos_texto_alerta(*, max_linhas: int = 8) -> str:
    """Bloco curto para digest SES / Telegram."""
    pack = listar_atos_para_alerta(max_validados=5, max_iomat=2)
    lines = [
        "📜 Atos oficiais (decretos / portarias) — eixo clima–saúde",
        f"📌 {pack['disclaimer']}",
    ]
    n = 0
    for a in pack["validados"]:
        mun = f" · {a['municipio']}" if a.get("municipio") else ""
        lines.append(f"• {a['titulo']}{mun}: {a['ementa']}")
        n += 1
        if n >= max_linhas:
            break
    if n < max_linhas:
        for a in pack["iomat_recente"]:
            lines.append(f"• (IOMAT) {a['titulo']}: {a['ementa']}")
            n += 1
            if n >= max_linhas:
                break
    if pack.get("n_iomat_tabela"):
        lines.append(f"Base IOMAT na rodada: {pack['n_iomat_tabela']} registros (triagem humana prevalece).")
    return "\n".join(lines)


def bloco_decretos_markdown_boletim() -> str:
    """Subseção Markdown para o boletim El Niño / Sala."""
    pack = listar_atos_para_alerta(max_validados=6, max_iomat=3)
    lines = [
        "### Atos oficiais correlatos (decretos e portarias)",
        "",
        f"*{pack['disclaimer']}*",
        "",
        "**Validados para inserção no boletim**",
        "",
    ]
    for a in pack["validados"]:
        link = f" — {a['link']}" if a.get("link") else ""
        mun = f" ({a['municipio']})" if a.get("municipio") else ""
        lines.append(f"- **{a['titulo']}**{mun}: {a['ementa']}{link}")
    if pack["iomat_recente"]:
        lines += ["", "**Amostra IOMAT recente (requer triagem)**", ""]
        for a in pack["iomat_recente"]:
            link = f" — {a['link']}" if a.get("link") else ""
            lines.append(f"- {a['titulo']}: {a['ementa']}{link}")
    lines += [
        "",
        f"Fonte curada: `{pack['fonte_curada']}` · tabela IOMAT: {pack.get('n_iomat_tabela') or 0} itens.",
        "",
    ]
    return "\n".join(lines)
