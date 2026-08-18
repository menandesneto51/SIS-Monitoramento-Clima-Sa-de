# -*- coding: utf-8 -*-
"""Usuários do painel: cadastro, níveis e senha com PBKDF2 (sem texto puro)."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
from typing import Any

from sisclima.core.config import env
from sisclima.core.db import db_conn, execute, fetchall, fetchone, is_postgres
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

SESSION_KEY = "araras_user"
MODO_KEY = "araras_modo"
GATE_KEY = "araras_mostrar_acesso"

NIVEIS: list[tuple[str, str]] = [
    ("publico", "Público — painel aberto"),
    ("municipal", "Municipal — SMS / vigilância municipal"),
    ("regional", "Regional — CRS / escritório regional"),
    ("ses", "SES / CIEVS — painel interno completo"),
    ("admin", "Administração — cadastros e níveis"),
]
NIVEL_RANK = {k: i for i, (k, _lbl) in enumerate(NIVEIS)}
NIVEIS_AUTO = {"publico"}
NIVEIS_SOLICITaveis = ("publico", "municipal", "regional", "ses")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_email(email: str) -> str:
    return str(email or "").strip().lower()


def rotulo_nivel(nivel: str) -> str:
    for key, lbl in NIVEIS:
        if key == nivel:
            return lbl
    return nivel or "—"


def ensure_schema() -> None:
    pk = "SERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    sql = f"""
    CREATE TABLE IF NOT EXISTS usuarios_painel (
        id {pk},
        email TEXT NOT NULL UNIQUE,
        nome TEXT NOT NULL,
        instituicao TEXT,
        nivel_solicitado TEXT NOT NULL,
        nivel TEXT NOT NULL,
        status TEXT NOT NULL,
        regional_saude TEXT,
        municipio TEXT,
        cod_ibge TEXT,
        password_salt TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT,
        aprovado_em TEXT,
        aprovado_por TEXT
    )
    """
    with db_conn() as conn:
        execute(conn, sql)


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return salt.hex(), digest.hex()


def _verify(password: str, salt_hex: str, hash_hex: str) -> bool:
    if not salt_hex or not hash_hex:
        return False
    _, check = _hash_password(password, str(salt_hex))
    stored = str(hash_hex).strip().lower()
    got = str(check).strip().lower()
    if len(got) != len(stored):
        return False
    return hmac.compare_digest(got.encode("ascii"), stored.encode("ascii"))


def _row_public(row: Any | None) -> dict[str, Any] | None:
    if not row:
        return None
    d = dict(row)
    d.pop("password_hash", None)
    d.pop("password_salt", None)
    return d


def get_user_by_email(email: str) -> dict[str, Any] | None:
    ensure_schema()
    mail = _norm_email(email)
    if not mail:
        return None
    with db_conn() as conn:
        row = fetchone(conn, "SELECT * FROM usuarios_painel WHERE email = ?", (mail,))
    return dict(row) if row else None


def list_users() -> list[dict[str, Any]]:
    ensure_schema()
    with db_conn() as conn:
        rows = fetchall(conn, "SELECT * FROM usuarios_painel ORDER BY criado_em DESC")
    return [_row_public(r) or {} for r in rows]


def register_user(
    *,
    email: str,
    nome: str,
    password: str,
    instituicao: str = "",
    nivel_solicitado: str = "publico",
    regional_saude: str = "",
    municipio: str = "",
    cod_ibge: str = "",
) -> tuple[bool, str]:
    ensure_schema()
    mail = _norm_email(email)
    nome = str(nome or "").strip()
    if not _EMAIL_RE.match(mail):
        return False, "Informe um e-mail válido."
    if len(nome) < 3:
        return False, "Informe o nome completo."
    if len(password) < 8:
        return False, "A senha precisa ter pelo menos 8 caracteres."
    if nivel_solicitado not in NIVEL_RANK or nivel_solicitado == "admin":
        return False, "Nível solicitado inválido. Administração só é concedida internamente."
    if nivel_solicitado == "municipal" and not str(municipio or "").strip():
        return False, "Nível municipal exige o município de atuação."
    if nivel_solicitado == "regional" and not str(regional_saude or "").strip():
        return False, "Nível regional exige a Regional de Saúde."
    if get_user_by_email(mail):
        return False, "Já existe cadastro com este e-mail."

    auto = nivel_solicitado in NIVEIS_AUTO
    salt, hashed = _hash_password(password)
    now = _now()
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO usuarios_painel (
                email, nome, instituicao, nivel_solicitado, nivel, status,
                regional_saude, municipio, cod_ibge, password_salt, password_hash,
                criado_em, atualizado_em, aprovado_em, aprovado_por
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mail,
                nome,
                str(instituicao or "").strip(),
                nivel_solicitado,
                "publico" if not auto else nivel_solicitado,
                "ativo" if auto else "pendente",
                str(regional_saude or "").strip() or None,
                str(municipio or "").strip() or None,
                str(cod_ibge or "").strip() or None,
                salt,
                hashed,
                now,
                now,
                now if auto else None,
                "auto" if auto else None,
            ),
        )
    if auto:
        return True, "Cadastro ativo. Você já pode usar o painel público com esta conta."
    return True, "Cadastro recebido. O acesso restrito será liberado após aprovação do CIEVS/SES."


def authenticate(email: str, password: str) -> tuple[dict[str, Any] | None, str]:
    row = get_user_by_email(email)
    if not row:
        return None, "E-mail ou senha inválidos."
    if not _verify(password, str(row.get("password_salt") or ""), str(row.get("password_hash") or "")):
        log.warning("Falha de login no painel para %s", _norm_email(email))
        return None, "E-mail ou senha inválidos."
    status = str(row.get("status") or "")
    if status == "pendente":
        return None, "Cadastro ainda pendente de aprovação do CIEVS/SES."
    if status != "ativo":
        return None, "Esta conta está suspensa ou recusada."
    return _row_public(row), "ok"


def set_user_status(
    email: str,
    *,
    status: str,
    nivel: str | None = None,
    aprovado_por: str = "",
) -> tuple[bool, str]:
    if status not in {"pendente", "ativo", "recusado", "suspenso"}:
        return False, "Status inválido."
    row = get_user_by_email(email)
    if not row:
        return False, "Usuário não encontrado."
    novo_nivel = nivel if nivel in NIVEL_RANK else str(row.get("nivel") or "publico")
    now = _now()
    with db_conn() as conn:
        execute(
            conn,
            """
            UPDATE usuarios_painel
            SET status = ?, nivel = ?, atualizado_em = ?, aprovado_em = ?, aprovado_por = ?
            WHERE email = ?
            """,
            (status, novo_nivel, now, now if status == "ativo" else row.get("aprovado_em"), aprovado_por or None, _norm_email(email)),
        )
    return True, f"{email}: {status} / {novo_nivel}"


def current_user(session: dict | None = None) -> dict[str, Any] | None:
    if session is None:
        try:
            import streamlit as st

            session = st.session_state
        except Exception:
            return None
    user = session.get(SESSION_KEY) if session is not None else None
    return user if isinstance(user, dict) and user.get("email") else None


def login_to_session(user: dict[str, Any], session: dict) -> None:
    session[SESSION_KEY] = {
        "email": user.get("email"),
        "nome": user.get("nome"),
        "nivel": user.get("nivel"),
        "status": user.get("status"),
        "regional_saude": user.get("regional_saude"),
        "municipio": user.get("municipio"),
        "cod_ibge": user.get("cod_ibge"),
        "instituicao": user.get("instituicao"),
    }
    session[GATE_KEY] = False
    if is_interno(session[SESSION_KEY]):
        session[MODO_KEY] = "interno"
    else:
        session[MODO_KEY] = "publico"


def logout_session(session: dict) -> None:
    session.pop(SESSION_KEY, None)
    session[MODO_KEY] = "publico"
    session[GATE_KEY] = False


def is_interno(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    return NIVEL_RANK.get(str(user.get("nivel") or ""), 0) >= NIVEL_RANK["municipal"] and str(user.get("status") or "ativo") == "ativo"


def is_admin(user: dict[str, Any] | None) -> bool:
    return bool(user) and str(user.get("nivel") or "") == "admin" and str(user.get("status") or "") == "ativo"


def modo_publico(session: dict | None = None) -> bool:
    user = current_user(session)
    if session is None:
        try:
            import streamlit as st

            session = st.session_state
        except Exception:
            return True
    if not is_interno(user):
        return True
    modo = str((session or {}).get(MODO_KEY) or "interno")
    return modo != "interno"


def bootstrap_admin() -> None:
    """Cria o primeiro administrador se ARARAS_ADMIN_EMAIL e ARARAS_ADMIN_PASSWORD existirem."""
    ensure_schema()
    email = _norm_email(env("ARARAS_ADMIN_EMAIL", "") or "")
    password = env("ARARAS_ADMIN_PASSWORD", "") or ""
    nome = (env("ARARAS_ADMIN_NOME", "") or "Administrador CIEVS").strip()
    if not email or not password:
        return
    existing = get_user_by_email(email)
    if existing:
        return
    salt, hashed = _hash_password(password)
    now = _now()
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO usuarios_painel (
                email, nome, instituicao, nivel_solicitado, nivel, status,
                regional_saude, municipio, cod_ibge, password_salt, password_hash,
                criado_em, atualizado_em, aprovado_em, aprovado_por
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (email, nome, "SES-MT / CIEVS-MT", "admin", "admin", "ativo", None, None, None, salt, hashed, now, now, now, "env"),
        )
    log.info("Administrador do painel criado via ambiente: %s", email)
