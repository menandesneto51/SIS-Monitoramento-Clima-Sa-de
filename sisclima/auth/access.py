# -*- coding: utf-8 -*-
"""Backend de controle de acesso: usuários, papéis, aprovação e recorte territorial.

Papéis (níveis):
- publico    — ativo na hora; só o painel público aberto (não exige conta).
- municipal  — SMS; exige município; aguarda aprovação de um admin.
- regional    — CRS; exige a regional; aguarda aprovação.
- ses        — SES/CIEVS; painel interno completo; aguarda aprovação.
- admin      — gestão de cadastros/níveis; NÃO pode ser autoatribuído.

Sem dependências externas: hash PBKDF2-SHA256 da biblioteca padrão.
O primeiro admin é criado a partir do .env (ARARAS_ADMIN_EMAIL/PASSWORD/NOME).
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from sisclima.core.config import env
from sisclima.core.db import db_conn, execute, fetchall, fetchone, is_postgres, table_exists
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

TABELA = "araras_usuarios"

PAPEIS = ["publico", "municipal", "regional", "ses", "admin"]
PAPEIS_INTERNOS = {"municipal", "regional", "ses", "admin"}
PAPEIS_APROVACAO = {"municipal", "regional", "ses"}  # ficam pendentes até aprovação
PAPEL_LABEL = {
    "publico": "Público",
    "municipal": "Municipal (SMS)",
    "regional": "Regional (CRS)",
    "ses": "SES / CIEVS",
    "admin": "Administrador",
}

_PBKDF2_ITER = 200_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _norm_email(email: str | None) -> str:
    return str(email or "").strip().lower()


# --------------------------------------------------------------------------- #
# Hash de senha (PBKDF2-SHA256, stdlib)
# --------------------------------------------------------------------------- #
def hash_senha(senha: str, iteracoes: int = _PBKDF2_ITER) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", str(senha).encode("utf-8"), bytes.fromhex(salt), iteracoes)
    return f"pbkdf2_sha256${iteracoes}${salt}${dk.hex()}"


def verificar_senha(senha: str, armazenado: str | None) -> bool:
    if not armazenado:
        return False
    try:
        algo, it, salt, h = str(armazenado).split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", str(senha).encode("utf-8"), bytes.fromhex(salt), int(it))
        return secrets.compare_digest(dk.hex(), h)
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Esquema
# --------------------------------------------------------------------------- #
def ensure_schema() -> None:
    """Cria a tabela de usuários se ainda não existir (SQLite ou PostgreSQL)."""
    if is_postgres():
        ddl = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    nome TEXT,
    papel TEXT NOT NULL,
    municipio TEXT,
    cod_ibge TEXT,
    regional TEXT,
    status TEXT NOT NULL,
    criado_em TEXT,
    atualizado_em TEXT,
    aprovado_por TEXT,
    aprovado_em TEXT,
    observacao TEXT
)
"""
    else:
        ddl = f"""
CREATE TABLE IF NOT EXISTS {TABELA} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    senha_hash TEXT NOT NULL,
    nome TEXT,
    papel TEXT NOT NULL,
    municipio TEXT,
    cod_ibge TEXT,
    regional TEXT,
    status TEXT NOT NULL,
    criado_em TEXT,
    atualizado_em TEXT,
    aprovado_por TEXT,
    aprovado_em TEXT,
    observacao TEXT
)
"""
    with db_conn() as conn:
        execute(conn, ddl)


def _row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


# --------------------------------------------------------------------------- #
# Consultas
# --------------------------------------------------------------------------- #
def get_user_by_email(email: str) -> dict | None:
    if not table_exists(TABELA):
        return None
    with db_conn() as conn:
        row = fetchone(conn, f"SELECT * FROM {TABELA} WHERE email = ?", (_norm_email(email),))
    return _row_to_dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    if not table_exists(TABELA):
        return None
    with db_conn() as conn:
        row = fetchone(conn, f"SELECT * FROM {TABELA} WHERE id = ?", (int(user_id),))
    return _row_to_dict(row)


def list_users(status: str | None = None) -> list[dict]:
    if not table_exists(TABELA):
        return []
    with db_conn() as conn:
        if status:
            rows = fetchall(conn, f"SELECT * FROM {TABELA} WHERE status = ? ORDER BY criado_em DESC", (status,))
        else:
            rows = fetchall(conn, f"SELECT * FROM {TABELA} ORDER BY criado_em DESC")
    return [dict(r) for r in rows]


def count_pendentes() -> int:
    if not table_exists(TABELA):
        return 0
    with db_conn() as conn:
        row = fetchone(conn, f"SELECT COUNT(*) AS n FROM {TABELA} WHERE status = ?", ("pendente",))
    try:
        return int(dict(row).get("n", 0)) if row is not None else 0
    except Exception:
        return 0


# --------------------------------------------------------------------------- #
# Criação / autenticação
# --------------------------------------------------------------------------- #
def criar_usuario(
    email: str,
    senha: str,
    nome: str,
    papel: str,
    municipio: str | None = None,
    cod_ibge: str | None = None,
    regional: str | None = None,
) -> dict:
    """Cria um usuário. Papéis internos ficam 'pendente'; 'publico' já entra 'ativo'.

    'admin' NÃO pode ser autoatribuído por este fluxo (bloqueado).
    """
    ensure_schema()
    email = _norm_email(email)
    if not email or "@" not in email:
        raise ValueError("Informe um e-mail válido.")
    if not senha or len(str(senha)) < 6:
        raise ValueError("A senha deve ter ao menos 6 caracteres.")
    if papel not in PAPEIS:
        raise ValueError("Nível inválido.")
    if papel == "admin":
        raise ValueError("Nível Admin não pode ser autoatribuído.")
    if papel == "municipal" and not (municipio or cod_ibge):
        raise ValueError("Nível municipal exige o município.")
    if papel == "regional" and not regional:
        raise ValueError("Nível regional exige a regional.")
    if get_user_by_email(email) is not None:
        raise ValueError("Já existe um cadastro com este e-mail.")

    status = "ativo" if papel == "publico" else "pendente"
    now = _now()
    with db_conn() as conn:
        execute(
            conn,
            f"""INSERT INTO {TABELA}
                (email, senha_hash, nome, papel, municipio, cod_ibge, regional, status, criado_em, atualizado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                email,
                hash_senha(senha),
                str(nome or "").strip() or email,
                papel,
                municipio,
                cod_ibge,
                regional,
                status,
                now,
                now,
            ),
        )
    log.info("Novo cadastro de acesso: %s (%s/%s)", email, papel, status)
    return get_user_by_email(email)


def autenticar(email: str, senha: str) -> dict | None:
    user = get_user_by_email(email)
    if user is None:
        return None
    if not verificar_senha(senha, user.get("senha_hash")):
        return None
    return user


# --------------------------------------------------------------------------- #
# Gestão (admin)
# --------------------------------------------------------------------------- #
def definir_papel_status(
    user_id: int,
    papel: str,
    status: str,
    municipio: str | None = None,
    cod_ibge: str | None = None,
    regional: str | None = None,
    admin_email: str | None = None,
) -> None:
    if papel not in PAPEIS:
        raise ValueError("Nível inválido.")
    if status not in {"pendente", "ativo", "recusado"}:
        raise ValueError("Status inválido.")
    now = _now()
    with db_conn() as conn:
        execute(
            conn,
            f"""UPDATE {TABELA}
                SET papel = ?, status = ?, municipio = ?, cod_ibge = ?, regional = ?,
                    aprovado_por = ?, aprovado_em = ?, atualizado_em = ?
                WHERE id = ?""",
            (papel, status, municipio, cod_ibge, regional, admin_email, now, now, int(user_id)),
        )
    log.info("Acesso atualizado por %s: id=%s papel=%s status=%s", admin_email, user_id, papel, status)


def aprovar_usuario(
    user_id: int,
    papel: str,
    municipio: str | None = None,
    cod_ibge: str | None = None,
    regional: str | None = None,
    admin_email: str | None = None,
) -> None:
    definir_papel_status(
        user_id, papel, "ativo", municipio=municipio, cod_ibge=cod_ibge, regional=regional, admin_email=admin_email
    )


def recusar_usuario(user_id: int, admin_email: str | None = None) -> None:
    user = get_user_by_id(user_id) or {}
    definir_papel_status(
        user_id,
        user.get("papel", "publico"),
        "recusado",
        municipio=user.get("municipio"),
        cod_ibge=user.get("cod_ibge"),
        regional=user.get("regional"),
        admin_email=admin_email,
    )


# --------------------------------------------------------------------------- #
# Bootstrap do primeiro admin via .env
# --------------------------------------------------------------------------- #
def bootstrap_admin_from_env() -> None:
    """Cria/garante o admin inicial a partir de ARARAS_ADMIN_EMAIL/PASSWORD/NOME."""
    email = _norm_email(env("ARARAS_ADMIN_EMAIL"))
    senha = env("ARARAS_ADMIN_PASSWORD")
    nome = env("ARARAS_ADMIN_NOME") or "Administrador CIEVS"
    if not email or not senha:
        return
    ensure_schema()
    existente = get_user_by_email(email)
    now = _now()
    try:
        if existente is None:
            with db_conn() as conn:
                execute(
                    conn,
                    f"""INSERT INTO {TABELA}
                        (email, senha_hash, nome, papel, status, criado_em, atualizado_em, aprovado_por, aprovado_em, observacao)
                        VALUES (?, ?, ?, 'admin', 'ativo', ?, ?, 'bootstrap_env', ?, 'Admin inicial via .env')""",
                    (email, hash_senha(senha), nome, now, now, now),
                )
            log.info("Admin inicial criado via .env: %s", email)
        elif existente.get("papel") != "admin" or existente.get("status") != "ativo":
            # Garante que o admin declarado no .env esteja ativo como admin.
            with db_conn() as conn:
                execute(
                    conn,
                    f"UPDATE {TABELA} SET papel='admin', status='ativo', atualizado_em=? WHERE id=?",
                    (now, int(existente["id"])),
                )
            log.info("Admin inicial promovido/ativado via .env: %s", email)
    except Exception as exc:
        log.warning("Falha no bootstrap do admin via .env: %s", exc)
