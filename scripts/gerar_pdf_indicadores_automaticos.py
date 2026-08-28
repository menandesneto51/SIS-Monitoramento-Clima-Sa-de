# -*- coding: utf-8 -*-
"""Gera o PDF da coleta dos indicadores automáticos do Plano El Niño.

  python scripts/gerar_pdf_indicadores_automaticos.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.plano.relatorio_pdf import DEFAULT_OUT, gerar_pdf_indicadores_automaticos  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    path = gerar_pdf_indicadores_automaticos(Path(args.out))
    print(f"PDF: {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
