# -*- coding: utf-8 -*-
"""Agendador operacional da ETL do ARARAS MT.

Executa o pipeline em intervalo configurável, sem enviar alertas, registra um
arquivo de saúde para a operação e impede duas execuções simultâneas no mesmo
host/volume Docker.

Uso:
  python -m sisclima.etl_scheduler --once
  python -m sisclima.etl_scheduler --loop
"""
from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
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
) -> dict[str, Any]:
    """Executa uma rodada auditável da ETL e atualiza o arquivo de saúde."""

    started_at = _now_iso()
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
    interval_h = float(env("ETL_INTERVAL_HOURS", "6") or 6)
    retry_min = float(env("ETL_RETRY_MINUTES", "15") or 15)
    interval_s = max(300, int(interval_h * 3600))
    retry_s = max(60, int(retry_min * 60))
    run_on_start = as_bool(env("ETL_RUN_ON_START", "true"), True)

    log.info(
        "Agendador ETL ARARAS iniciado · intervalo=%.1fh · retry=%.1fmin · run_on_start=%s",
        interval_h,
        retry_min,
        run_on_start,
    )

    if not run_on_start:
        time.sleep(interval_s)

    while True:
        cycle_started = time.monotonic()
        delay = interval_s
        try:
            result = run_once()
            if result.get("status") == "skipped_locked":
                delay = retry_s
            else:
                elapsed = int(time.monotonic() - cycle_started)
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
    args = parser.parse_args(argv)

    if args.loop:
        run_loop()
        return 0

    try:
        result = run_once()
    except Exception:
        return 1
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0 if result.get("status") in {"success", "skipped_locked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
