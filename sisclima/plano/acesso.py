# -*- coding: utf-8 -*-
"""Perfis do Plano El Niño — dimensão extra, sem alterar niveis do painel.

Níveis existentes (publico/municipal/regional/ses/admin) continuam valendo
para o painel climático. O Plano usa perfil_plano + area_id.
A Sala só abre para ses+ (ses ou admin).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sisclima.core.db import db_conn, execute, fetchall, fetchone
from sisclima.plano.areas import AREAS_CANONICAS, rotulo_area
from sisclima.plano.constants import NIVEIS_PAINEL_SALA, PERFIS_PLANO
from sisclima.plano.schema import garantir_schema

PERFIS_PLANO_IDS = {k for k, _ in PERFIS_PLANO}

# Quem vê a Sala no menu interno (não o público).
NIVEIS_ABRIR_SALA = NIVEIS_PAINEL_SALA

# Escrita restrita à própria área.
PERFIS_EDICAO_AREA = frozenset({"coordenador_area", "tecnico_area"})
PERFIS_TODAS_AREAS = frozenset({"admin_araras", "secretaria_executiva_cievs"})
PERFIS_VALIDAR = frozenset({"admin_araras", "secretaria_executiva_cievs"})
PERFIS_DECISAO_SALA = frozenset({"admin_araras", "secretaria_executiva_cievs", "gestor"})
PERFIS_VER_EVIDENCIA = frozenset(
    {
        "admin_araras",
        "secretaria_executiva_cievs",
        "coordenador_area",
        "tecnico_area",
        "gestor",
    }
)


def rotulo_perfil_plano(perfil: str) -> str:
    for key, lbl in PERFIS_PLANO:
        if key == perfil:
            return lbl
    return perfil or "—"


def _nivel_painel(user: dict[str, Any] | None) -> str:
    return str((user or {}).get("nivel") or "publico")


def _status_ativo(user: dict[str, Any] | None) -> bool:
    return bool(user) and str((user or {}).get("status") or "ativo") == "ativo"


def pode_abrir_sala(user: dict[str, Any] | None) -> bool:
    """Sala de Situação / Plano: ses ou admin ativos. Público, municipal e regional não entram."""
    if not _status_ativo(user):
        return False
    return _nivel_painel(user) in NIVEIS_ABRIR_SALA


def perfil_plano_efetivo(user: dict[str, Any] | None) -> str:
    """Admin do painel equivale a admin_araras até o vínculo institucional (STI) existir."""
    if not user:
        return ""
    raw = str(user.get("perfil_plano") or "").strip()
    if raw not in PERFIS_PLANO_IDS:
        vinculo = vinculo_ativo(str(user.get("email") or ""))
        raw = str((vinculo or {}).get("perfil_plano") or "").strip()
    if raw in PERFIS_PLANO_IDS:
        return raw
    if _nivel_painel(user) == "admin":
        return "admin_araras"
    if _nivel_painel(user) == "ses":
        return "consulta"
    return ""


def area_id_usuario(user: dict[str, Any] | None) -> str:
    raw = str((user or {}).get("area_id") or "").strip()
    if raw:
        return raw
    vinculo = vinculo_ativo(str((user or {}).get("email") or ""))
    return str((vinculo or {}).get("area_id") or "").strip()


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def vinculo_ativo(email: str) -> dict[str, Any] | None:
    """Último vínculo ativo do Plano para o e-mail (tabela plano_vinculo)."""
    alvo = str(email or "").strip().lower()
    if not alvo:
        return None
    garantir_schema()
    with db_conn() as conn:
        row = fetchone(
            conn,
            """
            SELECT email, perfil_plano, area_id, status, criado_em
            FROM plano_vinculo
            WHERE lower(email) = ? AND status = 'ativo'
            ORDER BY id DESC
            """,
            (alvo,),
        )
    return dict(row) if row else None


def anexar_vinculo(user: dict[str, Any] | None) -> dict[str, Any] | None:
    """Copia perfil_plano/area_id do vínculo para o dict do usuário, sem gravar sessão."""
    if not user:
        return None
    out = dict(user)
    vinculo = vinculo_ativo(str(out.get("email") or ""))
    if vinculo:
        if not str(out.get("perfil_plano") or "").strip():
            out["perfil_plano"] = vinculo.get("perfil_plano")
        if not str(out.get("area_id") or "").strip():
            out["area_id"] = vinculo.get("area_id") or ""
    return out


def listar_vinculos(*, so_ativos: bool = True) -> list[dict[str, Any]]:
    garantir_schema()
    sql = "SELECT id, email, perfil_plano, area_id, status, criado_em FROM plano_vinculo"
    if so_ativos:
        sql += " WHERE status = 'ativo'"
    sql += " ORDER BY email, id DESC"
    with db_conn() as conn:
        rows = fetchall(conn, sql)
    out = []
    for row in rows:
        item = dict(row)
        item["area_rotulo"] = rotulo_area(str(item.get("area_id") or ""))
        item["perfil_rotulo"] = rotulo_perfil_plano(str(item.get("perfil_plano") or ""))
        out.append(item)
    return out


def gravar_vinculo(
    *,
    email: str,
    perfil_plano: str,
    area_id: str = "",
    ator_email: str = "",
) -> tuple[bool, str]:
    """Um vínculo ativo por e-mail. Área obrigatória para coordenador/técnico."""
    alvo = str(email or "").strip().lower()
    perfil = str(perfil_plano or "").strip()
    area = str(area_id or "").strip()
    if not alvo or "@" not in alvo:
        return False, "Informe um e-mail institucional."
    if perfil not in PERFIS_PLANO_IDS:
        return False, "Perfil do Plano inválido."
    if perfil in PERFIS_EDICAO_AREA and not area:
        return False, "Coordenador e técnico de área exigem area_id."
    if area and area not in {k for k, _ in AREAS_CANONICAS}:
        return False, f"Área desconhecida: {area}."
    garantir_schema()
    agora = _agora()
    with db_conn() as conn:
        execute(conn, "UPDATE plano_vinculo SET status = 'inativo' WHERE lower(email) = ?", (alvo,))
        if area:
            row = fetchone(
                conn,
                "SELECT id FROM plano_vinculo WHERE lower(email) = ? AND perfil_plano = ? AND area_id = ?",
                (alvo, perfil, area),
            )
        else:
            row = fetchone(
                conn,
                """
                SELECT id FROM plano_vinculo
                WHERE lower(email) = ? AND perfil_plano = ? AND (area_id IS NULL OR area_id = '')
                """,
                (alvo, perfil),
            )
        if row:
            execute(
                conn,
                "UPDATE plano_vinculo SET status = 'ativo', criado_em = ? WHERE id = ?",
                (agora, int(row["id"])),
            )
        else:
            execute(
                conn,
                """
                INSERT INTO plano_vinculo (email, perfil_plano, area_id, status, criado_em)
                VALUES (?, ?, ?, 'ativo', ?)
                """,
                (alvo, perfil, area or None, agora),
            )
        execute(
            conn,
            """
            INSERT INTO audit_log (criado_em, ator_email, acao, entidade, entidade_id, detalhe)
            VALUES (?, ?, 'vinculo_plano', 'plano_vinculo', ?, ?)
            """,
            (agora, ator_email or alvo, alvo, f"{perfil}|{area}"),
        )
    return True, f"{alvo}: {rotulo_perfil_plano(perfil)}" + (f" · {rotulo_area(area)}" if area else "")


def pode_abrir_interno(user: dict[str, Any] | None) -> bool:
    """Painel interno (municipal+ aprovado). Público permanece no painel aberto."""
    if not _status_ativo(user):
        return False
    return _nivel_painel(user) in {"municipal", "regional", "ses", "admin"}


MATRIZ_ACESSO_PAINEL: tuple[dict[str, str], ...] = (
    {
        "nivel": "publico",
        "rotulo": "Público",
        "abre_interno": "não",
        "abre_sala": "não",
        "recorte": "Estado agregado",
        "plano": "não aplica",
    },
    {
        "nivel": "municipal",
        "rotulo": "Municipal (SMS)",
        "abre_interno": "sim, após aprovação",
        "abre_sala": "não",
        "recorte": "Município do cadastro",
        "plano": "não aplica",
    },
    {
        "nivel": "regional",
        "rotulo": "Regional (CRS)",
        "abre_interno": "sim, após aprovação",
        "abre_sala": "não",
        "recorte": "Regional de Saúde do cadastro",
        "plano": "não aplica",
    },
    {
        "nivel": "ses",
        "rotulo": "SES / CIEVS",
        "abre_interno": "sim, após aprovação",
        "abre_sala": "sim",
        "recorte": "Estado",
        "plano": "consulta até haver vínculo (área + perfil)",
    },
    {
        "nivel": "admin",
        "rotulo": "Administração",
        "abre_interno": "sim (não é autoatribuído)",
        "abre_sala": "sim",
        "recorte": "Estado",
        "plano": "admin_araras, ou o vínculo gravado",
    },
)


def capacidades_usuario(user: dict[str, Any] | None) -> dict[str, Any]:
    u = anexar_vinculo(user) if user else None
    perfil = perfil_plano_efetivo(u)
    area = area_id_usuario(u)
    return {
        "email": str((u or {}).get("email") or ""),
        "nome": str((u or {}).get("nome") or ""),
        "nivel": _nivel_painel(u),
        "status": str((u or {}).get("status") or ""),
        "abre_interno": pode_abrir_interno(u),
        "abre_sala": pode_abrir_sala(u),
        "perfil_plano": perfil,
        "rotulo_perfil": rotulo_perfil_plano(perfil),
        "area_id": area,
        "area_rotulo": rotulo_area(area) if area else "",
        "pode_editar_area": bool(perfil in PERFIS_EDICAO_AREA and area),
        "pode_validar": pode_validar(u),
        "pode_ver_evidencia": pode_ver_evidencia(u, area),
    }


def pode_editar_area(user: dict[str, Any] | None, area_id: str) -> bool:
    """Assistência Farmacêutica não edita Vigilância Sanitária, e vice-versa."""
    if not pode_abrir_sala(user):
        return False
    alvo = str(area_id or "").strip()
    if not alvo:
        return False
    perfil = perfil_plano_efetivo(user)
    if perfil in PERFIS_TODAS_AREAS:
        return True
    if perfil not in PERFIS_EDICAO_AREA:
        return False
    return area_id_usuario(user) == alvo


def pode_validar(user: dict[str, Any] | None) -> bool:
    if not pode_abrir_sala(user):
        return False
    return perfil_plano_efetivo(user) in PERFIS_VALIDAR


def pode_ver_evidencia(user: dict[str, Any] | None, area_id: str = "") -> bool:
    """Evidência/PDF/SEI nunca vai ao painel público. Consulta não baixa arquivo."""
    if not pode_abrir_sala(user):
        return False
    perfil = perfil_plano_efetivo(user)
    if perfil not in PERFIS_VER_EVIDENCIA:
        return False
    if perfil in PERFIS_TODAS_AREAS or perfil == "gestor":
        return True
    if not area_id:
        return True
    return area_id_usuario(user) == str(area_id).strip()


def contexto_plano(user: dict[str, Any] | None) -> dict[str, Any]:
    u = anexar_vinculo(user) if user else None
    return {
        "pode_abrir": pode_abrir_sala(u),
        "perfil_plano": perfil_plano_efetivo(u),
        "area_id": area_id_usuario(u),
        "rotulo_perfil": rotulo_perfil_plano(perfil_plano_efetivo(u)),
        "pode_validar": pode_validar(u),
    }
