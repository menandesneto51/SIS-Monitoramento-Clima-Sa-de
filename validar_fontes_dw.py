"""Valida agregação das fontes DW + IndicaSUS (usuário Roney).

Uso:
  .\\.venv\\Scripts\\python.exe validar_fontes_dw.py
"""

from __future__ import annotations

import pandas as pd

from sisclima.core.config import env
from sisclima.ingestion.sqlserver import (
    build_sqlserver_conn,
    probe_sqlserver,
    read_sqlserver,
    use_sqlserver,
)
from sisclima.ingestion.dw_sources import (
    load_dw_gal_lacen,
    load_dw_sim_obitos,
    load_dw_sinan_agravos,
    load_dw_indicasus_leitos,
)


def _mask(v: str | None) -> str:
    if not v:
        return "(vazio)"
    if len(v) <= 4:
        return "***"
    return v[:2] + "***" + v[-2:]


def _try_load(label: str, fn) -> pd.DataFrame:
    try:
        df = fn()
        if df is None or df.empty:
            print(f"[VAZIO] {label}")
            return pd.DataFrame()
        print(f"[OK] {label}: linhas={len(df)} cols={list(df.columns)[:10]}")
        return df
    except Exception as exc:
        print(f"[ERRO] {label}: {exc}")
        return pd.DataFrame()


def main() -> int:
    print("=== VALIDAÇÃO FONTES DW / INDICASUS ===\n")
    print(f"USE_SQLSERVER={use_sqlserver()}")
    print(f"DW_HOST/SERVER={env('DW_SERVER') or env('DW_HOST')}")
    print(f"DW_DATABASE={env('DW_DATABASE')}")
    print(f"DW_USER={env('DW_USER')}")
    print(f"INDICASUS_HOST={env('INDICASUS_HOST') or env('INDICASUS_SERVER')}")
    print(f"INDICASUS_DATABASE={env('INDICASUS_DATABASE')}")
    print(f"INDICASUS_USER={env('INDICASUS_USER')}")
    print(f"INDICASUS_PASSWORD={_mask(env('INDICASUS_PASSWORD'))}")
    print(f"INDICASUS_ENCRYPT={env('INDICASUS_ENCRYPT') or env('DW_ENCRYPT') or 'no'}")
    print(
        "INDICASUS_TRUST_SERVER_CERTIFICATE="
        f"{env('INDICASUS_TRUST_SERVER_CERTIFICATE') or env('DW_TRUST_SERVER_CERTIFICATE') or 'yes'}"
    )
    print()

    print("--- Probe DW (Datawarehouse) ---")
    print(probe_sqlserver("DW"))
    print("conn DW (sem senha):", (build_sqlserver_conn("DW") or "").split("PWD=")[0] + "PWD=***")

    print("\n--- Extratores DW (SIM / SINAN / GAL / CNES-IndicaSUS view) ---")
    sim = _try_load("SIM óbitos (dbo.SIM)", load_dw_sim_obitos)
    sinan = _try_load("SINAN agravos", load_dw_sinan_agravos)
    gal = _try_load("GAL/LACEN (dbo.VW_GAL)", load_dw_gal_lacen)
    cnes = _try_load("CNES leitos via DW", load_dw_indicasus_leitos)

    print("\n--- Probe IndicaSUS dedicado (usuário Roney / BdSES) ---")
    # Garante aliases HOST->SERVER para o prefixo INDICASUS
    if env("INDICASUS_HOST") and not env("INDICASUS_SERVER"):
        import os

        os.environ["INDICASUS_SERVER"] = env("INDICASUS_HOST") or ""
    print(probe_sqlserver("INDICASUS"))
    conn_i = build_sqlserver_conn("INDICASUS")
    if conn_i:
        print("conn INDICASUS:", conn_i.split("PWD=")[0] + "PWD=***")
        # Teste mínimo de listagem de tabelas
        try:
            df = read_sqlserver(
                "INDICASUS",
                "SELECT TOP 20 TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME",
            )
            print(f"[OK] tabelas IndicaSUS visíveis: {len(df)}")
            if not df.empty:
                print(df.head(20).to_string(index=False))
        except Exception as exc:
            print(f"[ERRO] listar tabelas IndicaSUS: {exc}")
    else:
        print("[ERRO] string de conexão INDICASUS não montada — confira HOST/DB/USER/PASSWORD")

    print(
        """
=== .env recomendado (Roney no IndicaSUS; DW para SIM/SINAN/GAL) ===
USE_SQLSERVER=true
USE_DW_SIM=true
USE_DW_SINAN=true
USE_DW_GAL=true
USE_DW_INDICASUS=true
USE_DW_CNES=true

# DW institucional
DW_HOST=10.15.1.50
DW_DATABASE=Datawarehouse
DW_USER=menandes_cievs
DW_PASSWORD=****
DW_ENCRYPT=no
DW_TRUST_SERVER_CERTIFICATE=yes

# IndicaSUS tempo real (usuário Roney)
INDICASUS_HOST=10.15.0.222
INDICASUS_SERVER=10.15.0.222
INDICASUS_DATABASE=BdSES
INDICASUS_USER=roneydamaceno
INDICASUS_PASSWORD=****senha_do_roney****
INDICASUS_ENCRYPT=no
INDICASUS_TRUST_SERVER_CERTIFICATE=yes
INDICASUS_USE_DW_CREDENTIALS=false
USE_INDICASUS_OCCUPANCY_SCRIPT=true

# SRAG continua local (sem SIVEP no DW neste fluxo)
USE_SIVEP_LOCAL=true
"""
    )

    ok_dw = any(not x.empty for x in (sim, sinan, gal, cnes))
    return 0 if ok_dw else 2


if __name__ == "__main__":
    raise SystemExit(main())
