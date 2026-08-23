# -*- coding: utf-8 -*-
"""CLI: busca decretos de emergência no IOMAT (+ imprensa) para o ARARAS MT.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\buscar_decretos_emergencia_araras.py
  .\\.venv\\Scripts\\python.exe scripts\\buscar_decretos_emergencia_araras.py --dias 60 --pages 3
  .\\.venv\\Scripts\\python.exe scripts\\buscar_decretos_emergencia_araras.py --sem-imprensa
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.ingestion.iomat_decretos import run_busca_decretos  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Busca decretos de emergência IOMAT/imprensa (ARARAS MT)")
    p.add_argument("--dias", type=int, default=90, help="Filtrar IOMAT aos últimos N dias (ISO). Default 90.")
    p.add_argument("--pages", type=int, default=None, help="Páginas por termo no IOMAT (default do YAML).")
    p.add_argument("--sem-imprensa", action="store_true", help="Não consultar RSS de imprensa.")
    p.add_argument("--nao-persistir", action="store_true", help="Não gravar no SQLite.")
    args = p.parse_args()

    result = run_busca_decretos(
        dias_retroativos=args.dias,
        pages=args.pages,
        incluir_imprensa=not args.sem_imprensa,
        persistir=not args.nao_persistir,
    )
    if not result.get("ok"):
        print(result.get("motivo") or "Sem resultados.")
        return 1
    print(f"OK: {result['n']} itens (IOMAT={result['n_iomat']}, imprensa={result['n_imprensa']})")
    print(f"Tabela: {result.get('tabela')}")
    print(f"Relatório: {result.get('markdown')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
