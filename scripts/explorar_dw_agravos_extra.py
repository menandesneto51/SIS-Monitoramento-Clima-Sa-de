# -*- coding: utf-8 -*-
"""Exploração complementar: internações, intox fumaça, tabelas ESUS."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.ingestion.sqlserver import read_sqlserver


def main() -> int:
    cols = read_sqlserver(
        "DW",
        """
        SELECT COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'VW_INTERNACAO'
        ORDER BY ORDINAL_POSITION
        """,
    )
    print("=== VW_INTERNACAO colunas ===")
    for r in cols.itertuples():
        print(f"  {r.COLUMN_NAME} ({r.DATA_TYPE})")
    n = read_sqlserver("DW", "SELECT COUNT(*) AS n FROM dbo.VW_INTERNACAO")
    print(f"linhas: {int(n.iloc[0, 0])}")

    cid_cols = [c for c in cols["COLUMN_NAME"].astype(str) if "CID" in c.upper() or "DIAG" in c.upper()]
    print(f"colunas CID/diagnóstico: {cid_cols}")

    for prefix in ("J30", "J45", "E86", "T67", "I21", "A09", "K52"):
        q = f"""
        SELECT COUNT(*) AS n
        FROM dbo.VW_INTERNACAO
        WHERE (
            CidPrincipal LIKE '{prefix}%'
            OR CidSecundario1 LIKE '{prefix}%'
            OR CidSecundario2 LIKE '{prefix}%'
        )
        """
        try:
            cnt = int(read_sqlserver("DW", q).iloc[0, 0])
            print(f"  internações CID {prefix}*: {cnt}")
        except Exception as exc:
            print(f"  internações CID {prefix}*: erro {exc}")

    print("\n=== Intoxicação fumaça (12 meses) ===")
    q_fumaca = """
    SELECT COUNT(*) AS n
    FROM dbo.VW_SINAN_INTOXICACAOEXOGENA
    WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1
      AND (
            LocalOcorrenciaExposicao LIKE '%fumac%'
         OR LocalOcorrenciaExposicaoOutros LIKE '%fumac%'
         OR CircunstanciaExposicaoContaminacao LIKE '%fumac%'
         OR CircunstanciaExposicaoContaminacaoOutra LIKE '%fumac%'
         OR AgenteToxicoClassificacao LIKE '%fumac%'
         OR AgenteToxicoClassificacaoOutro LIKE '%fumac%'
         OR AgenteToxico1PrincipioAtivo LIKE '%monox%'
         OR AgenteToxico1NomeComercial LIKE '%fumac%'
         OR AgenteToxico2PrincipioAtivo LIKE '%monox%'
         OR AgenteToxico3PrincipioAtivo LIKE '%monox%'
         OR AgenteToxico1PrincipioAtivo LIKE '%dioxido de carbono%'
         OR AgenteToxico1PrincipioAtivo LIKE '%CO %'
      )
    """
    print(f"notificações: {int(read_sqlserver('DW', q_fumaca).iloc[0, 0])}")

    print("\n=== Distribuição agente intox (top 15) ===")
    top = read_sqlserver(
        "DW",
        """
        SELECT TOP 15 AgenteToxicoClassificacao, COUNT(*) AS n
        FROM dbo.VW_SINAN_INTOXICACAOEXOGENA
        WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1
        GROUP BY AgenteToxicoClassificacao
        ORDER BY n DESC
        """,
    )
    print(top.to_string(index=False))

    print("\n=== Objetos dbo (ESUS / INDICASUS / PROCED / AIH) ===")
    for pat in ("%ESUS%", "%INDICASUS%", "%PROCED%", "%NEBUL%", "%AIH%", "%AMBUL%", "%LEITO%"):
        df = read_sqlserver(
            "DW",
            f"""
            SELECT TABLE_NAME, TABLE_TYPE
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME LIKE '{pat}'
            ORDER BY TABLE_NAME
            """,
        )
        if df is not None and not df.empty:
            print(f"\n-- {pat} --")
            print(df.to_string(index=False))

    print("\n=== SINAN extras climáticos (contagem 12m) ===")
    extras = [
        "VW_SINAN_HANTAVIROSE",
        "VW_SINAN_ANIMAISPECONHENTOS",
        "VW_SINAN_FEBREMACULOSA",
        "VW_SINAN_LEISHMANIOSEVISCERAL",
        "VW_SINAN_MENINGITE",
        "VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE",
    ]
    for v in extras:
        try:
            cnt = int(
                read_sqlserver(
                    "DW",
                    f"""
                    SELECT COUNT(*) AS n FROM dbo.[{v}]
                    WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1
                    """,
                ).iloc[0, 0]
            )
            print(f"  {v}: {cnt}")
        except Exception as exc:
            print(f"  {v}: erro {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
