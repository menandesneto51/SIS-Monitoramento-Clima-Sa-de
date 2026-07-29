# -*- coding: utf-8 -*-
"""Consolida tabelas do monitoramento saúde-calor + status GeoCalor no Postgres."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from sisclima.core.db import backend_name
    from sisclima.engines.saude_calor_consolida import run_saude_calor_consolidation

    print(f"Backend: {backend_name()}")
    summary = run_saude_calor_consolidation(include_geocalor=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
