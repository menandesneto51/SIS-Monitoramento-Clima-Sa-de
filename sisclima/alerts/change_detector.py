from __future__ import annotations
import json
from sisclima.core.db import sqlite_conn
from sisclima.utils.dates import now_iso
from sisclima.alerts.notifier import dispatch_alert


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
    if old == new:
        return False
    subject = f'[SIS Clima-Saúde] Mudança de nível: {old or "sem registro"} -> {new}'
    message = f'Data de referência: {data_referencia}\nNível anterior: {old or "sem registro"}\nNovo nível: {new}\n\nMotivos principais:\n- ' + '\n- '.join(motivos[:8])
    results = dispatch_alert(subject, message, {'data_referencia': data_referencia, 'nivel_anterior': old, 'nivel_novo': new, 'indicadores': indicadores})
    with sqlite_conn() as conn:
        conn.execute('''INSERT INTO alertas_enviados (created_at, nivel_anterior, nivel_novo, titulo, mensagem, canais, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', (now_iso(), old, new, subject, message, json.dumps(results, ensure_ascii=False), 'enviado' if any(results.values()) else 'registrado_sem_canal'))
    return True
