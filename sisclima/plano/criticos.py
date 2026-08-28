# -*- coding: utf-8 -*-
"""Indicadores mais críticos da Sala — adequação 28/08 + operação.

Não inventa numerador. Sem fonte = não calculável, nunca zero.
"""
from __future__ import annotations

from typing import Any

from sisclima.plano.areas import rotulo_area
from sisclima.plano.catalogo import carregar_catalogo
from sisclima.plano.conectores import BLOCO_AGUARDANDO, ESTOQUE_DEFASADO
from sisclima.plano.escalonamento import item_escalonamento

# Deliberação 6 da proposta 28/08: limiares/baselines antes do go-live.
LIMIARES_HOMOLOGAR = (
    "IND-013",
    "IND-016",
    "IND-021",
    "IND-062",
    "IND-063",
    "IND-064",
    "IND-065",
    "IND-066",
    "IND-067",
    "IND-075",
    "IND-076",
    "IND-077",
)

PAPEIS_ROTULO = {
    "operacional": "Operacional",
    "preparacao": "Prontidão",
    "gatilho": "Gatilho",
    "hibrido": "Híbrido",
    "alias": "Alias",
}


def _motivo(item: dict[str, Any], esc: dict[str, Any], situacao: str) -> str:
    iid = str(item.get("id") or "")
    partes: list[str] = []
    if iid in LIMIARES_HOMOLOGAR:
        partes.append("Homologar limiar/baseline antes de regra automática")
    pend = str(esc.get("pendencia_parametro") or "").strip()
    if pend:
        partes.append(pend)
    if iid in BLOCO_AGUARDANDO:
        partes.append(f"Sem conector contínuo ({BLOCO_AGUARDANDO[iid]})")
    if iid in ESTOQUE_DEFASADO:
        partes.append("Carga de estoque pode estar defasada — não tratar como ruptura atual")
    if str(item.get("papel_operacional") or "") == "gatilho":
        partes.append("Gatilho: não entra no índice; abre verificação/PAI a partir do Amarelo")
    if item.get("gate_prontidao") or str(item.get("papel_operacional") or "") == "preparacao":
        partes.append("Gate de prontidão: 100% no Verde/Amarelo; Laranja+ só validade/acionamento")
    if situacao == "aguardando_fonte":
        partes.append("Não calculável nesta rodada")
    return " · ".join(partes) or str(item.get("alteracao_proposta") or item.get("decisao_adequacao") or "—")


def _prioridade(item: dict[str, Any], esc: dict[str, Any], situacao: str) -> int:
    iid = str(item.get("id") or "")
    if iid in LIMIARES_HOMOLOGAR and (iid in BLOCO_AGUARDANDO or str(esc.get("classe_emergencia")) == "B"):
        return 1
    if iid in LIMIARES_HOMOLOGAR:
        return 2
    if iid in BLOCO_AGUARDANDO or situacao == "aguardando_fonte":
        return 3
    if str(esc.get("classe_emergencia") or "") == "B":
        return 4
    if str(item.get("papel_operacional") or "") == "gatilho":
        return 5
    if item.get("gate_prontidao") or str(item.get("papel_operacional") or "") == "preparacao":
        return 6
    if iid in ESTOQUE_DEFASADO:
        return 7
    return 9


def _pacote(item: dict[str, Any], esc: dict[str, Any], situacao: str) -> str:
    iid = str(item.get("id") or "")
    if iid in LIMIARES_HOMOLOGAR:
        return "limiar"
    if iid in BLOCO_AGUARDANDO or situacao == "aguardando_fonte":
        return "sem_fonte"
    if str(esc.get("classe_emergencia") or "") == "B":
        return "classe_b"
    if str(item.get("papel_operacional") or "") == "gatilho":
        return "gatilho"
    if item.get("gate_prontidao") or str(item.get("papel_operacional") or "") == "preparacao":
        return "prontidao"
    if iid in ESTOQUE_DEFASADO:
        return "estoque"
    return "outros"


def _leituras_por_id() -> dict[str, dict[str, Any]]:
    try:
        from sisclima.plano.conectores import coletar_automaticos
        from sisclima.plano.indicadores import linhas_painel_indicadores, quadro_indicadores

        quadro = quadro_indicadores(so_indice=False)
        leituras = coletar_automaticos()
        linhas = linhas_painel_indicadores(quadro=quadro, leituras_auto=leituras)
        return {str(r.get("id") or ""): r for r in linhas if r.get("id")}
    except Exception:
        return {}


def quadro_criticos(*, incluir_prontidao: bool = True) -> dict[str, Any]:
    """Lista priorizada. Sem dado não vira 0."""
    cat = carregar_catalogo()
    live = _leituras_por_id()
    rows: list[dict[str, Any]] = []
    for item in cat.get("indicadores") or []:
        iid = str(item.get("id") or "")
        esc = item_escalonamento(iid)
        live_row = live.get(iid) or {}
        situacao = str(live_row.get("situacao") or "")
        pacote = _pacote(item, esc, situacao)
        if pacote == "outros":
            continue
        if pacote == "prontidao" and not incluir_prontidao:
            continue
        leitura = str(live_row.get("leitura") or "—")
        if situacao in {"aguardando_fonte", "nao_informado", ""}:
            leitura = "—"
        rows.append(
            {
                "id": iid,
                "codigo_fonte": item.get("codigo_fonte") or "",
                "nome": item.get("nome_ajustado") or item.get("nome") or "",
                "area_id": item.get("area_id") or "",
                "area": rotulo_area(str(item.get("area_id") or "")),
                "papel": str(item.get("papel_operacional") or ""),
                "papel_rotulo": PAPEIS_ROTULO.get(str(item.get("papel_operacional") or ""), "—"),
                "perfil_s": item.get("perfil_s") or "",
                "padrao_c": item.get("padrao_completude") or "",
                "classe": esc.get("classe_emergencia") or item.get("classe_emergencia") or "",
                "pendencia_parametro": esc.get("pendencia_parametro") or "",
                "situacao": situacao or "nao_informado",
                "leitura": leitura,
                "percentual": live_row.get("percentual") if situacao == "coletado" else None,
                "pacote": pacote,
                "prioridade": _prioridade(item, esc, situacao),
                "motivo": _motivo(item, esc, situacao),
                "entra_no_indice": bool(item.get("entra_no_indice")),
                "subindicadores": list(item.get("subindicadores") or []),
            }
        )
    rows.sort(key=lambda r: (int(r["prioridade"]), str(r["id"])))
    por_pacote: dict[str, int] = {}
    for r in rows:
        por_pacote[str(r["pacote"])] = por_pacote.get(str(r["pacote"]), 0) + 1
    return {
        "n": len(rows),
        "por_pacote": por_pacote,
        "n_limiar": sum(1 for r in rows if r["pacote"] == "limiar"),
        "n_sem_fonte": sum(1 for r in rows if r["id"] in BLOCO_AGUARDANDO),
        "n_classe_b": sum(1 for r in rows if r["classe"] == "B"),
        "n_gatilho": sum(1 for r in rows if r["papel"] == "gatilho"),
        "n_prontidao": sum(1 for r in rows if r["pacote"] == "prontidao"),
        "linhas": rows,
        "limiares": [r for r in rows if r["pacote"] == "limiar"],
        "sem_fonte": [r for r in rows if r["id"] in BLOCO_AGUARDANDO],
        "classe_b": [r for r in rows if r["classe"] == "B"],
        "gatilhos": [r for r in rows if r["papel"] == "gatilho"],
        "prontidao": [r for r in rows if r["pacote"] == "prontidao"],
        "estoque": [r for r in rows if r["id"] in ESTOQUE_DEFASADO],
        "nota": (
            "Sem dado válido o indicador fica não calculável — não é meta não atingida. "
            "Gatilho não reduz o índice de implementação. "
            "Estágio de resposta é decisão do Comando, independente do nível de risco."
        ),
    }
