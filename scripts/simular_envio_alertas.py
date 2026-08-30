# -*- coding: utf-8 -*-
"""Simula fan-out territorial (cronômetro) e envia de verdade só ao canal SES.

Uso:
  python scripts/simular_envio_alertas.py
  python scripts/simular_envio_alertas.py --sem-envio-ses   # só cronometra, sem e-mail SES

Comportamento padrão:
  - SES (ALERT_EMAIL_TO = menandesneto + notifica) + Telegram central: ENVIO REAL
  - Municípios / regionais: SIMULAÇÃO (não envia; inclui PENDENTE para medir cobertura)
  - ALERT_FANOUT_ENABLED permanece false
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.alerts.digest import send_digest  # noqa: E402
from sisclima.core.config import env  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Simula fan-out e envia alerta real só à SES")
    parser.add_argument(
        "--sem-envio-ses",
        action="store_true",
        help="Não envia e-mail/Telegram à SES (só monta e cronometra fan-out)",
    )
    parser.add_argument(
        "--so-aprovados",
        action="store_true",
        help="Na simulação, ignore PENDENTE (só ativo=1)",
    )
    args = parser.parse_args()

    # Força simulação de fan-out nesta rodada (sem alterar .env permanentemente via subprocess).
    import os

    os.environ["ALERT_FANOUT_SIMULATE"] = "true"
    os.environ["ALERT_FANOUT_SIMULATE_PENDENTES"] = "false" if args.so_aprovados else "true"
    # Garante que fan-out real continue off.
    os.environ["ALERT_FANOUT_ENABLED"] = "false"

    print("=== Simulação de alertas ARARAS ===")
    print(f"Canal SES (ALERT_EMAIL_TO): {env('ALERT_EMAIL_TO')}")
    print(f"Envio real SES: {'NÃO' if args.sem_envio_ses else 'SIM'}")
    print(f"Fan-out municipal: SIMULADO (PENDENTE={'não' if args.so_aprovados else 'sim'})")
    print()

    t0 = time.perf_counter()
    if args.sem_envio_ses:
        # Só pack + fanout simulado, sem SMTP central.
        from sisclima.alerts.digest import _fanout_territorial, build_multilevel_pack

        payloads, fingerprint, meta = build_multilevel_pack()
        fanout = _fanout_territorial(payloads, simulate=True, include_inactive=not args.so_aprovados)
        out = {
            "status": "simulado_sem_ses",
            "fingerprint": fingerprint,
            "canais": {"fanout": fanout, "email": False, "telegram": False},
            **meta,
        }
    else:
        out = send_digest(force=True, skip_cooldown=True, simulate_fanout=True)

    elapsed = time.perf_counter() - t0
    canais = out.get("canais") or {}
    fanout = canais.get("fanout") or {}

    report = {
        "status": out.get("status"),
        "nivel": out.get("nivel"),
        "fingerprint": out.get("fingerprint"),
        "n_ses": out.get("n_ses"),
        "n_regionais": out.get("n_regionais"),
        "n_municipais": out.get("n_municipais"),
        "n_cuiaba": out.get("n_cuiaba"),
        "n_gerados": out.get("n_gerados"),
        "ses_email_ok": canais.get("email"),
        "ses_telegram_ok": canais.get("telegram"),
        "tempo_build_s": canais.get("tempo_build_s"),
        "tempo_central_s": canais.get("tempo_central_s"),
        "fanout_status": fanout.get("status"),
        "fanout_gerados": fanout.get("gerados"),
        "fanout_simulados": fanout.get("simulados"),
        "fanout_sem_destinatario": fanout.get("sem_destinatario"),
        "fanout_emails_unicos": fanout.get("emails_unicos"),
        "fanout_tempo_format_s": fanout.get("tempo_format_s"),
        "fanout_tempo_total_s": fanout.get("tempo_total_s"),
        "fanout_smtp_estimado_s": fanout.get("smtp_estimado_s"),
        "tempo_wall_s": round(elapsed, 3),
        "melhorias_sugeridas": [
            "Aprovar contatos em lotes (regional) antes de ALERT_FANOUT_ENABLED=true.",
            "Enviar municipais em paralelo com pool SMTP limitado (hoje é sequencial + sleep 0,2s).",
            "Resumo regional único por escritório em vez de N e-mails municipais idênticos na mesma região.",
            "Pré-formatar HTML uma vez por escopo e reutilizar template (format_s atual é o custo de CPU).",
            "Fila assíncrona (etl → fila → worker) para não bloquear o digest SES.",
        ],
    }

    out_dir = ROOT / "logs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"sim_alerta_fanout_{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("--- Resultado ---")
    print(f"Status: {report['status']} · nível {report['nivel']}")
    print(f"SES e-mail: {report['ses_email_ok']} · Telegram: {report['ses_telegram_ok']}")
    print(
        f"Fan-out simulado: {report['fanout_simulados']}/{report['fanout_gerados']} "
        f"(sem dest.: {report['fanout_sem_destinatario']}) · e-mails únicos: {report['fanout_emails_unicos']}"
    )
    print(
        f"Tempos: build={report['tempo_build_s']}s · SES={report['tempo_central_s']}s · "
        f"format={report['fanout_tempo_format_s']}s · fanout={report['fanout_tempo_total_s']}s · "
        f"SMTP estimado se real={report['fanout_smtp_estimado_s']}s · wall={report['tempo_wall_s']}s"
    )
    print(f"Relatório: {path}")
    print()
    print("Melhorias sugeridas:")
    for i, tip in enumerate(report["melhorias_sugeridas"], 1):
        print(f"  {i}. {tip}")
    return 0 if report["status"] in {"enviado", "simulado_sem_ses"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
