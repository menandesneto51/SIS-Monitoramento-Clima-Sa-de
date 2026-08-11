# -*- coding: utf-8 -*-
"""Agendador de boletins CIEVS (loop ou disparo único).

Uso:
  python -m sisclima.alerts.scheduler --once --force
  python -m sisclima.alerts.scheduler --loop
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sisclima.alerts.digest import send_digest
from sisclima.core.config import as_bool, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def _etl_health_status() -> tuple[bool, dict[str, Any]]:
    """Confirma que a última ETL terminou com sucesso e ainda está fresca."""

    if not as_bool(env("ALERT_REQUIRE_FRESH_ETL", "false"), False):
        return True, {"gate": "disabled"}

    path = Path(env("ETL_HEALTH_FILE", "logs/etl_scheduler_health.json") or "logs/etl_scheduler_health.json")
    max_age_h = float(env("ALERT_MAX_ETL_AGE_HOURS", "12") or 12)
    if not path.is_file():
        return False, {"gate": "enabled", "reason": "health_file_missing", "path": str(path)}

    try:
        health = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, {"gate": "enabled", "reason": "health_file_invalid", "detail": str(exc)}

    if health.get("status") != "success":
        return False, {
            "gate": "enabled",
            "reason": "etl_not_successful",
            "etl_status": health.get("status"),
            "message": health.get("message"),
        }

    finished_raw = health.get("finished_at")
    if not finished_raw:
        return False, {"gate": "enabled", "reason": "finished_at_missing"}

    try:
        finished_at = datetime.fromisoformat(str(finished_raw).replace("Z", "+00:00"))
        now = datetime.now().astimezone()
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=now.tzinfo)
        age_h = max(0.0, (now - finished_at.astimezone(now.tzinfo)).total_seconds() / 3600)
    except Exception as exc:  # noqa: BLE001
        return False, {"gate": "enabled", "reason": "finished_at_invalid", "detail": str(exc)}

    meta = {
        "gate": "enabled",
        "status": "fresh" if age_h <= max_age_h else "stale",
        "age_hours": round(age_h, 2),
        "max_age_hours": max_age_h,
        "run_id": health.get("run_id"),
        "finished_at": finished_raw,
    }
    return age_h <= max_age_h, meta


def run_once(*, force: bool = False, skip_cooldown: bool = False) -> dict:
    if not force:
        ready, etl_meta = _etl_health_status()
        if not ready:
            log.warning("Envio adiado: ETL indisponível ou defasada · %s", etl_meta)
            return {"status": "etl_indisponivel", "etl": etl_meta}
    return send_digest(force=force, skip_cooldown=skip_cooldown)


def run_loop() -> None:
    interval_h = float(env("ALERT_INTERVAL_HOURS", "24") or 24)
    interval_s = max(300, int(interval_h * 3600))
    log.info(
        "Agendador ARARAS alertas iniciado · intervalo=%.1fh · SEND_ALERT=%s · min_level=%s · "
        "central=somente SES · fanout=%s · exige_etl_fresca=%s",
        interval_h,
        env("SEND_ALERT_ON_LEVEL_CHANGE", "false"),
        env("ALERT_MIN_LEVEL", "laranja"),
        env("ALERT_FANOUT_ENABLED", "false"),
        env("ALERT_REQUIRE_FRESH_ETL", "false"),
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
    p = argparse.ArgumentParser(description="Agendador de alertas ARARAS MT")
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
    return 0 if out.get("status") in {
        "enviado",
        "identico",
        "cooldown",
        "abaixo_do_minimo",
        "bloqueado_por_config",
        "etl_indisponivel",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
