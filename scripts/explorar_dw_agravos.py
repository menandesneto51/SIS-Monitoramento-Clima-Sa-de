# -*- coding: utf-8 -*-
"""Explora views do DW SES-MT para mapear fontes de agravos climáticos."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.ingestion.sqlserver import read_sqlserver, use_sqlserver

PATTERNS = [
    "SINAN",
    "ESUS",
    "INDICASUS",
    "SIM",
    "GAL",
    "CNES",
    "SISREG",
    "AMBULATOR",
    "HOSPITAL",
    "INTERN",
    "PROCED",
    "NEBUL",
    "SRAG",
    "SIVEP",
    "DDA",
    "DIARRE",
    "ALERG",
    "INTOX",
    "DENGUE",
    "CHIK",
    "ZIKA",
    "LEITO",
    "BDSES",
    "AIH",
    "CID",
]

KEY_VIEWS = [
    "VW_SINAN_INTOXICACAOEXOGENA",
    "VW_SINAN_DENGUE",
    "VW_SINAN_CHIKUNGUNYA",
    "VW_SINAN_ZIKA",
    "VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE",
    "VW_SINAN_NOTIFICACAOINDIVIDUAL",
    "VW_GAL",
    "SIM",
]


def list_views() -> list[str]:
    like = " OR ".join([f"TABLE_NAME LIKE '%{p}%'" for p in PATTERNS])
    sql = f"""
    SELECT TABLE_NAME
    FROM INFORMATION_SCHEMA.VIEWS
    WHERE TABLE_SCHEMA = 'dbo' AND ({like})
    ORDER BY TABLE_NAME
    """
    df = read_sqlserver("DW", sql)
    if df is None or df.empty:
        return []
    return df["TABLE_NAME"].astype(str).tolist()


def columns_for(view: str) -> list[str]:
    sql = f"""
    SELECT COLUMN_NAME, DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = '{view}'
    ORDER BY ORDINAL_POSITION
    """
    df = read_sqlserver("DW", sql)
    if df is None or df.empty:
        return []
    return [f"{r.COLUMN_NAME} ({r.DATA_TYPE})" for r in df.itertuples(index=False)]


def row_count(view: str) -> int | None:
    try:
        df = read_sqlserver("DW", f"SELECT COUNT(*) AS n FROM dbo.[{view}]")
        if df is not None and not df.empty:
            return int(df.iloc[0, 0])
    except Exception:
        return None
    return None


def sample_top(view: str, n: int = 1):
    try:
        return read_sqlserver("DW", f"SELECT TOP {n} * FROM dbo.[{view}]")
    except Exception as exc:
        return str(exc)


def main() -> int:
    if not use_sqlserver():
        print("USE_SQLSERVER=false — ligue VPN e .env")
        return 1

    views = list_views()
    print(f"=== {len(views)} views encontradas ===")
    for v in views:
        print(v)

    report: dict = {"views": views, "detalhes": {}}
    print("\n=== Detalhe views-chave ===")
    for v in KEY_VIEWS:
        cols = columns_for(v)
        cnt = row_count(v)
        print(f"\n--- {v} ---")
        print(f"linhas: {cnt}")
        print(f"colunas ({len(cols)}):")
        for c in cols:
            print(f"  {c}")
        report["detalhes"][v] = {"linhas": cnt, "colunas": cols}

    # intoxicação: colunas agente/circunstância
    intox_cols = columns_for("VW_SINAN_INTOXICACAOEXOGENA")
    agent_like = [c for c in intox_cols if any(k in c.upper() for k in ("AGENT", "SUBST", "CIRCUN", "LOCAL", "EXPOS", "TOXIC", "FUMAC", "QUEIM"))]
    report["intoxicacao_colunas_relevantes"] = agent_like
    print("\n=== Colunas intoxicação (agente/circunstância) ===")
    for c in agent_like:
        print(c)

    out = ROOT / "docs" / "dw_views_agravos_exploracao.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRelatório salvo: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
