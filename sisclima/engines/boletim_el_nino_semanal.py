# -*- coding: utf-8 -*-
"""Relatório semanal El Niño para a sala de situação CIEVS-MT.

Ponto de entrada legado — implementação modular em ``sisclima.engines.boletim_el_nino``.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from sisclima.core.config import ROOT
from sisclima.engines.boletim_el_nino.builder import build_boletim_semanal, save_boletim
from sisclima.engines.boletim_el_nino.cenario import load_cenario_oficial, semana_iso
from sisclima.engines.boletim_el_nino.documento import format_markdown
from sisclima.engines.boletim_el_nino.snapshot import snapshot_operacional

OUT_DIR = ROOT / "docs" / "apresentacoes"
CENARIO_PATH = ROOT / "config" / "painel_el_nino.yaml"

__all__ = [
    "build_boletim_semanal",
    "save_boletim",
    "format_markdown",
    "load_cenario_oficial",
    "semana_iso",
    "snapshot_operacional",
    "CENARIO_PATH",
    "OUT_DIR",
]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Relatório semanal El Niño — sala de situação")
    p.add_argument("--out-dir", default=None, help="Pasta de saída (padrão docs/apresentacoes)")
    p.add_argument("--publico", action="store_true", help="Omite pauta interna da sala")
    p.add_argument("--no-dw", action="store_true", help="Não consultar DW epidemiológico")
    args = p.parse_args(argv)
    from sisclima.core.db import read_table

    resumo = read_table("resumo_municipal_atual")
    out = Path(args.out_dir) if args.out_dir else None
    payload = build_boletim_semanal(resumo, publico=bool(args.publico), try_dw=not args.no_dw, out_dir=out)
    path = save_boletim(payload, out)
    qa = payload.get("qa") or {}
    print(path)
    if qa.get("log"):
        print(qa["log"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
