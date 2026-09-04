# -*- coding: utf-8 -*-
"""Carga agregada e-SUS APS x clima (VPN SES).

  .\\.venv\\Scripts\\python.exe scripts\\atualizar_esus_aps.py
  .\\.venv\\Scripts\\python.exe scripts\\atualizar_esus_aps.py --so-cruzar
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.ingestion.esus_aps_clima import (  # noqa: E402
    cruzar_esus_classe_araras,
    persist_municipal,
    persist_prioridade,
    atualizar_esus_aps,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--so-cruzar",
        action="store_true",
        help="Não consulta o Centralizador; cruza tabelas ops já gravadas com a classe ARARAS.",
    )
    args = ap.parse_args()
    if args.so_cruzar:
        from sisclima.ingestion.esus_aps_clima import NIVEIS_CRITICOS

        full = cruzar_esus_classe_araras(so_criticos=False)
        prio = full[full["classe_araras"].isin(NIVEIS_CRITICOS)].copy() if "classe_araras" in full.columns else full
        meta = {
            "ok": True,
            "n_municipal": persist_municipal(full),
            "n_prioridade": persist_prioridade(prio),
        }
    else:
        meta = atualizar_esus_aps()
    print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    return 0 if meta.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
