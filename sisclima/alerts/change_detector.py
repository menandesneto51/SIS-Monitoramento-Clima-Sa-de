from __future__ import annotations
from sisclima.core.config import env, as_bool
from sisclima.core.logging_utils import get_logger
from sisclima.alerts.vigia_alerts import dispatch_vigia_alerts
from sisclima.core.db import sqlite_conn
from sisclima.utils.dates import now_iso

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


def maybe_send_level_change(
    data_referencia: str,
    old: str | None,
    new: str,
    motivos: list[str],
    indicadores: dict,
    resumo_mun=None,
) -> bool:
    """Dispara os 3 alertas VIGIA (Estado, Regionais, Cuiabá) com orientações.

    - SEND_ALERT_ON_LEVEL_CHANGE=true: só envia se o nível mudou
    - FORCE_ALERT_SEND=true: força envio mesmo sem mudança
    """
    force = as_bool(env('FORCE_ALERT_SEND', 'false'), False)
    only_on_change = as_bool(env('SEND_ALERT_ON_LEVEL_CHANGE', 'true'), True)

    if only_on_change and not force and old == new:
        log.info(
            'Sem mudança de nível (%s); alerta VIGIA não enviado. Use FORCE_ALERT_SEND=true para forçar.',
            new,
        )
        return False

    result = dispatch_vigia_alerts(
        data_referencia=data_referencia,
        old=old,
        new=new,
        motivos=motivos,
        indicadores=indicadores,
        resumo_mun=resumo_mun,
        force=force,
    )
    log.info('Pacote VIGIA processado: %s', result)
    return True
