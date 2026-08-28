# -*- coding: utf-8 -*-
"""Cobrança operacional dos indicadores do Plano El Niño.

Classifica o que a área precisa informar, o que falta de fonte e quem
receber o ofício. E-mail é rascunho — o registro oficial continua a Sala.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path
from typing import Any

from sisclima.plano.areas import rotulo_area
from sisclima.plano.catalogo import carregar_catalogo
from sisclima.plano.conectores import ESTOQUE_DEFASADO
from sisclima.plano.participantes import participantes_com_email

EMAILS_CIEVS = ("menandesneto@ses.mt.gov.br", "tatianabelmonte@ses.mt.gov.br")

ACAO_DOCUMENTAL = "Anexar evidência (link SEI) e registrar Sim/Não na Sala"
ACAO_SUGESTAO = "Confirmar a leitura sugerida pelo ARARAS na Sala e enviar à validação CIEVS"
ACAO_INFORMAR = "Informar numerador e denominador na Sala (não inventar zero)"
ACAO_FONTE = "Disponibilizar a base para o conector automático (CIEVS + área dona da fonte)"
ACAO_ESTOQUE = "Atualizar a carga oficial de estoque — leitura atual pode estar defasada"
ACAO_FOCAL = "Indicar ponto focal com e-mail na Portaria 0590 / catálogo de participantes"


def _areas_catalogo() -> list[str]:
    cat = carregar_catalogo()
    return [
        str(a.get("id") or "")
        for a in cat.get("areas") or []
        if str(a.get("id") or "") not in {"", "multi_area"}
    ]


def areas_sem_focal() -> list[dict[str, str]]:
    previstas = set(_areas_catalogo())
    pessoas = participantes_com_email()
    cobertas = {str(p.get("area_id") or "") for p in pessoas if str(p.get("area_id") or "") in previstas}
    return [{"area_id": aid, "area": rotulo_area(aid), "acao": ACAO_FOCAL} for aid in sorted(previstas - cobertas)]


def contatos_da_area(area_id: str) -> list[dict[str, str]]:
    out = []
    vistos: set[str] = set()
    for p in participantes_com_email():
        if str(p.get("area_id") or "") != area_id:
            continue
        email = str(p.get("email") or "").strip().lower()
        if "@" not in email or email in vistos:
            continue
        vistos.add(email)
        out.append(
            {
                "nome": str(p.get("nome") or ""),
                "email": email,
                "sigla": str(p.get("sigla") or ""),
                "telefone": str(p.get("telefone") or ""),
                "perfil": str(p.get("perfil_sugerido") or ""),
            }
        )
    return out


def classificar_pendencia(row: dict[str, Any]) -> dict[str, Any] | None:
    """Devolve a pendência acionável, ou None se não há cobrança."""
    from sisclima.plano.sugestoes import meta_fila

    situacao = str(row.get("situacao") or "")
    modo = str(row.get("modo") or "")
    iid = str(row.get("id") or "")
    papel = str(row.get("papel_operacional") or "")
    if papel == "alias" or str(row.get("classe_emergencia") or "") == "D":
        return None
    if papel == "gatilho" and situacao in {"nao_informado", "coletado"}:
        if situacao == "nao_informado":
            return None
    onda = str(row.get("onda") or meta_fila(iid, modo=modo, entra_no_indice=bool(row.get("entra_no_indice", True)))["onda"])
    if situacao == "nao_informado":
        if row.get("gate_prontidao") or str(row.get("classe_emergencia") or "") == "C":
            return {
                "id": iid,
                "prioridade": 6,
                "classe": "prontidao",
                "acao": "Gate de prontidão (Verde/Amarelo) — não tratar como atraso de crise",
                "onda": onda or "prontidao",
            }
        sug = str(row.get("sugestao") or "").strip()
        if modo == "documental" or onda == "1":
            prioridade, acao = 1, ACAO_DOCUMENTAL
        elif sug and sug not in {"—", "-", "ver nota"}:
            prioridade, acao = 2, f"{ACAO_SUGESTAO} ({sug})"
        elif onda == "4":
            prioridade, acao = 3, "Informar numerador real — não registrar zero (derruba o operacional)"
        else:
            prioridade, acao = 3, ACAO_INFORMAR
        return {
            "id": iid,
            "prioridade": prioridade,
            "classe": "area",
            "acao": acao,
            "onda": onda,
        }
    if situacao == "aguardando_fonte":
        bloco = str(row.get("bloco_pendente") or row.get("bloco") or "fonte sem conector")
        return {
            "id": iid,
            "prioridade": 4,
            "classe": "fonte",
            "acao": f"{ACAO_FONTE} — {bloco}",
            "onda": onda or "fonte",
        }
    if iid in ESTOQUE_DEFASADO or "defasad" in str(row.get("nota") or "").casefold():
        return {
            "id": iid,
            "prioridade": 5,
            "classe": "carga",
            "acao": ACAO_ESTOQUE,
            "onda": onda,
        }
    return None


def _linhas_base(linhas: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if linhas is not None:
        return list(linhas)
    from sisclima.plano.conectores import coletar_automaticos
    from sisclima.plano.indicadores import linhas_painel_indicadores, quadro_indicadores

    quadro = quadro_indicadores(so_indice=False)
    return linhas_painel_indicadores(quadro=quadro, leituras_auto=coletar_automaticos())


def relatorio_cobranca(
    linhas: list[dict[str, Any]] | None = None,
    *,
    coletado_em: str = "",
) -> dict[str, Any]:
    rows = _linhas_base(linhas)
    quando = coletado_em or datetime.now().strftime("%d/%m/%Y %H:%M")
    por_area: dict[str, dict[str, Any]] = {}
    itens: list[dict[str, Any]] = []
    for row in rows:
        pend = classificar_pendencia(row)
        if not pend:
            continue
        item = {
            **pend,
            "nome": row.get("nome") or "",
            "area_id": row.get("area_id") or "",
            "area": row.get("area") or rotulo_area(str(row.get("area_id") or "")),
            "modo": row.get("modo") or "",
            "situacao": row.get("situacao") or "",
            "leitura": row.get("leitura") or "—",
            "indice": bool(row.get("entra_no_indice")),
            "sugestao": row.get("sugestao") or "",
            "fonte": row.get("fonte") or "",
            "onda": pend.get("onda") or row.get("onda") or "",
        }
        itens.append(item)
        aid = str(item["area_id"])
        bloco = por_area.setdefault(
            aid,
            {
                "area_id": aid,
                "area": item["area"],
                "n_area": 0,
                "n_fonte": 0,
                "n_carga": 0,
                "n_documental": 0,
                "n_indice": 0,
                "ids": [],
                "itens": [],
                "contatos": contatos_da_area(aid),
            },
        )
        bloco["ids"].append(item["id"])
        bloco["itens"].append(
            {
                "id": item["id"],
                "nome": item["nome"],
                "acao": item["acao"],
                "classe": item["classe"],
                "onda": item.get("onda") or "",
            }
        )
        if item["classe"] == "area":
            bloco["n_area"] += 1
            if item["modo"] == "documental":
                bloco["n_documental"] += 1
        elif item["classe"] == "fonte":
            bloco["n_fonte"] += 1
        else:
            bloco["n_carga"] += 1
        if item["indice"]:
            bloco["n_indice"] += 1

    focais = areas_sem_focal()
    areas = sorted(
        por_area.values(),
        key=lambda a: (-(a["n_area"] + a["n_fonte"] + a["n_carga"]), a["area"]),
    )
    itens.sort(key=lambda r: (r["prioridade"], r["area"], r["id"]))
    n_area = sum(1 for i in itens if i["classe"] == "area")
    n_fonte = sum(1 for i in itens if i["classe"] == "fonte")
    n_carga = sum(1 for i in itens if i["classe"] == "carga")
    n_doc = sum(1 for i in itens if i["modo"] == "documental" and i["classe"] == "area")
    return {
        "coletado_em": quando,
        "n_pendencias": len(itens),
        "n_cobrar_area": n_area,
        "n_aguardar_fonte": n_fonte,
        "n_carga_defasada": n_carga,
        "n_documentais": n_doc,
        "n_areas": len(areas),
        "areas_sem_focal": focais,
        "areas": areas,
        "itens": itens,
        "cc_cievs": list(EMAILS_CIEVS),
    }


def rascunho_email_area(bloco: dict[str, Any], *, coletado_em: str = "") -> dict[str, str]:
    area = str(bloco.get("area") or "")
    ids = ", ".join(bloco.get("ids") or [])
    para = "; ".join(c["email"] for c in bloco.get("contatos") or [])
    n_area = int(bloco.get("n_area") or 0)
    n_fonte = int(bloco.get("n_fonte") or 0)
    n_carga = int(bloco.get("n_carga") or 0)
    n_doc = int(bloco.get("n_documental") or 0)
    itens = list(bloco.get("itens") or [])
    onda1 = [it for it in itens if str(it.get("onda") or "") == "1"]
    resto = [it for it in itens if str(it.get("onda") or "") != "1"]
    linhas_item = []
    if onda1:
        linhas_item.append("Prioridade desta semana (documental — Sim + SEI):")
        for it in onda1:
            linhas_item.append(f"- {it.get('id')}: {it.get('nome')} — {it.get('acao')}")
        if resto:
            linhas_item.append("")
            linhas_item.append("Demais pendências:")
    for it in resto:
        linhas_item.append(f"- {it.get('id')}: {it.get('nome')} — {it.get('acao')}")
    lista = "\n".join(linhas_item) if linhas_item else f"- {ids}"
    corpo = (
        f"Prezados(as) da {area},\n\n"
        f"Segue a cobrança dos indicadores do Plano El Niño (Portaria SES-MT 0590/2026) "
        f"com leitura em {coletado_em or datetime.now().strftime('%d/%m/%Y')}.\n\n"
        f"Pendências desta área: {n_area} para informar na Sala"
        + (f", das quais {n_doc} documentais (Sim/Não + link SEI)" if n_doc else "")
        + (f"; {n_fonte} aguardando integração de fonte" if n_fonte else "")
        + (f"; {n_carga} com carga defasada" if n_carga else "")
        + ".\n\n"
        f"{lista}\n\n"
        "O registro oficial é a Sala de Situação do ARARAS MT "
        "(painel interno → Sala de Situação / Plano El Niño → Indicadores). "
        "Responder só por e-mail não atualiza o índice. "
        "Não informar zero na ausência de dado.\n\n"
        "CIEVS / Secretaria-executiva — SES-MT\n"
    )
    return {
        "para": para or "(sem e-mail no cadastro da Portaria 0590)",
        "cc": "; ".join(EMAILS_CIEVS),
        "assunto": f"Plano El Niño — pendências de indicadores ({area})",
        "corpo": corpo,
        "area": area,
        "area_id": str(bloco.get("area_id") or ""),
    }


def rascunhos_email(relatorio: dict[str, Any] | None = None) -> list[dict[str, str]]:
    data = relatorio if relatorio is not None else relatorio_cobranca()
    quando = str(data.get("coletado_em") or "")
    return [rascunho_email_area(bloco, coletado_em=quando) for bloco in data.get("areas") or []]


def texto_rascunho(draft: dict[str, str]) -> str:
    return (
        f"Para: {draft.get('para')}\n"
        f"Cc: {draft.get('cc')}\n"
        f"Assunto: {draft.get('assunto')}\n\n"
        f"{draft.get('corpo') or ''}"
    )


def exportar_rascunhos(
    dest: Path | None = None,
    *,
    relatorio: dict[str, Any] | None = None,
) -> Path:
    from sisclima.core.config import ROOT

    pasta = dest or (ROOT / "docs" / "apresentacoes" / "cobranca_emails")
    pasta.mkdir(parents=True, exist_ok=True)
    data = relatorio if relatorio is not None else relatorio_cobranca()
    drafts = rascunhos_email(data)
    pack: list[str] = []
    for draft in drafts:
        slug = str(draft.get("area_id") or "area")
        texto = texto_rascunho(draft)
        (pasta / f"{slug}.txt").write_text(texto, encoding="utf-8")
        pack.append(texto)
    (pasta / "_todas_as_areas.txt").write_text("\n\n-----\n\n".join(pack), encoding="utf-8")
    return pasta


def csv_cobranca(relatorio: dict[str, Any] | None = None) -> str:
    data = relatorio if relatorio is not None else relatorio_cobranca()
    buf = io.StringIO()
    campos = [
        "id",
        "nome",
        "area",
        "modo",
        "classe",
        "prioridade",
        "onda",
        "acao",
        "indice",
        "sugestao",
        "emails",
    ]
    writer = csv.DictWriter(buf, fieldnames=campos, extrasaction="ignore")
    writer.writeheader()
    emails_area = {a["area_id"]: "; ".join(c["email"] for c in a.get("contatos") or []) for a in data.get("areas") or []}
    for item in data.get("itens") or []:
        writer.writerow(
            {
                "id": item.get("id"),
                "nome": item.get("nome"),
                "area": item.get("area"),
                "modo": item.get("modo"),
                "classe": item.get("classe"),
                "prioridade": item.get("prioridade"),
                "onda": item.get("onda") or "",
                "acao": item.get("acao"),
                "indice": "sim" if item.get("indice") else "nao",
                "sugestao": item.get("sugestao") or "",
                "emails": emails_area.get(str(item.get("area_id") or ""), ""),
            }
        )
    return buf.getvalue()


def resumo_cobranca(linhas: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rel = relatorio_cobranca(linhas)
    return {
        "n_pendencias": rel["n_pendencias"],
        "n_cobrar_area": rel["n_cobrar_area"],
        "n_aguardar_fonte": rel["n_aguardar_fonte"],
        "n_carga_defasada": rel["n_carga_defasada"],
        "n_documentais": rel["n_documentais"],
        "n_areas": rel["n_areas"],
        "areas_sem_focal": [a["area_id"] for a in rel["areas_sem_focal"]],
    }
