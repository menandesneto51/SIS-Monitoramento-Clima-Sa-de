"""Valida agregação das fontes DW + SISREG + IndicaSUS (usuário Roney).

Uso:
  .\\.venv\\Scripts\\python.exe validar_fontes_dw.py
"""

from __future__ import annotations

import os

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
    load_dw_cnes_estabelecimentos,
    load_dw_cnes_leitos,
    load_dw_cnes_equipamentos,
    load_dw_cnes_equipes,
    load_dw_cnes_profissionais,
)
from sisclima.ingestion.pressao_sources import load_pressao_assistencial_raw, load_dw_sih_internacoes
from sisclima.engines.cnes_ops import aggregate_cnes_municipal


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
        print(f"[OK] {label}: linhas={len(df)} cols={list(df.columns)[:12]}")
        return df
    except Exception as exc:
        print(f"[ERRO] {label}: {exc}")
        return pd.DataFrame()


def main() -> int:
    print("=== VALIDAÇÃO FONTES DW / SISREG / INDICASUS ===\n")
    print(f"USE_SQLSERVER={use_sqlserver()}")
    print(f"DW_HOST/SERVER={env('DW_SERVER') or env('DW_HOST')}")
    print(f"DW_DATABASE={env('DW_DATABASE')}")
    print(f"DW_USER={env('DW_USER')}")
    print(f"SISREG_HOST={env('SISREG_HOST') or env('SISREG_SERVER')}")
    print(f"SISREG_DATABASE={env('SISREG_DATABASE')}")
    print(f"SISREG_USER={env('SISREG_USER')}")
    print(f"INDICASUS_HOST={env('INDICASUS_HOST') or env('INDICASUS_SERVER')}")
    print(f"INDICASUS_DATABASE={env('INDICASUS_DATABASE')}")
    print(f"INDICASUS_USER={env('INDICASUS_USER')}")
    print(f"INDICASUS_PASSWORD={_mask(env('INDICASUS_PASSWORD'))}")
    print()

    print("--- Probe DW (sua senha / Datawarehouse) ---")
    print(probe_sqlserver("DW"))

    print("\n--- Extratores DW (SIM / SINAN / GAL / CNES / SIH) ---")
    sim = _try_load("SIM óbitos (dbo.SIM)", load_dw_sim_obitos)
    sinan = _try_load("SINAN agravos", load_dw_sinan_agravos)
    gal = _try_load("GAL/LACEN (dbo.VW_GAL)", load_dw_gal_lacen)
    cnes_est = _try_load("CNES estabelecimentos", load_dw_cnes_estabelecimentos)
    cnes_lei = _try_load("CNES leitos", load_dw_cnes_leitos)
    cnes_eqp = _try_load("CNES equipamentos", load_dw_cnes_equipamentos)
    cnes_eq = _try_load("CNES equipes AB", load_dw_cnes_equipes)
    cnes_prof = _try_load("CNES profissionais AB", load_dw_cnes_profissionais)
    _try_load("CNES leitos (alias IndicaSUS capacidade)", load_dw_indicasus_leitos)
    sih = _try_load("SIH VW_INTERNACAO (pressão fallback DW)", load_dw_sih_internacoes)

    ops = aggregate_cnes_municipal(cnes_est, cnes_lei, cnes_eqp, cnes_eq, cnes_prof)
    if ops.empty:
        print("[VAZIO] agregação CNES municipal")
    else:
        print(f"[OK] agregação CNES municipal: {len(ops)} municípios | índice médio={ops['indice_capacidade_cnes'].mean():.1f}")

    print("\n--- Probe SISREG (pressão) ---")
    if env("SISREG_HOST") and not env("SISREG_SERVER"):
        os.environ["SISREG_SERVER"] = env("SISREG_HOST") or ""
    print(probe_sqlserver("SISREG"))
    press = _try_load("Pressão (SISREG→SIH)", load_pressao_assistencial_raw)
    if not press.empty and "fonte_pressao" in press.columns:
        print("fonte_pressao:", press["fonte_pressao"].dropna().astype(str).head(1).tolist())

    print("\n--- Probe IndicaSUS dedicado (ocupação / usuário Roney / BdSES) ---")
    if env("INDICASUS_HOST") and not env("INDICASUS_SERVER"):
        os.environ["INDICASUS_SERVER"] = env("INDICASUS_HOST") or ""
    print(probe_sqlserver("INDICASUS"))
    conn_i = build_sqlserver_conn("INDICASUS")
    if conn_i:
        print("conn INDICASUS:", conn_i.split("PWD=")[0] + "PWD=***")
        try:
            df = read_sqlserver(
                "INDICASUS",
                "SELECT TOP 40 TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_TYPE IN ('BASE TABLE','VIEW') "
                "AND (TABLE_NAME LIKE '%OCUP%' OR TABLE_NAME LIKE '%LEITO%' "
                " OR TABLE_NAME LIKE '%MOVIM%' OR TABLE_NAME LIKE '%HOSP%') "
                "ORDER BY TABLE_NAME",
            )
            print(f"[OK] candidatos ocupação IndicaSUS: {len(df)}")
            if not df.empty:
                print(df.to_string(index=False))
            else:
                print("(nenhum nome com OCUP/LEITO/MOVIM/HOSP — rode atualizar_ocupacao_indicasus.py --descobrir)")
        except Exception as exc:
            print(f"[ERRO] listar tabelas IndicaSUS: {exc}")
    else:
        print("[ERRO] string de conexão INDICASUS não montada — confira HOST/DB/USER/PASSWORD do Roney")

    print(
        """
=== Mapa de senhas ===
DW (sua senha)     → SIM, SINAN, GAL, CNES_*, VW_INTERNACAO, VW_GAL
SISREG             → pressão (solicitações/regulação) se USE_SISREG=true
IndicaSUS (Roney)  → ocupação de leitos em tempo real (BdSES)
SIVEP local        → SRAG (não usa DW neste fluxo)

.env mínimo:
USE_SQLSERVER=true
USE_DW_SIM=true
USE_DW_SINAN=true
USE_DW_GAL=true
USE_DW_CNES=true
USE_DW_SIH=true
USE_SISREG=true
INDICASUS_USE_DW_CREDENTIALS=false
USE_INDICASUS_OCCUPANCY_SCRIPT=true
USE_SIVEP_LOCAL=true
"""
    )

    ok_dw = any(not x.empty for x in (sim, sinan, gal, cnes_est, cnes_lei, sih, ops))
    return 0 if ok_dw else 2


if __name__ == "__main__":
    raise SystemExit(main())
