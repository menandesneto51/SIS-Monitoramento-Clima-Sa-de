# -*- coding: utf-8 -*-
"""Notificação de eventos em saúde (canal CIEVS) — complementar ao SINAN.

Ficha territorial/operacional (rumor, cluster, impacto climático).
Não substitui notificação individual de agravo.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from sisclima.core.db import db_conn, execute, fetchall, fetchone, is_postgres

TIPOS: list[tuple[str, str]] = [
    ("calor", "Calor extremo / desidratação"),
    ("fumaca_ar", "Fumaça / qualidade do ar"),
    ("estiagem_agua", "Estiagem / abastecimento de água"),
    ("fogo_queimada", "Incêndio / queimada"),
    ("inundacao", "Inundação / alagamento"),
    ("surto_agravo", "Surto / aumento de agravo"),
    ("rumor", "Rumor / sinal precoce"),
    ("outro", "Outro evento de saúde pública"),
]
TIPO_LABEL = {k: lbl for k, lbl in TIPOS}

SITUACOES: list[tuple[str, str]] = [
    ("rumor", "Rumor"),
    ("em_verificacao", "Em verificação"),
    ("confirmado", "Confirmado"),
    ("encerrado", "Encerrado"),
    ("descartado", "Descartado"),
]
SITUACAO_LABEL = {k: lbl for k, lbl in SITUACOES}

NIVEIS_NOTIFICAR = {"municipal", "regional", "ses", "admin"}
NIVEIS_TRIAR = {"ses", "admin"}
TABLE = "eventos_saude_notificacao"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pk() -> str:
    return "SERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"


def ensure_schema() -> None:
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TABLE} (
        id {_pk()},
        uid TEXT NOT NULL UNIQUE,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL,
        municipio TEXT NOT NULL,
        cod_ibge TEXT,
        regional_saude TEXT,
        tipo TEXT NOT NULL,
        situacao TEXT NOT NULL,
        data_evento TEXT NOT NULL,
        descricao TEXT NOT NULL,
        n_afetados_aprox INTEGER,
        territorio_tradicional TEXT,
        cobrade TEXT,
        link_anexo TEXT,
        notificado_por_email TEXT,
        notificado_por_nome TEXT,
        notificado_por_nivel TEXT,
        triado_em TEXT,
        triado_por_email TEXT,
        triagem_nota TEXT
    )
    """
    with db_conn() as conn:
        execute(conn, sql)


def pode_notificar(user: dict[str, Any] | None) -> bool:
    if not user or str(user.get("status") or "ativo") != "ativo":
        return False
    return str(user.get("nivel") or "") in NIVEIS_NOTIFICAR


def pode_triar(user: dict[str, Any] | None) -> bool:
    if not user or str(user.get("status") or "ativo") != "ativo":
        return False
    return str(user.get("nivel") or "") in NIVEIS_TRIAR


def recorte_eventos(user: dict[str, Any] | None) -> dict[str, Any]:
    out: dict[str, Any] = {"municipio": "", "regional_saude": "", "lock": False}
    if not user:
        return out
    nivel = str(user.get("nivel") or "")
    if nivel == "municipal":
        out.update(municipio=str(user.get("municipio") or "").strip(), lock=True)
    elif nivel == "regional":
        out.update(regional_saude=str(user.get("regional_saude") or "").strip(), lock=True)
    return out


def criar_evento(
    *,
    user: dict[str, Any],
    municipio: str,
    tipo: str,
    descricao: str,
    data_evento: str,
    cod_ibge: str = "",
    regional_saude: str = "",
    n_afetados_aprox: int | None = None,
    territorio_tradicional: str = "",
    cobrade: str = "",
    link_anexo: str = "",
) -> tuple[bool, str, str]:
    if not pode_notificar(user):
        return False, "Conta sem permissão para notificar.", ""
    mun = str(municipio or "").strip()
    tipo_k = str(tipo or "").strip()
    desc = str(descricao or "").strip()
    if not mun:
        return False, "Informe o município.", ""
    if tipo_k not in TIPO_LABEL:
        return False, "Tipo de evento inválido.", ""
    if len(desc) < 20:
        return False, "Descreva o evento com pelo menos 20 caracteres (sem dado identificável de paciente).", ""
    rec = recorte_eventos(user)
    if rec.get("municipio") and mun.casefold() != str(rec["municipio"]).casefold():
        return False, "Conta municipal só notifica o próprio município.", ""
    if rec.get("regional_saude") and regional_saude and regional_saude.casefold() != str(rec["regional_saude"]).casefold():
        return False, "Conta regional só notifica municípios da própria CRS.", ""
    ensure_schema()
    uid = uuid.uuid4().hex[:12]
    now = _now()
    n_af = None if n_afetados_aprox is None else int(n_afetados_aprox)
    if n_af is not None and n_af < 0:
        n_af = None
    with db_conn() as conn:
        execute(
            conn,
            f"""
            INSERT INTO {TABLE} (
                uid, criado_em, atualizado_em, municipio, cod_ibge, regional_saude,
                tipo, situacao, data_evento, descricao, n_afetados_aprox,
                territorio_tradicional, cobrade, link_anexo,
                notificado_por_email, notificado_por_nome, notificado_por_nivel
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uid, now, now, mun,
                str(cod_ibge or "").strip() or None,
                str(regional_saude or "").strip() or None,
                tipo_k, "rumor", str(data_evento or now[:10])[:10], desc, n_af,
                str(territorio_tradicional or "").strip() or None,
                str(cobrade or "").strip() or None,
                str(link_anexo or "").strip() or None,
                str(user.get("email") or ""),
                str(user.get("nome") or ""),
                str(user.get("nivel") or ""),
            ),
        )
    return True, "Evento registrado para triagem do CIEVS.", uid


def triar_evento(
    *,
    user: dict[str, Any],
    uid: str,
    situacao: str,
    nota: str = "",
) -> tuple[bool, str]:
    if not pode_triar(user):
        return False, "Somente SES/CIEVS pode triar."
    sit = str(situacao or "").strip()
    if sit not in SITUACAO_LABEL:
        return False, "Situação inválida."
    ensure_schema()
    now = _now()
    with db_conn() as conn:
        row = fetchone(conn, f"SELECT uid FROM {TABLE} WHERE uid = ?", (uid,))
        if not row:
            return False, "Evento não encontrado."
        execute(
            conn,
            f"""
            UPDATE {TABLE}
            SET situacao = ?, atualizado_em = ?, triado_em = ?,
                triado_por_email = ?, triagem_nota = ?
            WHERE uid = ?
            """,
            (sit, now, now, str(user.get("email") or ""), str(nota or "").strip() or None, uid),
        )
    return True, f"Situação atualizada para {SITUACAO_LABEL[sit]}."


def listar_eventos(user: dict[str, Any] | None, *, limite: int = 200) -> pd.DataFrame:
    ensure_schema()
    rec = recorte_eventos(user)
    sql = f"SELECT * FROM {TABLE}"
    params: list[Any] = []
    clauses: list[str] = []
    if rec.get("municipio"):
        clauses.append("LOWER(municipio) = ?")
        params.append(str(rec["municipio"]).casefold())
    elif rec.get("regional_saude"):
        clauses.append("LOWER(COALESCE(regional_saude, '')) = ?")
        params.append(str(rec["regional_saude"]).casefold())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY criado_em DESC"
    with db_conn() as conn:
        rows = fetchall(conn, sql, tuple(params) if params else None)
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return df
    if "tipo" in df.columns:
        df["tipo_rotulo"] = df["tipo"].map(TIPO_LABEL).fillna(df["tipo"])
    if "situacao" in df.columns:
        df["situacao_rotulo"] = df["situacao"].map(SITUACAO_LABEL).fillna(df["situacao"])
    return df.head(int(limite))


def resumo_fila(df: pd.DataFrame) -> dict[str, int]:
    if df is None or df.empty or "situacao" not in df.columns:
        return {k: 0 for k, _ in SITUACOES}
    vc = df["situacao"].astype(str).value_counts()
    return {k: int(vc.get(k, 0)) for k, _ in SITUACOES}
