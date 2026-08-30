# -*- coding: utf-8 -*-
"""Agendador operacional da ETL do ARARAS MT.

Executa o pipeline em intervalo configurável, sem enviar alertas, registra um
arquivo de saúde para a operação e impede duas execuções simultâneas no mesmo
host/volume Docker.

Por padrão a **extração completa** (``run_pipeline`` com replace das tabelas)
corre **no máximo 1× por dia civil** local (``ETL_FULL_ONCE_PER_DAY=true``),
com intervalo de 24 h. Reinícios do container não disparam nova carga se a
rodada do dia já tiver sido ``success``.

Uso:
  python -m sisclima.etl_scheduler --once
  python -m sisclima.etl_scheduler --loop
  ETL_FORCE=true python -m sisclima.etl_scheduler --once   # ignora gate diário
"""
from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator

from sisclima.core.config import as_bool, env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

PipelineRunner = Callable[[], dict[str, Any]]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _path_from_env(name: str, default: str) -> Path:
    return Path(env(name, default) or default)


def _health_path() -> Path:
    return _path_from_env("ETL_HEALTH_FILE", "logs/etl_scheduler_health.json")


def _lock_path() -> Path:
    return _path_from_env("ETL_LOCK_FILE", "logs/etl_scheduler.lock")


def _parse_health_dt(raw: Any) -> datetime | None:
    if raw is None:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except (TypeError, ValueError):
        return None


def _already_succeeded_today(health_path: Path | None = None) -> bool:
    """True se já houve ETL completa com sucesso no dia civil local."""
    if not as_bool(env("ETL_FULL_ONCE_PER_DAY", "true"), True):
        return False
    target = health_path or _health_path()
    if not target.is_file():
        return False
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if str(data.get("status") or "").lower() != "success":
        return False
    finished = _parse_health_dt(data.get("finished_at") or data.get("started_at"))
    if finished is None:
        return False
    return finished.date() == datetime.now().date()


def _seconds_until_next_daily_window() -> int:
    """Espera até o próximo dia no horário ETL_DAILY_HOUR."""
    now = datetime.now()
    try:
        hour = int(env("ETL_DAILY_HOUR", "6") or 6)
    except (TypeError, ValueError):
        hour = 6
    hour = min(23, max(0, hour))
    nxt = (now + timedelta(days=1)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return max(300, int((nxt - now).total_seconds()))


def _write_health(payload: dict[str, Any], path: Path | None = None) -> None:
    target = path or _health_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


@contextmanager
def _exclusive_lock(path: Path | None = None) -> Iterator[bool]:
    """Adquire trava não bloqueante compartilhada pelo volume ``logs``.

    O container é Linux; em plataformas sem ``fcntl`` a execução continua com
    log explícito, preservando compatibilidade com testes/uso local no Windows.
    """

    target = path or _lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = target.open("a+", encoding="utf-8")
    acquired = True
    fcntl_module = None
    try:
        try:
            import fcntl as fcntl_module  # type: ignore[no-redef]

            fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_EX | fcntl_module.LOCK_NB)
        except BlockingIOError:
            acquired = False
        except ImportError:
            log.warning("fcntl indisponível; ETL seguirá sem trava entre processos")

        if acquired:
            handle.seek(0)
            handle.truncate()
            handle.write(f"pid={os.getpid()} iniciado_em={_now_iso()}\n")
            handle.flush()
        yield acquired
    finally:
        if acquired and fcntl_module is not None:
            try:
                fcntl_module.flock(handle.fileno(), fcntl_module.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _default_runner() -> dict[str, Any]:
    from sisclima.pipeline import run_pipeline

    # O envio permanece em serviço separado e só pode ocorrer depois do gate
    # de frescor. Isso evita que uma ETL reprocessada dispare comunicação.
    return run_pipeline(send_alerts=False)


def run_once(
    *,
    runner: PipelineRunner | None = None,
    health_path: Path | None = None,
    lock_path: Path | None = None,
    force: bool | None = None,
) -> dict[str, Any]:
    """Executa uma rodada auditável da ETL e atualiza o arquivo de saúde."""

    started_at = _now_iso()
    force_run = as_bool(env("ETL_FORCE", "false"), False) if force is None else bool(force)
    if not force_run and _already_succeeded_today(health_path):
        result = {
            "status": "skipped_already_today",
            "started_at": started_at,
            "finished_at": _now_iso(),
            "message": (
                "Extração completa já concluída com sucesso hoje "
                "(ETL_FULL_ONCE_PER_DAY). Use ETL_FORCE=true para forçar."
            ),
        }
        # Não sobrescrever o health de success do dia — o gate lê status=success.
        log.info(result["message"])
        return result

    with _exclusive_lock(lock_path) as acquired:
        if not acquired:
            result = {
                "status": "skipped_locked",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": "Outra execução da ETL está em andamento.",
            }
            _write_health(result, health_path)
            log.warning(result["message"])
            return result

        # Revalida sob lock (evita corrida entre dois starts no mesmo dia).
        if not force_run and _already_succeeded_today(health_path):
            result = {
                "status": "skipped_already_today",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": "Extração completa já concluída com sucesso hoje (sob trava).",
            }
            log.info(result["message"])
            return result

        _write_health({"status": "running", "started_at": started_at}, health_path)
        try:
            output = (runner or _default_runner)() or {}
            finished_at = _now_iso()
            pipeline_status = str(output.get("status") or "success")
            health_status = "success" if pipeline_status == "success" else "error"
            result = {
                "status": health_status,
                "pipeline_status": pipeline_status,
                "run_id": output.get("run_id"),
                "nivel": output.get("nivel"),
                "started_at": started_at,
                "finished_at": finished_at,
                "message": output.get("message") or f"Pipeline finalizado com status {pipeline_status}.",
                "mode": "full_extract",
            }
            _write_health(result, health_path)
            if health_status != "success":
                raise RuntimeError(str(result["message"]))
            log.info("ETL concluída · run_id=%s · nível=%s", result.get("run_id"), result.get("nivel"))
            return result
        except Exception as exc:
            result = {
                "status": "error",
                "started_at": started_at,
                "finished_at": _now_iso(),
                "message": str(exc),
            }
            _write_health(result, health_path)
            log.exception("Falha na ETL agendada")
            raise


def run_loop() -> None:
    interval_h = float(env("ETL_INTERVAL_HOURS", "24") or 24)
    retry_min = float(env("ETL_RETRY_MINUTES", "15") or 15)
    interval_s = max(300, int(interval_h * 3600))
    retry_s = max(60, int(retry_min * 60))
    run_on_start = as_bool(env("ETL_RUN_ON_START", "true"), True)
    once_per_day = as_bool(env("ETL_FULL_ONCE_PER_DAY", "true"), True)

    log.info(
        "Agendador ETL ARARAS iniciado · intervalo=%.1fh · retry=%.1fmin · "
        "run_on_start=%s · full_once_per_day=%s",
        interval_h,
        retry_min,
        run_on_start,
        once_per_day,
    )

    if not run_on_start:
        time.sleep(interval_s)

    while True:
        cycle_started = time.monotonic()
        delay = interval_s
        try:
            result = run_once()
            status = str(result.get("status") or "")
            if status == "skipped_locked":
                delay = retry_s
            elif status == "skipped_already_today":
                delay = _seconds_until_next_daily_window()
            else:
                elapsed = int(time.monotonic() - cycle_started)
                if once_per_day:
                    delay = max(300, _seconds_until_next_daily_window())
                else:
                    delay = max(60, interval_s - elapsed)
        except Exception:
            delay = retry_s
        log.info("Próxima tentativa da ETL em %.1f minuto(s)", delay / 60)
        time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agendador da ETL ARARAS MT")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Executa uma rodada e encerra")
    mode.add_argument("--loop", action="store_true", help="Executa continuamente")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignora o gate de 1× por dia (equivalente a ETL_FORCE=true)",
    )
    args = parser.parse_args(argv)

    if args.force:
        os.environ["ETL_FORCE"] = "true"

    if args.loop:
        run_loop()
        return 0

    run_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
