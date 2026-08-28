# -*- coding: utf-8 -*-
"""Overlay de sugestão para indicadores sem leitura oficial.

Não grava `atualizacao`. Sem numerador para SISAGUA, entomologia ou denúncias.
A área confirma; o ARARAS não trata isto como dado oficial.
"""
from __future__ import annotations

from typing import Any

SEM_NUMERADOR = frozenset(
    {
        "IND-008",
        "IND-069",
        "IND-070",  # SISAGUA / Vigiágua
        "IND-075",
        "IND-076",
        "IND-077",  # entomologia COVSAM
        "IND-052",
        "IND-053",  # denúncias COVSAN
    }
)

ONDA_1_DOCUMENTAIS = (
    "IND-002",
    "IND-014",
    "IND-028",
    "IND-033",
    "IND-035",
    "IND-042",
    "IND-044",
    "IND-046",
    "IND-050",
)
ONDA_2_GOVERNANCA = ("IND-001", "IND-003")
ONDA_3_ATENCAO = (
    "IND-017",
    "IND-020",
    "IND-022",
    "IND-082",
    "IND-084",
    "IND-085",
    "IND-087",
    "IND-088",
)
ONDA_4_NAO_ZERAR = (
    "IND-009",
    "IND-010",
    "IND-036",
    "IND-037",
    "IND-038",
    "IND-039",
    "IND-040",
    "IND-041",
    "IND-043",
    "IND-045",
    "IND-047",
    "IND-048",
    "IND-049",
    "IND-051",
)

_ONDA_POR_ID: dict[str, str] = {}
for _iid in ONDA_1_DOCUMENTAIS:
    _ONDA_POR_ID[_iid] = "1"
for _iid in ONDA_2_GOVERNANCA:
    _ONDA_POR_ID[_iid] = "2"
for _iid in ONDA_3_ATENCAO:
    _ONDA_POR_ID[_iid] = "3"
for _iid in ONDA_4_NAO_ZERAR:
    _ONDA_POR_ID[_iid] = "4"

_NOTA_DOCUMENTAL = (
    "Documental: marcar Sim e colar o SEI se o documento já existe. "
    "Cada 1/1 sobe o índice operacional; 0/1 baixa. Não inventar Sim."
)
_NOTA_IND031 = "Mapeamento (IND-032) não é estratégia vigente — não copiar 142/142."
_NOTA_IND082 = "CNES é capacidade instalada (IND-083), não plano de contingência vigente."


def meta_fila(indicador_id: str, *, modo: str = "", entra_no_indice: bool = True) -> dict[str, str]:
    iid = str(indicador_id or "")
    onda = _ONDA_POR_ID.get(iid, "")
    if iid in SEM_NUMERADOR:
        return {"onda": "fonte", "impacto": "neutro"}
    if not entra_no_indice:
        return {"onda": onda or "fora", "impacto": "neutro"}
    if onda == "1":
        return {"onda": "1", "impacto": "sobe"}
    if onda == "2":
        return {"onda": "2", "impacto": "sobe"}
    if onda == "3":
        return {"onda": "3", "impacto": "sobe"}
    if onda == "4":
        return {"onda": "4", "impacto": "pode_descer"}
    if modo == "documental":
        return {"onda": "1", "impacto": "sobe"}
    return {"onda": onda or "area", "impacto": "neutro"}


def sugerir_indicador(indicador_id: str) -> dict[str, Any] | None:
    """Valor sugerido. Nunca persiste. Sem numerador nas 8 fontes externas."""
    iid = str(indicador_id or "")
    if iid in SEM_NUMERADOR:
        return None
    if iid in ONDA_1_DOCUMENTAIS:
        return {
            "numerador": None,
            "denominador": 1,
            "fonte": None,
            "nota": _NOTA_DOCUMENTAL,
            "status": "sugerido",
        }
    if iid == "IND-001":
        return _sugestao_ind001()
    if iid == "IND-003":
        return _sugestao_ind003()
    if iid == "IND-031":
        return {
            "numerador": None,
            "denominador": None,
            "fonte": None,
            "nota": _NOTA_IND031,
            "status": "sugerido",
        }
    if iid in {"IND-082", "IND-084"}:
        return _sugestao_cnes_hospital(iid)
    if iid == "IND-087":
        return _sugestao_cnes_urgencia()
    return None


def sugerir_todos() -> dict[str, dict[str, Any]]:
    from sisclima.plano.catalogo import carregar_catalogo

    cat = carregar_catalogo()
    out: dict[str, dict[str, Any]] = {}
    for item in cat.get("indicadores") or []:
        iid = str(item.get("id") or "")
        sug = sugerir_indicador(iid)
        if sug:
            out[iid] = sug
    return out


def enriquecer_linhas(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Acrescenta onda, impacto e texto de sugestão. Não altera leitura oficial."""
    out: list[dict[str, Any]] = []
    for row in linhas:
        item = dict(row)
        iid = str(item.get("id") or "")
        modo = str(item.get("modo") or "")
        meta = meta_fila(iid, modo=modo, entra_no_indice=bool(item.get("entra_no_indice", True)))
        item["onda"] = meta["onda"]
        item["impacto"] = meta["impacto"]
        situacao = str(item.get("situacao") or "")
        if situacao in {"nao_informado", "aguardando_fonte"} and not item.get("sugestao"):
            sug = sugerir_indicador(iid)
            if sug:
                den = sug.get("denominador")
                num = sug.get("numerador")
                if den:
                    item["sugestao"] = f"{num if num is not None else '—'}/{den}"
                elif sug.get("nota"):
                    item["sugestao"] = "ver nota"
                if sug.get("nota") and not item.get("nota"):
                    item["nota"] = str(sug["nota"])
                item["sugestao_status"] = "sugerido"
        out.append(item)
    return out


def fila_para_indice(linhas: list[dict[str, Any]]) -> dict[str, Any]:
    """Pendências do índice agrupadas pela fila operacional (ondas 1–4)."""
    rows = enriquecer_linhas(list(linhas or []))
    pendentes = [
        r
        for r in rows
        if r.get("entra_no_indice") and str(r.get("situacao") or "") in {"nao_informado", "aguardando_fonte"}
    ]
    grupos: dict[str, list[dict[str, Any]]] = {"1": [], "2": [], "3": [], "4": [], "fonte": [], "area": []}
    for r in pendentes:
        chave = str(r.get("onda") or "area")
        grupos.setdefault(chave, []).append(r)
    return {
        "n_pendentes_indice": len(pendentes),
        "onda1": grupos.get("1") or [],
        "onda2": grupos.get("2") or [],
        "onda3": grupos.get("3") or [],
        "onda4": grupos.get("4") or [],
        "fonte": grupos.get("fonte") or [],
        "area": grupos.get("area") or [],
    }


def _areas_previstas() -> list[str]:
    from sisclima.plano.conectores import _areas_previstas_plano

    return _areas_previstas_plano()


def _sugestao_ind001() -> dict[str, Any] | None:
    previstas = _areas_previstas()
    if not previstas:
        return None
    cobertas: set[str] = set()
    fonte = "plano_vinculo"
    try:
        from sisclima.plano.acesso import listar_vinculos

        for v in listar_vinculos(so_ativos=True):
            aid = str(v.get("area_id") or "")
            if aid in previstas:
                cobertas.add(aid)
    except Exception:  # noqa: BLE001
        cobertas = set()
    if not cobertas:
        from sisclima.plano.participantes import participantes_com_email

        for p in participantes_com_email():
            aid = str(p.get("area_id") or "")
            if aid in previstas:
                cobertas.add(aid)
        fonte = "plano_el_nino_participantes.yaml"
    return {
        "numerador": len(cobertas),
        "denominador": len(previstas),
        "fonte": fonte,
        "nota": "sugerido: cadastro ARARAS (vínculo/participante), não ofício de designação SEI",
        "status": "sugerido",
    }


def _sugestao_ind003() -> dict[str, Any]:
    from sisclima.plano.conectores import N_ERS, _n_ers_resumo

    n, fonte = _n_ers_resumo()
    if n <= 0:
        return {
            "numerador": None,
            "denominador": N_ERS,
            "fonte": None,
            "nota": "área informa N/16 — sem chute. Confirme ERS com ponto focal e contato válido.",
            "status": "sugerido",
        }
    return {
        "numerador": min(n, N_ERS),
        "denominador": N_ERS,
        "fonte": fonte,
        "nota": "sugerido: ERS distintas no painel; confirmar ponto focal, contato e fluxo vigente",
        "status": "sugerido",
    }


def _sugestao_cnes_hospital(iid: str) -> dict[str, Any] | None:
    from sisclima.plano.conectores import _n_unidades_cnes

    n, fonte = _n_unidades_cnes("hospital")
    if n <= 0:
        return None
    o_que = "plano de contingência" if iid == "IND-082" else "protocolos vigentes"
    nota = f"denominador CNES: {n} hospitais; informe quantos têm {o_que}"
    if iid == "IND-082":
        nota = f"{_NOTA_IND082} {nota}"
    return {
        "numerador": None,
        "denominador": n,
        "fonte": fonte,
        "nota": nota,
        "status": "sugerido",
    }


def _sugestao_cnes_urgencia() -> dict[str, Any] | None:
    from sisclima.plano.conectores import _n_unidades_cnes

    n, fonte = _n_unidades_cnes(r"urgencia|urgência|upa|samu|emergencia|emergência|hospital")
    if n <= 0:
        return None
    return {
        "numerador": None,
        "denominador": n,
        "fonte": fonte,
        "nota": f"denominador CNES: {n} serviços de urgência/hospital; informe quantos têm checklist validado",
        "status": "sugerido",
    }
