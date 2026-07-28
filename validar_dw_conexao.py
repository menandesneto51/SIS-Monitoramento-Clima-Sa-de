# -*- coding: utf-8 -*-
"""Valida conexão com o DW SQL Server e a base operacional única."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sisclima.core.config import env, as_bool
from sisclima.core.db import backend_name, init_db, table_exists, get_engine
from sisclima.ingestion.sqlserver import build_sqlserver_conn, read_sqlserver, use_sqlserver


def main() -> int:
    print("=== Validação DW + Base Única ===")
    print(f"Base operacional: {backend_name()}")
    print(f"DATABASE_URL driver: {(env('DATABASE_URL') or '')[:48]}...")

    ok = True
    try:
        init_db()
        eng = get_engine()
        with eng.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        print("OK base operacional respondendo")
        for t in ["pipeline_runs", "nivel_atual", "alertas_enviados"]:
            print(f"  tabela {t}: {'ok' if table_exists(t) else 'ausente'}")
    except Exception as e:
        ok = False
        print(f"FALHA base operacional: {e}")

    print(f"\nUSE_SQLSERVER={use_sqlserver()}")
    if use_sqlserver():
        conn_str = build_sqlserver_conn("DW")
        if not conn_str:
            ok = False
            print("FALHA: DW_SERVER/DW_DATABASE/DW_USER/DW_PASSWORD incompletos")
        else:
            print(f"DW_SERVER={env('DW_SERVER')}")
            print(f"DW_DATABASE={env('DW_DATABASE')}")
            print(f"DW_DRIVER={env('DW_DRIVER') or 'ODBC Driver 17/18 for SQL Server'}")
            df = read_sqlserver("DW", "SELECT 1 AS ok")
            if df.empty:
                ok = False
                print("FALHA: não foi possível executar SELECT 1 no DW (rede/credencial/driver)")
            else:
                print("OK DW SQL Server respondendo")

            # Smoke das principais views (não falha o script se a view não existir)
            probes = {
                "SINAN dengue": "SELECT TOP 1 * FROM dbo.VW_SINAN_DENGUE",
                "SINAN notificação": "SELECT TOP 1 * FROM dbo.VW_SINAN_NOTIFICACAOINDIVIDUAL",
                "GAL": "SELECT TOP 1 * FROM dbo.VW_GAL",
            }
            for name, sql in probes.items():
                sample = read_sqlserver("DW", sql)
                status = "ok" if not sample.empty else "indisponível/sem retorno"
                print(f"  probe {name}: {status}")
    else:
        print("DW desligado (USE_SQLSERVER=false). Pipeline usará CSV locais.")

    print("=== FIM ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
