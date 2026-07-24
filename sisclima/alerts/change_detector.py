from __future__ import annotations
import json
from sisclima.core.db import sqlite_conn
from sisclima.core.config import env, as_bool
from sisclima.utils.dates import now_iso
from sisclima.alerts.notifier import dispatch_alert
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def get_previous_level() -> str | None:
    with sqlite_conn() as conn:
        row = conn.execute('SELECT nivel FROM nivel_atual WHERE id=1').fetchone()
        return row['nivel'] if row else None


def update_current_level(data_referencia: str, nivel: str, score: int, motivo: str):
    with sqlite_conn() as conn:
        conn.execute('''
        INSERT INTO nivel_atual (id, data_referencia, nivel, score, motivo, updated_at)
        VALUES (1, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET data_referencia=excluded.data_referencia, nivel=excluded.nivel, score=excluded.score, motivo=excluded.motivo, updated_at=excluded.updated_at
        ''', (data_referencia, nivel, score, motivo, now_iso()))


def maybe_send_level_change(data_referencia: str, old: str | None, new: str, motivos: list[str], indicadores: dict) -> bool:
    force = as_bool(env('FORCE_ALERT_SEND', 'false'), False)
    only_on_change = as_bool(env('SEND_ALERT_ON_LEVEL_CHANGE', 'true'), True)

    if only_on_change and not force and old == new:
        log.info('Sem mudança de nível (%s); alerta não enviado. Use FORCE_ALERT_SEND=true para forçar.', new)
        return False

    if force and old == new:
        subject = f'[SIS Clima-Saúde] Alerta forçado — nível atual: {new}'
        message = (
            f'Data de referência: {data_referencia}\n'
            f'Nível atual: {new} (sem mudança; envio forçado por FORCE_ALERT_SEND)\n\n'
            f'Motivos principais:\n- ' + '\n- '.join(motivos[:8])
        )
    else:
        subject = f'[SIS Clima-Saúde] Mudança de nível: {old or "sem registro"} -> {new}'
        message = (
            f'Data de referência: {data_referencia}\n'
            f'Nível anterior: {old or "sem registro"}\n'
            f'Novo nível: {new}\n\n'
            f'Motivos principais:\n- ' + '\n- '.join(motivos[:8])
        )

    results = dispatch_alert(
        subject,
        message,
        {
            'data_referencia': data_referencia,
            'nivel_anterior': old,
            'nivel_novo': new,
            'indicadores': indicadores,
            'force': force,
        },
    )
    with sqlite_conn() as conn:
        conn.execute(
            '''INSERT INTO alertas_enviados (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (
                now_iso(),
                old,
                new,
                subject,
                message,
                json.dumps(results, ensure_ascii=False),
                'enviado' if any(results.values()) else 'registrado_sem_canal',
            ),
        )
    return True
