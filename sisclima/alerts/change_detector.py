from __future__ import annotations

import json
from typing import Any

from sisclima.core.config import as_bool, env
from sisclima.core.db import db_conn, execute, fetchone, init_db
from sisclima.utils.dates import now_iso
from sisclima.alerts.notifier import dispatch_alert


def get_previous_level() -> str | None:
    with db_conn() as conn:
        row = fetchone(conn, "SELECT nivel FROM nivel_atual WHERE id=1")
        return row["nivel"] if row else None


def get_current_level_row() -> dict[str, Any] | None:
    with db_conn() as conn:
        row = fetchone(
            conn,
            "SELECT data_referencia, nivel, score, motivo, updated_at FROM nivel_atual WHERE id=1",
        )
        return dict(row) if row else None


def update_current_level(data_referencia: str, nivel: str, score: int, motivo: str):
    """Atualiza nivel_atual e anexa linha em nivel_historico (auditoria temporal)."""
    try:
        init_db()
    except Exception:
        pass
    prev = get_current_level_row()
    prev_nivel = (prev or {}).get("nivel")
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO nivel_atual (id, data_referencia, nivel, score, motivo, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                data_referencia=excluded.data_referencia,
                nivel=excluded.nivel,
                score=excluded.score,
                motivo=excluded.motivo,
                updated_at=excluded.updated_at
            """,
            (data_referencia, nivel, int(score or 0), motivo, now_iso()),
        )
        # Histórico: grava sempre a leitura da rodada (mesmo se nível não mudou)
        execute(
            conn,
            """
            INSERT INTO nivel_historico
                (data_referencia, nivel, score, motivo, nivel_anterior, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                data_referencia,
                nivel,
                int(score or 0),
                str(motivo or "")[:800],
                prev_nivel,
                now_iso(),
            ),
        )


def register_human_validation(
    *,
    data_referencia: str,
    nivel: str,
    usuario: str,
    decisao: str,
    checklist: dict[str, Any] | list[Any] | None = None,
    observacao: str = "",
) -> None:
    """Registra validação humana do alerta (não envia nada)."""
    try:
        init_db()
    except Exception:
        pass
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO alertas_validacao_humana
                (created_at, data_referencia, nivel, usuario, decisao, checklist_json, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                data_referencia,
                nivel,
                (usuario or "cievs").strip()[:120],
                (decisao or "validado").strip()[:80],
                json.dumps(checklist or {}, ensure_ascii=False),
                (observacao or "").strip()[:2000],
            ),
        )


def alerts_enabled() -> bool:
    """Envio só ocorre se SEND_ALERT_ON_LEVEL_CHANGE=true (padrão: false)."""
    return as_bool(env("SEND_ALERT_ON_LEVEL_CHANGE", "false"), False)


def build_level_change_message(
    data_referencia: str,
    old: str | None,
    new: str,
    motivos: list[str],
) -> tuple[str, str]:
    subject = f"[ARARAS MT] Mudança de nível: {old or 'sem registro'} -> {new}"
    message = (
        "ARARAS MT — Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde\n"
        "Clima, ambiente e saúde em uma só visão.\n\n"
        f"Data de referência: {data_referencia}\n"
        f"Nível anterior: {old or 'sem registro'}\n"
        f"Novo nível: {new}\n\nMotivos principais:\n- "
        + "\n- ".join((motivos or ["sem motivo informado"])[:8])
    )
    return subject, message


def maybe_send_level_change(data_referencia: str, old: str | None, new: str, motivos: list[str], indicadores: dict) -> bool:
    if old == new:
        return False

    subject, message = build_level_change_message(data_referencia, old, new, motivos)

    if not alerts_enabled():
        with db_conn() as conn:
            execute(
                conn,
                """
                INSERT INTO alertas_enviados
                    (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso(),
                    old,
                    new,
                    subject,
                    message,
                    json.dumps({"email": False, "telegram": False, "webhook": False, "motivo": "SEND_ALERT_ON_LEVEL_CHANGE=false"}, ensure_ascii=False),
                    "bloqueado_por_config",
                ),
            )
        return False

    results = dispatch_alert(
        subject,
        message,
        {
            "data_referencia": data_referencia,
            "nivel_anterior": old,
            "nivel_novo": new,
            "indicadores": indicadores,
        },
    )
    with db_conn() as conn:
        execute(
            conn,
            """
            INSERT INTO alertas_enviados
                (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now_iso(),
                old,
                new,
                subject,
                message,
                json.dumps(results, ensure_ascii=False),
                "enviado" if any(results.values()) else "registrado_sem_canal",
            ),
        )
    return True
