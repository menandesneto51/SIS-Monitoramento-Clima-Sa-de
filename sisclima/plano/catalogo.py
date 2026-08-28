# -*- coding: utf-8 -*-
"""Catálogo do Plano El Niño 2026 carregado de YAML."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT
from sisclima.plano.constants import (
    MAPA_MODO_PLANILHA,
    MAPA_TIPO_PLANILHA,
    MODOS_INDICADOR_SET,
    TIPOS_NO_INDICE,
)
from sisclima.plano.escalonamento import enriquecer_item_catalogo

CFG_DIR = ROOT / "config"
CATALOGO_PATH = CFG_DIR / "plano_el_nino_2026_catalogo.yaml"
OPERACAO_PATH = CFG_DIR / "plano_el_nino_2026.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _slug_tipo(valor: str) -> str:
    t = str(valor or "").strip().casefold().replace("ã", "a").replace("ç", "c")
    t = t.replace(" ", "")
    return MAPA_TIPO_PLANILHA.get(t, t if t in {"execucao", "capacidade", "resultado", "risco_gatilho"} else "execucao")


def _slug_modo(valor: str) -> str:
    t = str(valor or "").strip().casefold().replace("á", "a").replace("é", "e").replace(" ", "")
    mapped = MAPA_MODO_PLANILHA.get(t, "")
    if mapped in MODOS_INDICADOR_SET:
        return mapped
    if "semi" in t:
        return "semiautomatico"
    if "manual" in t or "document" in t:
        return "documental"
    if "auto" in t:
        return "automatico"
    return "documental"


@lru_cache(maxsize=1)
def carregar_operacao() -> dict[str, Any]:
    return _load_yaml(OPERACAO_PATH)


@lru_cache(maxsize=1)
def carregar_catalogo() -> dict[str, Any]:
    cat = _load_yaml(CATALOGO_PATH)
    op = carregar_operacao()
    if not cat:
        return {"plano": op.get("plano") or {}, "eixos": [], "metas": [], "acoes": [], "indicadores": [], "areas": []}
    indicadores = []
    for raw in cat.get("indicadores") or []:
        item = dict(raw)
        item["tipo"] = _slug_tipo(item.get("tipo") or item.get("tipo_planilha") or "")
        item["modo_atualizacao"] = _slug_modo(
            item.get("modo_atualizacao") or item.get("classe_automacao") or item.get("automacao") or ""
        )
        item["entra_no_indice"] = item["tipo"] in TIPOS_NO_INDICE
        item = enriquecer_item_catalogo(item)
        papel = str(item.get("papel_operacional") or "")
        if papel in {"gatilho", "alias"}:
            item["entra_no_indice"] = False
        elif papel:
            item["entra_no_indice"] = item["tipo"] in TIPOS_NO_INDICE
        indicadores.append(item)
    cat["indicadores"] = indicadores
    cat.setdefault("plano", op.get("plano") or {})
    return cat


def indicadores_do_indice(catalogo: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cat = catalogo or carregar_catalogo()
    return [i for i in cat.get("indicadores") or [] if i.get("entra_no_indice", i.get("tipo") in TIPOS_NO_INDICE)]


def resumo_adequacao(catalogo: dict[str, Any] | None = None) -> dict[str, Any]:
    """Contagem da proposta 28/08: 44 operacional, 17 preparação, 16 gatilho, 8 híbrido, 3 alias."""
    from collections import Counter

    cat = catalogo or carregar_catalogo()
    inds = list(cat.get("indicadores") or [])
    papeis = Counter(str(i.get("papel_operacional") or "") for i in inds)
    return {
        "n": len(inds),
        "por_papel": dict(papeis),
        "n_indice": sum(1 for i in inds if i.get("entra_no_indice")),
        "n_ativos": sum(1 for i in inds if str(i.get("papel_operacional") or "") != "alias"),
        "versao": "28-08-2026",
    }


def acao_por_id(acao_id: str, catalogo: dict[str, Any] | None = None) -> dict[str, Any] | None:
    cat = catalogo or carregar_catalogo()
    alvo = str(acao_id or "").strip()
    for acao in cat.get("acoes") or []:
        if str(acao.get("id") or "") == alvo:
            return acao
    return None


def indicador_por_id(indicador_id: str, catalogo: dict[str, Any] | None = None) -> dict[str, Any] | None:
    cat = catalogo or carregar_catalogo()
    alvo = str(indicador_id or "").strip()
    for item in cat.get("indicadores") or []:
        if str(item.get("id") or "") == alvo or str(item.get("codigo_fonte") or "") == alvo:
            return item
    return None
