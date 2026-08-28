# -*- coding: utf-8 -*-
"""Camada de escalonamento (classe A/B/C/D, perfil E, cadência por estágio)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from sisclima.core.config import ROOT

PATH = ROOT / "config" / "plano_el_nino_escalonamento.yaml"
ADEQUACAO_PATH = ROOT / "config" / "plano_el_nino_adequacao.yaml"

ESTAGIOS = ("verde", "amarelo", "laranja", "vermelho", "roxo")
CLASSES = frozenset({"A", "B", "C", "D"})
PAPEIS_OPERACIONAIS = ("operacional", "preparacao", "gatilho", "hibrido", "alias")
PAPEIS_FORA_INDICE = frozenset({"gatilho", "alias"})


@lru_cache(maxsize=1)
def carregar_escalonamento() -> dict[str, Any]:
    if not PATH.exists():
        return {"indicadores": [], "indicadores_cievs": [], "perfis": {}, "pesos_completude": {}}
    data = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def limpar_cache_escalonamento() -> None:
    carregar_escalonamento.cache_clear()
    carregar_adequacao.cache_clear()


@lru_cache(maxsize=1)
def carregar_adequacao() -> dict[str, Any]:
    if not ADEQUACAO_PATH.exists():
        return {"indicadores": [], "perfis_s": {}, "padroes_completude": {}}
    data = yaml.safe_load(ADEQUACAO_PATH.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def mapa_adequacao() -> dict[str, dict[str, Any]]:
    cfg = carregar_adequacao()
    out: dict[str, dict[str, Any]] = {}
    for raw in cfg.get("indicadores") or []:
        iid = str(raw.get("id") or "")
        if iid:
            out[iid] = dict(raw)
    return out


def item_adequacao(indicador_id: str) -> dict[str, Any]:
    return dict(mapa_adequacao().get(str(indicador_id or "")) or {})


def perfil_s(codigo: str) -> dict[str, Any]:
    return dict((carregar_adequacao().get("perfis_s") or {}).get(str(codigo or "")) or {})


def cadencia_perfil_s(codigo: str, estagio: str) -> str:
    bloco = perfil_s(codigo)
    est = str(estagio or "verde").casefold()
    if est not in ESTAGIOS:
        est = "verde"
    return str(bloco.get(est) or "")


def mapa_indicadores() -> dict[str, dict[str, Any]]:
    cfg = carregar_escalonamento()
    out: dict[str, dict[str, Any]] = {}
    for raw in cfg.get("indicadores") or []:
        iid = str(raw.get("id") or "")
        if iid:
            out[iid] = dict(raw)
    return out


def item_escalonamento(indicador_id: str) -> dict[str, Any]:
    return dict(mapa_indicadores().get(str(indicador_id or "")) or {})


def enriquecer_item_catalogo(item: dict[str, Any]) -> dict[str, Any]:
    return enriquecer_catalogo_item(item)


def enriquecer_catalogo_item(item: dict[str, Any]) -> dict[str, Any]:
    """Copia campos de escalonamento e da adequação 28/08 para o item do catálogo."""
    out = dict(item)
    iid = str(item.get("id") or "")
    esc = item_escalonamento(iid)
    if not esc:
        out.setdefault("classe_emergencia", "")
        out.setdefault("gate_prontidao", False)
    else:
        out["classe_emergencia"] = esc.get("classe_emergencia") or ""
        out["perfil_escalonamento"] = esc.get("perfil_escalonamento") or ""
        out["tipo_emergencia"] = esc.get("tipo_emergencia") or ""
        out["gate_prontidao"] = bool(esc.get("gate_prontidao"))
        out["cadencia_por_estagio"] = dict(esc.get("cadencia_por_estagio") or {})
        out["id_canonico"] = esc.get("id_canonico") or ""
        out["pendencia_parametro"] = esc.get("pendencia_parametro") or ""
    adq = item_adequacao(iid)
    if not adq:
        out.setdefault("papel_operacional", "")
        out.setdefault("perfil_s", "")
        out.setdefault("padrao_completude", "")
        return out
    papel = str(adq.get("papel") or "")
    out["papel_operacional"] = papel
    out["nome_ajustado"] = adq.get("nome_ajustado") or out.get("nome") or ""
    out["decisao_adequacao"] = adq.get("decisao") or ""
    out["perfil_s"] = adq.get("perfil_s") or ""
    out["padrao_completude"] = adq.get("padrao_completude") or ""
    out["alvo_automacao"] = adq.get("alvo_automacao") or ""
    out["alteracao_proposta"] = adq.get("alteracao") or ""
    out["subindicadores"] = list(adq.get("subindicadores") or [])
    if adq.get("id_canonico"):
        out["id_canonico"] = adq["id_canonico"]
    cad_s = {est: cadencia_perfil_s(out["perfil_s"], est) for est in ESTAGIOS}
    if any(cad_s.values()):
        out["cadencia_por_estagio"] = cad_s
    if papel == "alias":
        out["classe_emergencia"] = "D"
        out["gate_prontidao"] = False
        out["entra_no_indice"] = False
    elif papel == "gatilho":
        out["gate_prontidao"] = False
        out["entra_no_indice"] = False
        out["tipo"] = "risco_gatilho"
    elif papel == "preparacao":
        out["gate_prontidao"] = True
        if str(out.get("classe_emergencia") or "") not in {"C", "D"}:
            out["classe_emergencia"] = "C"
    elif papel == "operacional":
        if str(out.get("classe_emergencia") or "") == "C":
            out["classe_emergencia"] = "A"
        out["gate_prontidao"] = False
    elif papel == "hibrido":
        out["gate_prontidao"] = str(adq.get("padrao_completude") or "") == "C2"
    return out


def cadencia(indicador_id: str, estagio: str) -> str:
    esc = item_escalonamento(indicador_id)
    adq = item_adequacao(indicador_id)
    est = str(estagio or "verde").casefold()
    if est not in ESTAGIOS:
        est = "verde"
    perfil_novo = str(adq.get("perfil_s") or "")
    cad_s = cadencia_perfil_s(perfil_novo, est)
    if cad_s:
        return cad_s
    cad = esc.get("cadencia_por_estagio") or {}
    if isinstance(cad, dict) and cad.get(est):
        return str(cad[est])
    perfis = carregar_escalonamento().get("perfis") or {}
    perfil = str(esc.get("perfil_escalonamento") or "")
    bloco = perfis.get(perfil) or {}
    cad2 = bloco.get("cadencia_por_estagio") or {}
    return str(cad2.get(est) or "")


def indicadores_cievs() -> list[dict[str, Any]]:
    return [dict(x) for x in (carregar_escalonamento().get("indicadores_cievs") or [])]


def pesos_completude() -> dict[str, int]:
    raw = carregar_escalonamento().get("pesos_completude") or {}
    return {
        "fonte": int(raw.get("fonte") or 25),
        "atualidade": int(raw.get("atualidade") or raw.get("atualidade") or 25),
        "numerador": int(raw.get("numerador") or 20),
        "denominador": int(raw.get("denominador") or 15),
        "evidencia": int(raw.get("evidencia") or 10),
        "responsavel": int(raw.get("responsavel") or 5),
    }


def limiares_completude() -> dict[str, int]:
    raw = carregar_escalonamento().get("limiares_completude") or {}
    return {
        "calculavel": int(raw.get("calculavel") or 95),
        "ressalva": int(raw.get("ressalva") or 80),
    }
