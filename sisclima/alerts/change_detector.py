from __future__ import annotations
import json
from sisclima.core.config import as_bool, env
from sisclima.core.db import db_conn, execute, fetchone
from sisclima.utils.dates import now_iso
from sisclima.alerts.notifier import dispatch_alert


def get_previous_level() -> str | None:
    with db_conn() as conn:
        row = fetchone(conn, "SELECT nivel FROM nivel_atual WHERE id=1")
        return row["nivel"] if row else None


def update_current_level(data_referencia: str, nivel: str, score: int, motivo: str):
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
            (data_referencia, nivel, score, motivo, now_iso()),
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
    subject = f"[SIS Clima-Saúde] Mudança de nível: {old or 'sem registro'} -> {new}"
    message = (
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
