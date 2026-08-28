# -*- coding: utf-8 -*-
"""Estágio de ativação (decisão CIEVS/Comando) ≠ nível de risco (dado)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sisclima.core.db import db_conn, execute, fetchall
from sisclima.plano.escalonamento import ESTAGIOS, cadencia
from sisclima.plano.schema import garantir_schema

ESCOPOS = ("estado", "ers", "municipio")


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def estagio_atual(*, escopo: str = "estado", escopo_id: str = "") -> dict[str, Any]:
    garantir_schema()
    alvo = str(escopo or "estado")
    sid = str(escopo_id or "")
    with db_conn() as conn:
        rows = fetchall(
            conn,
            """
            SELECT estagio, escopo, escopo_id, observacao, autor_email, criado_em
            FROM plano_estagio_ativacao
            WHERE escopo = ? AND IFNULL(escopo_id, '') = ?
            ORDER BY id DESC
            """,
            (alvo, sid),
        )
    if not rows:
        return {
            "estagio": "verde",
            "escopo": alvo,
            "escopo_id": sid,
            "origem": "padrao",
            "observacao": "",
            "autor_email": "",
            "criado_em": "",
        }
    row = dict(rows[0])
    row["origem"] = "cievs"
    return row


def registrar_estagio(
    *,
    user: dict[str, Any],
    estagio: str,
    escopo: str = "estado",
    escopo_id: str = "",
    observacao: str = "",
) -> tuple[bool, str]:
    est = str(estagio or "").casefold()
    if est not in ESTAGIOS:
        return False, f"Estágio inválido: {estagio}. Use: {', '.join(ESTAGIOS)}."
    esc = str(escopo or "estado")
    if esc not in ESCOPOS:
        return False, f"Escopo inválido: {escopo}."
    email = str((user or {}).get("email") or "").strip().lower()
    if not email:
        return False, "Usuário sem e-mail."
    garantir_schema()
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO plano_estagio_ativacao
                (estagio, escopo, escopo_id, observacao, autor_email, criado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (est, esc, str(escopo_id or ""), observacao, email, _agora()),
        )
    return True, f"Estágio de ativação registrado: {est} ({esc})."


def nivel_risco_estadual() -> dict[str, Any]:
    """Sinal técnico (dado). Não grava estágio de ativação."""
    try:
        from sisclima.core.db import read_table, table_exists
        from sisclima.plano.conectores import _col

        if not table_exists("resumo_municipal_atual"):
            return {"nivel": None, "origem": "indisponivel", "n_municipios": 0}
        df = read_table("resumo_municipal_atual")
        col = _col(df, "nivel", "classe", "estagio_risco")
        if df is None or df.empty or not col:
            return {"nivel": None, "origem": "sem_coluna", "n_municipios": 0}
        s = df[col].astype(str).str.casefold()
        ordem = ["roxo", "vermelho", "laranja", "amarelo", "verde"]
        dominante = next((n for n in ordem if s.str.contains(n).any()), None)
        return {
            "nivel": dominante,
            "origem": "resumo_municipal_atual",
            "n_municipios": int(len(df)),
            "contagem": {n: int(s.str.contains(n).sum()) for n in ordem if int(s.str.contains(n).sum())},
        }
    except Exception:  # noqa: BLE001
        return {"nivel": None, "origem": "erro", "n_municipios": 0}


def quadro_dois_estados(indicador_id: str = "") -> dict[str, Any]:
    ativ = estagio_atual()
    risco = nivel_risco_estadual()
    return {
        "nivel_risco": risco.get("nivel"),
        "origem_risco": risco.get("origem"),
        "estagio_ativacao": ativ.get("estagio") or "verde",
        "origem_ativacao": ativ.get("origem"),
        "cadencia": cadencia(indicador_id, str(ativ.get("estagio") or "verde")) if indicador_id else "",
        "risco": risco,
        "ativacao": ativ,
    }
