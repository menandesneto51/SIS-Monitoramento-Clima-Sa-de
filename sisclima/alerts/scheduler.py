# -*- coding: utf-8 -*-
"""Agendador de boletins CIEVS (loop ou disparo único).

Uso:
  python -m sisclima.alerts.scheduler --once --force
  python -m sisclima.alerts.scheduler --loop
"""
from __future__ import annotations

import argparse
import time

from sisclima.alerts.digest import send_digest
from sisclima.core.config import as_bool, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def run_once(*, force: bool = False, skip_cooldown: bool = False) -> dict:
    return send_digest(force=force, skip_cooldown=skip_cooldown)


def run_loop() -> None:
    interval_h = float(env("ALERT_INTERVAL_HOURS", "24") or 24)
    interval_s = max(300, int(interval_h * 3600))
    log.info(
        "Agendador SIS alertas iniciado · intervalo=%.1fh · SEND_ALERT=%s · min_level=%s · "
        "central=somente SES · fanout=%s",
        interval_h,
        env("SEND_ALERT_ON_LEVEL_CHANGE", "false"),
        env("ALERT_MIN_LEVEL", "laranja"),
        env("ALERT_FANOUT_ENABLED", "false"),
    )
    # Primeiro ciclo logo ao subir (respeita cooldown/fingerprint, salvo FORCE).
    force_first = as_bool(env("ALERT_SEND_ON_START", "true"), True)
    while True:
        try:
            out = run_once(force=force_first, skip_cooldown=force_first)
            force_first = False
            log.info("Ciclo agendador: %s", out.get("status"))
        except Exception:
            log.exception("Falha no ciclo do agendador")
        time.sleep(interval_s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Agendador de alertas SIS Clima-Saúde")
    p.add_argument("--once", action="store_true", help="Disparo único e sai")
    p.add_argument("--loop", action="store_true", help="Loop contínuo (serviço Docker)")
    p.add_argument("--force", action="store_true", help="Força envio (ignora gate/cooldown/idêntico)")
    p.add_argument("--skip-cooldown", action="store_true", help="Ignora apenas cooldown")
    args = p.parse_args(argv)

    if args.loop:
        run_loop()
        return 0

    out = run_once(force=args.force, skip_cooldown=args.skip_cooldown or args.force)
    print(out)
    return 0 if out.get("status") in {"enviado", "identico", "cooldown", "abaixo_do_minimo", "bloqueado_por_config"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
