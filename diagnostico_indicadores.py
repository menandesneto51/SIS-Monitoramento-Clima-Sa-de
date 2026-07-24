"""Diagnóstico dos indicadores ainda indisponíveis no alerta VIGIA.

Uso:
  .\\.venv\\Scripts\\python.exe diagnostico_indicadores.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sisclima.core.config import ROOT, env, as_bool
from sisclima.core.db import read_table
from sisclima.ingestion.sqlserver import probe_sqlserver, use_sqlserver
from sisclima.ingestion.sivep_local import load_sivep_local
from sisclima.ingestion.dw_sources import (
    load_dw_gal_lacen,
    load_dw_sim_obitos,
    load_dw_sinan_agravos,
)


def _status_df(name: str, df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return f"{name}: VAZIO"
    return f"{name}: OK linhas={len(df)} cols={list(df.columns)[:8]}"


def main() -> int:
    print("=== DIAGNÓSTICO DE INDICADORES ===\n")

    resumo = read_table("resumo_municipal_atual")
    if resumo is None or resumo.empty:
        print("resumo_municipal_atual: VAZIO — rode o pipeline antes.")
    else:
        print(f"resumo_municipal_atual: {len(resumo)} municípios")
        for col in [
            "casos_srag",
            "positividade_lacen_pct",
            "obitos_total",
            "obitos_calor_suspeitos",
            "score_sentinela",
            "iq_ar_score",
            "ocupacao_leitos_pct",
            "atendimentos_total",
            "pressao_calor_pct",
            "autonomia_min_dias",
            "falhas_infra_pct",
            "cobertura_busca_pct",
            "latencia_comunicacao_horas",
        ]:
            if col not in resumo.columns:
                print(f"  - {col}: AUSENTE no resumo")
                continue
            s = pd.to_numeric(resumo[col], errors="coerce")
            nn = int(s.notna().sum())
            nz = int((s.fillna(0) != 0).sum())
            print(f"  - {col}: preenchido={nn}/{len(resumo)} nonzero={nz}")

    print("\n--- Fontes ---")
    print(f"USE_SQLSERVER={use_sqlserver()}")
    if use_sqlserver():
        print("probe DW:", probe_sqlserver("DW"))
        for label, loader in [
            ("DW GAL/LACEN", load_dw_gal_lacen),
            ("DW SIM", load_dw_sim_obitos),
            ("DW SINAN", load_dw_sinan_agravos),
        ]:
            try:
                df = loader()
                print(_status_df(label, df))
            except Exception as exc:
                print(f"{label}: ERRO {exc}")

    try:
        sivep = load_sivep_local()
        print(_status_df("SIVEP local", sivep))
    except Exception as exc:
        print(f"SIVEP local: ERRO {exc}")

    print(f"USE_COPERNICUS={as_bool(env('USE_COPERNICUS'), False)}")
    aq = read_table("qualidade_ar_municipal")
    print(_status_df("qualidade_ar_municipal (sqlite)", aq if aq is not None else pd.DataFrame()))

    print("\n--- CSVs operacionais esperados em data/input ---")
    expected = [
        "estoque_insumos.csv",
        "infraestrutura_unidades.csv",
        "busca_ativa.csv",
        "comunicacao.csv",
        "sentinela_rumores.csv",
        "lacen_gal.csv",
        "sim_obitos.csv",
    ]
    input_dir = ROOT / "data" / "input"
    for name in expected:
        p = input_dir / name
        # também procura qualquer arquivo com stem
        matches = list(input_dir.glob(f"*{name}*")) + list(input_dir.glob(f"*{name.replace('.csv','')}*"))
        if p.exists():
            print(f"  OK {name}")
        elif matches:
            print(f"  PARCIAL {name} -> {[m.name for m in matches[:3]]}")
        else:
            print(f"  AUSENTE {name}")

    sivep_folder = ROOT / (env("SIVEP_UPDATE_FOLDER", "data/input/sivep_atualizacao") or "data/input/sivep_atualizacao")
    nfiles = len([p for p in sivep_folder.glob("*") if p.is_file()]) if sivep_folder.exists() else 0
    print(f"\nSIVEP pasta {sivep_folder}: arquivos={nfiles}")

    print(
        """
=== COMO PREENCHER OS INDISPONÍVEIS ===
1) SRAG: colocar exportações em data/input/sivep_atualizacao/ e rodar pipeline
2) LACEN/SIM/SINAN: validar views DW (sql/dw_gal_lacen_resultados.sql, dw_sim_obitos_calor.sql)
   e USE_DW_GAL=true / USE_DW_SIM=true / USE_DW_SINAN=true
3) IQ ar: USE_COPERNICUS=true + key ADS válida (sem UID:) ou NetCDF local
4) Pressão assistencial: IndicaSUS com atendimentos (script + senha correta no host 10.15.0.222)
5) Estoque/infra/busca/comunicação/sentinela: CSVs em data/input/
"""
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
