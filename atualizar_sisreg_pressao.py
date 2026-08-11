# -*- coding: utf-8 -*-
"""Atualiza ops_sisreg_municipio a partir do SISREG (live) ou CSV V16."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Atualiza pressão SISREG no ARARAS MT")
    ap.add_argument("--csv-only", action="store_true", help="Não tenta SQL Server; só CSV V16")
    ap.add_argument("--csv", type=str, default="", help="Caminho CSV opcional")
    args = ap.parse_args()

    from sisclima.ingestion.sisreg import atualizar_sisreg

    meta = atualizar_sisreg(
        prefer_live=not args.csv_only,
        csv_path=Path(args.csv) if args.csv else None,
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0 if meta.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
