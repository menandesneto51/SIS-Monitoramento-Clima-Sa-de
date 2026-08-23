# -*- coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.ingestion.sqlserver import read_sqlserver, use_sqlserver

if not use_sqlserver():
    raise SystemExit("USE_SQLSERVER=false")

patterns = ["%INDIC%", "%BdSES%", "%LEITO%", "%OCUP%", "%INTERN%", "%HOSP%", "%AIH%", "%SIH%"]
for pat in patterns:
    df = read_sqlserver(
        "DW",
        f"""
        SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_NAME LIKE '{pat}'
        ORDER BY TABLE_NAME
        """,
    )
    if df is not None and not df.empty:
        print(f"--- {pat} ---")
        print(df.to_string(index=False))

# columns VW_INTERNACAO sample for indicasus-like fields
cols = read_sqlserver(
    "DW",
    """
    SELECT COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA='dbo' AND TABLE_NAME='VW_INTERNACAO'
      AND (COLUMN_NAME LIKE '%Indic%' OR COLUMN_NAME LIKE '%Leito%' OR COLUMN_NAME LIKE '%Ocup%')
    ORDER BY COLUMN_NAME
    """,
)
print("\n=== VW_INTERNACAO cols Indic/Leito/Ocup ===")
print(cols.to_string(index=False) if cols is not None and not cols.empty else "(nenhuma)")
