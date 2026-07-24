"""Atualiza ocupação hospitalar a partir do IndicaSUS (BdSES / usuário Roney).

Uso:
  .\\.venv\\Scripts\\python.exe atualizar_ocupacao_indicasus.py
  .\\.venv\\Scripts\\python.exe atualizar_ocupacao_indicasus.py --descobrir
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atualiza ocupação IndicaSUS (Roney/BdSES)")
    parser.add_argument(
        "--descobrir",
        action="store_true",
        help="Lista tabelas/views do BdSES e encerra sem gravar",
    )
    args = parser.parse_args(argv)

    from sisclima.core.config import env
    from sisclima.ingestion.indicasus_ocupacao import (
        atualizar_ocupacao_indicasus,
        descobrir_objetos_indicasus,
    )
    from sisclima.ingestion.sqlserver import probe_sqlserver

    # HOST -> SERVER
    if env("INDICASUS_HOST") and not env("INDICASUS_SERVER"):
        import os

        os.environ["INDICASUS_SERVER"] = env("INDICASUS_HOST") or ""

    print("=== IndicaSUS ocupação (usuário Roney / BdSES) ===")
    print(f"HOST={env('INDICASUS_HOST') or env('INDICASUS_SERVER')}")
    print(f"DATABASE={env('INDICASUS_DATABASE')}")
    print(f"USER={env('INDICASUS_USER')}")
    print(f"USE_DW_CREDENTIALS={env('INDICASUS_USE_DW_CREDENTIALS')}")
    print("probe:", probe_sqlserver("INDICASUS"))

    if args.descobrir:
        cat = descobrir_objetos_indicasus()
        if cat is None or cat.empty:
            print("[ERRO] não foi possível listar objetos do BdSES")
            return 2
        print(f"[OK] objetos visíveis: {len(cat)}")
        # Destaca candidatos a ocupação
        upper = cat["TABLE_NAME"].astype(str).str.upper()
        cand = cat[upper.str.contains("OCUP|LEITO|MOVIM|HOSP", regex=True, na=False)]
        print("--- candidatos (OCUP/LEITO/MOVIM/HOSP) ---")
        print((cand if not cand.empty else cat.head(40)).to_string(index=False))
        print(
            "\nPróximo passo: ajuste sql/indicasus_ocupacao_municipio.sql "
            "para a view/tabela correta e rode sem --descobrir."
        )
        return 0

    result = atualizar_ocupacao_indicasus()
    print(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
