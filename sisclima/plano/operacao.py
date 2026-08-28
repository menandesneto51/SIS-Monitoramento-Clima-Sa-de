# -*- coding: utf-8 -*-
"""Regras de % , histórico append-only e resumo da Sala (sem inventar números)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sisclima.core.db import db_conn, execute, fetchall
from sisclima.plano.acesso import pode_editar_area, pode_validar
from sisclima.plano.catalogo import acao_por_id, carregar_catalogo, indicadores_do_indice
from sisclima.plano.constants import (
    STATUS_ACAO_SET,
    STATUS_COR,
    SITUACAO_VALIDACAO_SET,
    TRANSICOES_STATUS,
    TRANSICOES_VALIDACAO,
)
from sisclima.plano.schema import garantir_schema


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def status_cor(status: str) -> str:
    return STATUS_COR.get(str(status or "").strip(), "#6b7280")


def percentual_implementacao(concluidos: int, total: int) -> float:
    """15/20 = 75.0. Não arredonda para 100 sem o denominador completo."""
    if total <= 0:
        return 0.0
    return round(100.0 * float(concluidos) / float(total), 2)


def percentual_oficial(*, concluidos_validados: int, total: int, pendente_validacao: int) -> dict[str, Any]:
    """100% só é oficial quando não há item do índice pendente de validação."""
    bruto = percentual_implementacao(concluidos_validados, total)
    oficial = bool(total > 0 and pendente_validacao == 0 and concluidos_validados == total)
    return {
        "percentual": bruto,
        "oficial": oficial,
        "motivo": (
            "Índice oficial: todos os itens do denominador concluídos e validados."
            if oficial
            else "Percentual operacional; 100% oficial exige validação CIEVS de todos os itens do índice."
        ),
    }


def _ultima_atualizacao(alvo: str, alvo_codigo: str) -> dict[str, Any] | None:
    garantir_schema()
    with db_conn() as conn:
        rows = fetchall(
            conn,
            """
            SELECT * FROM atualizacao
            WHERE alvo = ? AND alvo_codigo = ?
            ORDER BY id DESC
            """,
            (alvo, alvo_codigo),
        )
    return dict(rows[0]) if rows else None


def registrar_atualizacao(
    *,
    user: dict[str, Any],
    acao_codigo: str,
    status: str,
    valor: str = "",
    observacao: str = "",
    alvo: str = "acao",
    alvo_codigo: str | None = None,
) -> tuple[bool, str, int | None]:
    """Append-only. Nunca UPDATE na linha anterior."""
    garantir_schema()
    acao = acao_por_id(acao_codigo)
    if not acao:
        return False, "Ação não encontrada no catálogo.", None
    area_id = str(acao.get("area_id") or "")
    if not pode_editar_area(user, area_id):
        return False, "Área isolada: este perfil não atualiza outra área do Plano.", None
    novo = str(status or "").strip()
    if novo not in STATUS_ACAO_SET:
        return False, "Status inválido.", None
    codigo_alvo = str(alvo_codigo or acao_codigo)
    anterior = _ultima_atualizacao(alvo, codigo_alvo)
    atual = str((anterior or {}).get("status") or acao.get("status_inicial") or "nao_iniciada")
    # Ação: em_andamento não se repete. Indicador: a coleta diária reanexa
    # medições (mesmo status) — senão a 2ª corrida trava.
    if alvo != "indicador" and anterior and novo not in TRANSICOES_STATUS.get(atual, frozenset()):
        return False, f"Transição {atual} → {novo} não permitida.", None
    situacao = "informado"
    if novo == "em_validacao":
        situacao = "em_validacao"
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO atualizacao (
                alvo, alvo_codigo, status, valor, observacao, situacao_validacao,
                autor_email, autor_area_id, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alvo,
                codigo_alvo,
                novo,
                valor or None,
                observacao or None,
                situacao,
                str(user.get("email") or ""),
                str(user.get("area_id") or area_id),
                _now(),
            ),
        )
        execute(
            conn,
            """
            INSERT INTO audit_log (criado_em, ator_email, acao, entidade, entidade_id, detalhe)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _now(),
                str(user.get("email") or ""),
                "append_atualizacao",
                alvo,
                codigo_alvo,
                novo,
            ),
        )
        rows = fetchall(
            conn,
            "SELECT id FROM atualizacao WHERE alvo = ? AND alvo_codigo = ? ORDER BY id DESC",
            (alvo, codigo_alvo),
        )
    novo_id = int(rows[0]["id"]) if rows else None
    return True, "Atualização registrada (histórico preservado).", novo_id


def registrar_evidencia(
    *,
    user: dict[str, Any],
    acao_codigo: str,
    atualizacao_id: int | None,
    tipo: str,
    documento: str = "",
    data: str = "",
    versao: str = "1",
    link_sei: str = "",
    arquivo: str = "",
    observacao: str = "",
) -> tuple[bool, str]:
    acao = acao_por_id(acao_codigo)
    if not acao:
        return False, "Ação não encontrada."
    if not pode_editar_area(user, str(acao.get("area_id") or "")):
        return False, "Área isolada: evidência de outra área não pode ser enviada."
    if not str(link_sei or "").strip() and not str(arquivo or "").strip():
        return False, "Informe o link SEI (oficial) ou anexe a cópia PDF."
    garantir_schema()
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO evidencia (
                atualizacao_id, acao_codigo, tipo, documento, data, area, versao,
                responsavel_envio, uploaded_at, situacao, link_sei, arquivo, observacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                atualizacao_id,
                acao_codigo,
                tipo or "documento",
                documento or None,
                data or None,
                str(acao.get("area_id") or ""),
                versao or "1",
                str(user.get("email") or ""),
                _now(),
                "enviada",
                link_sei or None,
                arquivo or None,
                observacao or None,
            ),
        )
    return True, "Evidência anexada. O SEI permanece o processo administrativo oficial."


def validar_atualizacao(
    *,
    user: dict[str, Any],
    atualizacao_id: int,
    decisao: str,
    observacao: str = "",
) -> tuple[bool, str]:
    if not pode_validar(user):
        return False, "Somente secretaria-executiva CIEVS ou admin_araras valida."
    dest = str(decisao or "").strip()
    if dest not in {"validado", "rejeitado"}:
        return False, "Decisão deve ser validado ou rejeitado."
    garantir_schema()
    with db_conn() as conn:
        rows = fetchall(conn, "SELECT * FROM atualizacao WHERE id = ?", (atualizacao_id,))
        if not rows:
            return False, "Atualização não encontrada."
        row = dict(rows[0])
        atual = str(row.get("situacao_validacao") or "informado")
        if atual == "informado":
            atual = "em_validacao"
        if dest not in TRANSICOES_VALIDACAO.get(atual, frozenset()) and dest not in TRANSICOES_VALIDACAO.get(
            "em_validacao", frozenset()
        ):
            return False, f"Validação {atual} → {dest} não permitida."
        if dest not in SITUACAO_VALIDACAO_SET:
            return False, "Situação de validação inválida."
        execute(
            conn,
            """
            INSERT INTO validacao (atualizacao_id, decisao, validador_email, observacao, criado_em)
            VALUES (?, ?, ?, ?, ?)
            """,
            (atualizacao_id, dest, str(user.get("email") or ""), observacao or None, _now()),
        )
        novo_status = str(row.get("status") or "em_validacao")
        if dest == "rejeitado":
            novo_status = "em_andamento"
        elif dest == "validado" and novo_status == "em_validacao":
            novo_status = "concluida"
        execute(
            conn,
            """
            INSERT INTO atualizacao (
                alvo, alvo_codigo, status, valor, observacao, situacao_validacao,
                autor_email, autor_area_id, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row.get("alvo"),
                row.get("alvo_codigo"),
                novo_status,
                row.get("valor"),
                f"validacao:{dest}. {observacao}".strip(),
                dest,
                str(user.get("email") or ""),
                str(user.get("area_id") or ""),
                _now(),
            ),
        )
    return True, f"Validação registrada: {dest}."


def resumo_sala() -> dict[str, Any]:
    """Números só do catálogo + atualizações reais. Sem preenchimento, tudo zero."""
    garantir_schema()
    cat = carregar_catalogo()
    acoes = list(cat.get("acoes") or [])
    eixos = list(cat.get("eixos") or [])
    indicadores = list(cat.get("indicadores") or [])
    indice = indicadores_do_indice(cat)

    with db_conn() as conn:
        atualizacoes = [dict(r) for r in fetchall(conn, "SELECT * FROM atualizacao ORDER BY id ASC")]

    ultimo: dict[tuple[str, str], dict[str, Any]] = {}
    for row in atualizacoes:
        ultimo[(str(row.get("alvo")), str(row.get("alvo_codigo")))] = row

    por_status: Counter[str] = Counter()
    por_eixo: dict[str, dict[str, int]] = {}
    pendentes = 0
    vencidas = 0
    concluidas = 0
    concluidas_validadas = 0
    pendente_validacao = 0
    hoje = datetime.now().date()

    for acao in acoes:
        codigo = str(acao.get("id") or acao.get("codigo") or "")
        eixo = str(acao.get("eixo_codigo") or acao.get("eixo") or "—")
        row = ultimo.get(("acao", codigo))
        status = str((row or {}).get("status") or acao.get("status_inicial") or "nao_iniciada")
        if status not in STATUS_ACAO_SET:
            status = "nao_iniciada"
        por_status[status] += 1
        bucket = por_eixo.setdefault(eixo, {"total": 0, "concluida": 0})
        bucket["total"] += 1
        if status in {"nao_iniciada", "em_andamento", "em_validacao"}:
            pendentes += 1
        if status == "concluida":
            concluidas += 1
            bucket["concluida"] += 1
            if str((row or {}).get("situacao_validacao") or "") == "validado":
                concluidas_validadas += 1
            else:
                pendente_validacao += 1
        if status == "em_validacao":
            pendente_validacao += 1
        prazo_iso = str(acao.get("prazo_iso") or "")[:10]
        if prazo_iso and status not in {"concluida", "nao_aplicavel"}:
            try:
                if datetime.strptime(prazo_iso, "%Y-%m-%d").date() < hoje:
                    vencidas += 1
            except ValueError:
                pass

    denominador = sum(1 for a in acoes if str(a.get("status_inicial") or "nao_iniciada") != "nao_aplicavel")
    if not denominador:
        denominador = len(acoes)
    oficial = percentual_oficial(
        concluidos_validados=concluidas_validadas,
        total=denominador,
        pendente_validacao=pendente_validacao + max(0, denominador - concluidas_validadas),
    )
    return {
        "n_eixos": len(eixos),
        "n_metas": len(cat.get("metas") or []),
        "n_acoes": len(acoes),
        "n_indicadores": len(indicadores),
        "n_indicadores_indice": len(indice),
        "por_status": dict(por_status),
        "por_eixo": por_eixo,
        "pendentes": pendentes,
        "vencidas": vencidas,
        "percentual_bruto": percentual_implementacao(concluidas, denominador) if denominador else 0.0,
        "percentual_oficial": oficial["percentual"] if oficial["oficial"] else percentual_implementacao(concluidas_validadas, denominador),
        "indice_oficial": oficial["oficial"],
        "atualizacoes": len(atualizacoes),
        "fonte": str((cat.get("plano") or {}).get("fonte_xlsx") or ""),
    }


validar_atualizacao = validar_atualizacao
