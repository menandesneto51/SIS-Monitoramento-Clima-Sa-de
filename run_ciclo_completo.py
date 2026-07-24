"""Ciclo completo de produção: preflight + pipeline com alertas.

Uso:
  .\\.venv\\Scripts\\python.exe run_ciclo_completo.py
  .\\.venv\\Scripts\\python.exe run_ciclo_completo.py --force-alert
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description='Executa preflight + pipeline com alertas')
    parser.add_argument(
        '--force-alert',
        action='store_true',
        help='Força envio de alerta mesmo sem mudança de nível (FORCE_ALERT_SEND=true)',
    )
    parser.add_argument(
        '--skip-preflight',
        action='store_true',
        help='Não interrompe em falha crítica de preflight',
    )
    args = parser.parse_args()

    if args.force_alert:
        os.environ['FORCE_ALERT_SEND'] = 'true'

    # Garante flags de alerta ligadas para este ciclo (sem sobrescrever se já true).
    os.environ.setdefault('USE_EMAIL', 'true')
    os.environ.setdefault('ALERT_EMAIL_ENABLED', 'true')
    os.environ.setdefault('USE_TELEGRAM', 'true')
    os.environ.setdefault('ALERT_TELEGRAM_ENABLED', 'true')
    os.environ.setdefault('SEND_ALERT_ON_LEVEL_CHANGE', 'true')

    from sisclima.validation.preflight import run_preflight, summarize_preflight
    from sisclima.core.db import init_db
    from sisclima.pipeline import run_pipeline

    print('=== PREFLIGHT ===')
    df = run_preflight()
    summary = summarize_preflight(df)
    fails = df[~df['ok']]
    if not fails.empty:
        print(fails.to_string(index=False))
    print('RESUMO:', summary)

    if summary.get('critical_fail', 0) > 0 and not args.skip_preflight:
        print('Abortado: há falhas críticas no preflight.')
        return 2

    print('\n=== PIPELINE + ALERTAS ===')
    init_db()
    result = run_pipeline(send_alerts=True)
    print(result)
    return 0 if result.get('status') == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
