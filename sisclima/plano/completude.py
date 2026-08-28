# -*- coding: utf-8 -*-
"""Completude automática — independente do percentual de desempenho.

Sem dado válido não vira 0% nem vermelho de meta.
"""
from __future__ import annotations

from typing import Any

from sisclima.plano.escalonamento import item_escalonamento, limiares_completude, pesos_completude

SEM_FONTE = frozenset(
    {
        "IND-008",
        "IND-069",
        "IND-070",
        "IND-075",
        "IND-076",
        "IND-077",
        "IND-052",
        "IND-053",
    }
)


def _tem_texto(valor: Any) -> bool:
    return bool(str(valor or "").strip()) and str(valor).strip() not in {"—", "-", "None"}


def pontuar_completude(linha: dict[str, Any]) -> dict[str, Any]:
    """Devolve score 0–100 e status. Não inventa numerador."""
    pesos = pesos_completude()
    iid = str(linha.get("id") or "")
    situacao = str(linha.get("situacao") or "")
    modo = str(linha.get("modo") or "")
    esc = item_escalonamento(iid)

    fonte_ok = situacao != "aguardando_fonte" and iid not in SEM_FONTE
    if situacao == "coletado" or (linha.get("numerador") is not None and linha.get("denominador")):
        fonte_ok = True
    if situacao == "aguardando_fonte":
        fonte_ok = False

    atualidade_ok = fonte_ok and situacao in {"coletado", "informado", "validado", "em_validacao"}
    num_ok = linha.get("numerador") is not None
    den_ok = linha.get("denominador") not in (None, 0, "")
    evidencia_ok = _tem_texto(linha.get("evidencia") or linha.get("link_sei") or linha.get("nota"))
    if modo == "automatico" and situacao == "coletado":
        evidencia_ok = True
    if modo == "documental" and situacao in {"informado", "em_validacao", "validado"}:
        evidencia_ok = True
    resp_ok = _tem_texto(linha.get("responsavel") or linha.get("area_id") or linha.get("area"))
    if esc.get("pendencia_parametro") and str(esc.get("classe_emergencia") or "") == "B":
        # Classe B sem limiar homologado: não pontua atualidade plena.
        atualidade_ok = False

    pontos = 0
    if fonte_ok:
        pontos += pesos["fonte"]
    if atualidade_ok:
        pontos += pesos["atualidade"]
    if num_ok:
        pontos += pesos["numerador"]
    if den_ok:
        pontos += pesos["denominador"]
    if evidencia_ok:
        pontos += pesos["evidencia"]
    if resp_ok:
        pontos += pesos["responsavel"]

    padrao = str(linha.get("padrao_completude") or esc.get("padrao_completude") or "")
    papel = str(linha.get("papel_operacional") or "")
    den_valor = linha.get("denominador")
    lim = limiares_completude()
    if den_valor == 0:
        status = "nao_aplicavel"
    elif papel == "alias" or str(linha.get("id_canonico") or ""):
        status = "alias"
        pontos = 100 if str(linha.get("id_canonico") or "") else pontos
    elif not fonte_ok:
        status = "sem_dado_valido"
    elif padrao == "C4":
        status = "calculavel" if fonte_ok and atualidade_ok else "nao_calculavel"
    elif padrao == "C2" and not evidencia_ok:
        status = "nao_calculavel"
    elif padrao == "C5" and not (num_ok and den_ok and fonte_ok):
        status = "nao_calculavel"
    elif pontos >= lim["calculavel"]:
        status = "calculavel"
    elif pontos >= lim["ressalva"]:
        status = "com_ressalva"
    else:
        status = "incompleto"

    return {
        "id": iid,
        "completude": pontos,
        "status_completude": status,
        "fonte_ok": fonte_ok,
        "atualidade_ok": atualidade_ok,
        "numerador_ok": num_ok,
        "denominador_ok": den_ok,
        "evidencia_ok": evidencia_ok,
        "responsavel_ok": resp_ok,
    }


def enriquecer_completude(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in linhas:
        item = dict(row)
        item.update(pontuar_completude(item))
        out.append(item)
    return out
