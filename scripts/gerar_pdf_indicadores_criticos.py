# -*- coding: utf-8 -*-
"""Gera relatório e apresentação dos indicadores críticos do Plano El Niño.

  python scripts/gerar_pdf_indicadores_criticos.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.plano.relatorio_criticos import (  # noqa: E402
    DEFAULT_APRESENTACAO,
    DEFAULT_RELATORIO,
    gerar_pdf_apresentacao_criticos,
    gerar_pdf_relatorio_criticos,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--relatorio", default=str(DEFAULT_RELATORIO))
    parser.add_argument("--apresentacao", default=str(DEFAULT_APRESENTACAO))
    args = parser.parse_args()
    rel = gerar_pdf_relatorio_criticos(Path(args.relatorio))
    apr = gerar_pdf_apresentacao_criticos(Path(args.apresentacao))
    print(f"Relatório: {rel} ({rel.stat().st_size} bytes)")
    print(f"Apresentação: {apr} ({apr.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
