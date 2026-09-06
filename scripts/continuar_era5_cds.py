# -*- coding: utf-8 -*-
"""Continua o download ERA5-Land (CDS) mês a mês — retomável.

Não recalcula EHF; só preenche ``data/output/star/era5/``.
Depois rode ``scripts/carregar_star_ondas_geocalor.py --fonte cds`` (ou ``--skip-fetch``
se o bruto já estiver montado).
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path

from sisclima.core.config import APP_CONFIG
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.era5_cds import (
    dismiss_stale_cds_jobs,
    download_era5_year_stat,
    has_cds_credentials,
    inventariar_cache_era5,
)

log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output" / "star"
PROGRESS = OUT / "era5_cds_progress.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Continua download CDS ERA5-Land (mensal)")
    p.add_argument("--start-date", default="2020-01-01")
    p.add_argument("--end-date", default="")
    p.add_argument("--max-jobs", type=int, default=0, help="Limite de downloads nesta execução (0=todos)")
    p.add_argument("--sleep", type=float, default=1.0, help="Pausa entre jobs (s)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not has_cds_credentials():
        print("Sem COPERNICUS_CDS_KEY / .cdsapirc")
        return 2

    # Jobs accepted órfãos (reinícios) travam a fila CDS do usuário
    try:
        dismissed = dismiss_stale_cds_jobs(max_age_hours=1.5)
        if dismissed:
            print(json.dumps({"dismissed_stale_jobs": len(dismissed)}, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        log.warning("Não foi possível limpar jobs CDS órfãos: %s", exc)

    end = args.end_date or date.today().isoformat()
    cache = APP_CONFIG.output_dir / "star" / "era5"
    inv = inventariar_cache_era5(start_date=args.start_date, end_date=end, cache_dir=cache)
    print(
        json.dumps(
            {
                "cache_dir": inv["cache_dir"],
                "n_presentes": inv["n_presentes"],
                "n_faltantes": inv["n_faltantes"],
                "end_date": end,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    faltantes = inv["faltantes"]
    if args.max_jobs > 0:
        faltantes = faltantes[: args.max_jobs]
    if args.dry_run:
        print("dry-run: próximos", [f["file"] for f in faltantes[:12]])
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    fail = 0
    consecutive_fail = 0
    max_consecutive = 5
    for i, job in enumerate(faltantes, start=1):
        target = cache / job["file"]
        log.info(
            "[%s/%s] CDS %s %s-%s → %s",
            i,
            len(faltantes),
            job["col"],
            job["year"],
            job["month"],
            target.name,
        )
        try:
            months = None if job.get("month") in {None, "", "all"} else [job["month"]]
            download_era5_year_stat(
                job["year"],
                job["statistic"],
                target,
                months=months,
            )
            ok += 1
            consecutive_fail = 0
            PROGRESS.write_text(
                json.dumps(
                    {
                        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_ok": job["file"],
                        "ok": ok,
                        "fail": fail,
                        "restantes_estimado": max(0, inv["n_faltantes"] - ok - fail),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            fail += 1
            consecutive_fail += 1
            log.exception("Falha CDS %s: %s", job["file"], exc)
            PROGRESS.write_text(
                json.dumps(
                    {
                        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "last_fail": job["file"],
                        "error": str(exc)[:500],
                        "ok": ok,
                        "fail": fail,
                        "consecutive_fail": consecutive_fail,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            # Evita queimar a fila inteira em SSL/auth/rede
            if consecutive_fail >= max_consecutive:
                log.error(
                    "Abortando após %s falhas consecutivas (ok=%s fail=%s).",
                    consecutive_fail,
                    ok,
                    fail,
                )
                break
        if args.sleep > 0:
            time.sleep(args.sleep)

    print(json.dumps({"ok": ok, "fail": fail, "solicitados": len(faltantes)}, ensure_ascii=False))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
