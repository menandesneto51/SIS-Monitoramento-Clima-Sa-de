# -*- coding: utf-8 -*-
"""Citações e referências ABNT NBR 6023 para o boletim."""
from __future__ import annotations

from datetime import date
from typing import Any

import yaml

from sisclima.core.config import ROOT

_CFG: dict[str, Any] | None = None
_REF_PATH = ROOT / "config" / "boletim_el_nino_referencias.yaml"

_MESES_ABNT = (
    "jan.", "fev.", "mar.", "abr.", "maio", "jun.",
    "jul.", "ago.", "set.", "out.", "nov.", "dez.",
)


def _acesso_em(d: date | None = None) -> str:
    ref = d or date.today()
    return f"{ref.day} {_MESES_ABNT[ref.month - 1]} {ref.year}"


def load_referencias_config() -> dict[str, Any]:
    global _CFG
    if _CFG is not None:
        return _CFG
    if not _REF_PATH.exists():
        _CFG = {"referencias": []}
        return _CFG
    with _REF_PATH.open("r", encoding="utf-8") as fh:
        _CFG = yaml.safe_load(fh) or {"referencias": []}
    return _CFG


def _index_refs(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in cfg.get("referencias") or []:
        if isinstance(item, dict) and item.get("id"):
            out[str(item["id"])] = item
    return out


def cite(ref_id: str, *, acesso_em: date | None = None) -> str:
    """Retorna citação curta ABNT para uso inline, ex.: (INMET, 2026)."""
    idx = _index_refs(load_referencias_config())
    item = idx.get(ref_id)
    if not item:
        return f"({ref_id})"
    curta = str(item.get("citacao_curta") or ref_id)
    return f"({curta})"


def format_referencias_bibliograficas(*, ref_ids: list[str] | None = None, acesso_em: date | None = None) -> list[str]:
    """Lista de entradas bibliográficas completas (seção 18), ordem alfabética por autor institucional."""
    cfg = load_referencias_config()
    idx = _index_refs(cfg)
    acesso = _acesso_em(acesso_em)
    ids = ref_ids or list(idx.keys())
    linhas: list[str] = []
    for rid in ids:
        item = idx.get(rid)
        if not item:
            continue
        texto = str(item.get("abnt") or "").replace("{acesso_em}", acesso).strip()
        if texto:
            linhas.append(texto)
    # Ordem alfabética por autor/instituição (início da entrada ABNT)
    linhas.sort(key=lambda s: s.casefold())
    return linhas


def refs_usadas_boletim() -> list[str]:
    """Ordem canônica das referências citadas no boletim."""
    return [
        "abnt6023",
        "abnt14724",
        "abnt10719",
        "portaria_sala_590",
        "painel_el_nino_02",
        "inmet_alertas",
        "cemaden_alertas",
        "inpe_queimadas",
        "araras_mt",
        "vigibarragens",
        "ses_estoque_saf",
        "noaa_enso",
        "open_meteo",
    ]
