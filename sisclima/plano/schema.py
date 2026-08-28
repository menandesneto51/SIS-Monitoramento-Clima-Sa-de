# -*- coding: utf-8 -*-
"""DDL do Plano El Niño — histórico append-only; SEI é o processo oficial."""
from __future__ import annotations

from sisclima.core.db import db_conn, execute, is_postgres

def _pk() -> str:
    return "SERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"


def ddl_statements() -> list[str]:
    pk = _pk()
    return [
        f"""
        CREATE TABLE IF NOT EXISTS plano (
            id {pk},
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            vigencia_inicio TEXT,
            vigencia_fim TEXT,
            fonte_xlsx TEXT,
            criado_em TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS eixo (
            id {pk},
            plano_codigo TEXT NOT NULL,
            codigo TEXT NOT NULL UNIQUE,
            nome TEXT NOT NULL,
            ordem INTEGER NOT NULL DEFAULT 0
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS meta (
            id {pk},
            codigo TEXT NOT NULL UNIQUE,
            eixo_codigo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            meta_numerica TEXT,
            unidade TEXT,
            prazo TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS acao (
            id {pk},
            codigo TEXT NOT NULL UNIQUE,
            meta_codigo TEXT,
            eixo_codigo TEXT NOT NULL,
            area_id TEXT NOT NULL,
            descricao TEXT NOT NULL,
            responsavel TEXT,
            prazo TEXT,
            prazo_iso TEXT,
            prioridade TEXT,
            status_inicial TEXT NOT NULL DEFAULT 'nao_iniciada',
            linha_fonte INTEGER
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS indicador (
            id {pk},
            codigo TEXT NOT NULL UNIQUE,
            codigo_fonte TEXT,
            acao_codigo TEXT,
            meta_codigo TEXT,
            eixo_codigo TEXT,
            area_id TEXT NOT NULL,
            nome TEXT NOT NULL,
            tipo TEXT NOT NULL,
            modo_atualizacao TEXT NOT NULL,
            formula TEXT,
            meta_numerica TEXT,
            unidade TEXT,
            direcao TEXT,
            fonte TEXT,
            periodicidade TEXT,
            entra_no_indice INTEGER NOT NULL DEFAULT 1
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS atualizacao (
            id {pk},
            alvo TEXT NOT NULL,
            alvo_codigo TEXT NOT NULL,
            status TEXT NOT NULL,
            valor TEXT,
            observacao TEXT,
            situacao_validacao TEXT NOT NULL DEFAULT 'informado',
            autor_email TEXT,
            autor_area_id TEXT,
            criado_em TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS evidencia (
            id {pk},
            atualizacao_id INTEGER,
            acao_codigo TEXT,
            tipo TEXT,
            documento TEXT,
            data TEXT,
            area TEXT,
            versao TEXT,
            responsavel_envio TEXT,
            uploaded_at TEXT NOT NULL,
            situacao TEXT NOT NULL DEFAULT 'enviada',
            link_sei TEXT,
            arquivo TEXT,
            observacao TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS validacao (
            id {pk},
            atualizacao_id INTEGER NOT NULL,
            decisao TEXT NOT NULL,
            validador_email TEXT,
            observacao TEXT,
            criado_em TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS decisao_sala (
            id {pk},
            criado_em TEXT NOT NULL,
            autor_email TEXT,
            tipo TEXT,
            titulo TEXT NOT NULL,
            texto TEXT NOT NULL,
            acao_codigo TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS alerta (
            id {pk},
            evento TEXT NOT NULL,
            alvo_codigo TEXT,
            canal TEXT NOT NULL DEFAULT 'email',
            payload TEXT,
            status TEXT NOT NULL DEFAULT 'pendente',
            criado_em TEXT NOT NULL,
            enviado_em TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS audit_log (
            id {pk},
            criado_em TEXT NOT NULL,
            ator_email TEXT,
            acao TEXT NOT NULL,
            entidade TEXT,
            entidade_id TEXT,
            detalhe TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS plano_vinculo (
            id {pk},
            email TEXT NOT NULL,
            perfil_plano TEXT NOT NULL,
            area_id TEXT,
            status TEXT NOT NULL DEFAULT 'ativo',
            criado_em TEXT NOT NULL,
            UNIQUE(email, perfil_plano, area_id)
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS plano_estagio_ativacao (
            id {pk},
            estagio TEXT NOT NULL,
            escopo TEXT NOT NULL DEFAULT 'estado',
            escopo_id TEXT,
            observacao TEXT,
            autor_email TEXT,
            criado_em TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS plano_pai_acao (
            id {pk},
            indicador_id TEXT NOT NULL,
            estagio TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'aberta',
            descricao TEXT NOT NULL,
            prazo TEXT,
            observacao TEXT,
            autor_email TEXT,
            criado_em TEXT NOT NULL
        )
        """,
    ]


def garantir_schema() -> None:
    with db_conn() as conn:
        for stmt in ddl_statements():
            execute(conn, stmt)
