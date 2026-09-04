# -*- coding: utf-8 -*-
"""Exporta a rodada semanal do boletim (CSV + histórico) para validação proj. × obs."""
from __future__ import annotations

import argparse
import json
from datetime import date

from sisclima.reporting.rodada_semanal import export_rodada_semanal


def main() -> int:
    p = argparse.ArgumentParser(description="Export Rodada_Semanal ARARAS (boletim).")
    p.add_argument("--ref", help="Data de referência YYYY-MM-DD (default: hoje)")
    p.add_argument("--out-dir", help="Pasta de saída (default: data/output/boletim)")
    p.add_argument("--no-hist", action="store_true", help="Não gravar hist_boletim_rodada_semanal")
    args = p.parse_args()
    ref = date.fromisoformat(args.ref) if args.ref else None
    out = export_rodada_semanal(
        ref=ref,
        out_dir=args.out_dir,
        persist_hist=not args.no_hist,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("n_municipios") else 1


if __name__ == "__main__":
    raise SystemExit(main())
