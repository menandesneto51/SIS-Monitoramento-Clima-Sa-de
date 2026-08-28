# -*- coding: utf-8 -*-
"""Motor de indicadores do Plano El Niño — Sala de Situação ARARAS.

A área informa numerador/denominador ou anexa evidência.
O ARARAS calcula o percentual e o semáforo. Nada entra no painel
executivo sem validação da secretaria-executiva (CIEVS).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT

from sisclima.plano.catalogo import carregar_catalogo
from sisclima.plano.indicadores import progresso as _progresso_oficial

CATALOGO = ROOT / "config" / "plano_el_nino_2026_catalogo.yaml"


def load_catalogo(path: Path | None = None) -> dict[str, Any]:
    if path is not None:
        if not path.exists():
            return {"plano": {}, "acoes": [], "indicadores": [], "totais": {}}
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return carregar_catalogo()


def progresso(numerador: float | None, denominador: float | None) -> float | None:
    return _progresso_oficial(numerador, denominador)


def semaforo_percentual(pct: float | None, *, meta: float = 100.0) -> str:
    """Verde na meta; amarelo em andamento; vermelho crítico."""
    if pct is None:
        return "nao_informado"
    if pct >= meta:
        return "meta_atingida"
    if pct >= 70:
        return "em_andamento"
    if pct > 0:
        return "atraso_risco"
    return "nao_iniciado"


def rotulo_semaforo(codigo: str) -> str:
    return {
        "nao_informado": "⚪ Sem informação",
        "nao_iniciado": "⚪ Não iniciada",
        "em_andamento": "🟡 Em andamento",
        "atraso_risco": "🟠 Atraso / risco",
        "vencida": "🔴 Prazo vencido",
        "meta_atingida": "🟢 Meta atingida",
        "em_validacao": "🟠 Em validação",
        "rejeitado": "🔴 Correção solicitada",
    }.get(codigo, codigo)


def consolidar_eixos(indicadores: list[dict[str, Any]], valores: dict[str, float]) -> list[dict[str, Any]]:
    """Média simples dos percentuais validados por eixo (execução/capacidade)."""
    buckets: dict[str, list[float]] = {}
    for ind in indicadores:
        if ind.get("tipo") == "risco_gatilho":
            continue
        iid = ind.get("id")
        if iid not in valores:
            continue
        buckets.setdefault(str(ind.get("eixo") or "—"), []).append(float(valores[iid]))
    out = []
    for eixo, vals in sorted(buckets.items()):
        media = round(sum(vals) / len(vals), 1) if vals else None
        out.append({"eixo": eixo, "n": len(vals), "cumprimento_pct": media, "semaforo": semaforo_percentual(media)})
    return out
