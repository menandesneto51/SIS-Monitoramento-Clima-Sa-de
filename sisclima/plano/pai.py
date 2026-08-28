# -*- coding: utf-8 -*-
"""PAI — Plano de Ação do Incidente. Só a partir do Amarelo.

Rascunho rastreável; não dispara e-mail. Sem inventar valor de indicador.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sisclima.core.db import db_conn, execute, fetchall
from sisclima.plano.ativacao import estagio_atual
from sisclima.plano.catalogo import indicador_por_id
from sisclima.plano.escalonamento import ESTAGIOS, item_adequacao, item_escalonamento
from sisclima.plano.schema import garantir_schema

ESTAGIOS_PAI = frozenset({"amarelo", "laranja", "vermelho", "roxo"})
STATUS_PAI = ("aberta", "em_andamento", "concluida", "cancelada")


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pai_aplicavel(estagio: str | None = None) -> bool:
    est = str(estagio or (estagio_atual().get("estagio") or "verde")).casefold()
    return est in ESTAGIOS_PAI


def pode_abrir_pai(indicador_id: str, *, estagio: str | None = None) -> tuple[bool, str]:
    if not pai_aplicavel(estagio):
        return False, "PAI só a partir do estágio Amarelo."
    esc = item_escalonamento(indicador_id)
    if str(esc.get("classe_emergencia") or "") == "C":
        return False, "Gate de prontidão não abre ação de PAI de crise."
    if str(esc.get("classe_emergencia") or "") == "D":
        can = str(esc.get("id_canonico") or "")
        return False, f"Usar o indicador canônico {can or 'do catálogo'}."
    adq = item_adequacao(indicador_id)
    if str(adq.get("papel") or "") == "preparacao":
        return False, "Gate de prontidão não abre ação de PAI de crise."
    if str(adq.get("papel") or "") == "alias":
        return False, f"Usar o indicador canônico {adq.get('id_canonico') or 'do catálogo'}."
    ind = indicador_por_id(indicador_id)
    if not ind:
        return False, "Indicador não encontrado."
    return True, "ok"


def registrar_acao_pai(
    *,
    user: dict[str, Any],
    indicador_id: str,
    descricao: str,
    prazo: str = "",
    observacao: str = "",
) -> tuple[bool, str, int | None]:
    est = str(estagio_atual().get("estagio") or "verde")
    ok, msg = pode_abrir_pai(indicador_id, estagio=est)
    if not ok:
        return False, msg, None
    email = str((user or {}).get("email") or "").strip().lower()
    if not email:
        return False, "Usuário sem e-mail.", None
    texto = str(descricao or "").strip()
    if not texto:
        return False, "Informe a ação do PAI.", None
    garantir_schema()
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO plano_pai_acao
                (indicador_id, estagio, status, descricao, prazo, observacao, autor_email, criado_em)
            VALUES (?, ?, 'aberta', ?, ?, ?, ?, ?)
            """,
            (indicador_id, est, texto, prazo, observacao, email, _agora()),
        )
        rows = fetchall(conn, "SELECT id FROM plano_pai_acao ORDER BY id DESC")
    novo = int(rows[0]["id"]) if rows else None
    return True, f"Ação de PAI aberta para {indicador_id} no estágio {est}.", novo


def listar_acoes_pai(*, indicador_id: str | None = None, so_abertas: bool = True) -> list[dict[str, Any]]:
    garantir_schema()
    sql = "SELECT * FROM plano_pai_acao"
    params: list[Any] = []
    wh: list[str] = []
    if indicador_id:
        wh.append("indicador_id = ?")
        params.append(indicador_id)
    if so_abertas:
        wh.append("status IN ('aberta', 'em_andamento')")
    if wh:
        sql += " WHERE " + " AND ".join(wh)
    sql += " ORDER BY id DESC"
    with db_conn() as conn:
        rows = fetchall(conn, sql, tuple(params) if params else None)
    return [dict(r) for r in rows]


def indicadores_cievs_sala() -> list[dict[str, Any]]:
    from sisclima.plano.escalonamento import indicadores_cievs

    return indicadores_cievs()
