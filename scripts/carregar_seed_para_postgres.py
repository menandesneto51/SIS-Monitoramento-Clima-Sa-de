# -*- coding: utf-8 -*-
"""Carrega tabelas do seed SQLite Cloud para o Postgres (DATABASE_URL).

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\carregar_seed_para_postgres.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

from exportar_snapshot_cloud import TABLES  # noqa: E402
from sisclima.core.db import get_engine, is_postgres, reset_engine  # noqa: E402


def main() -> int:
    seed = ROOT / "data" / "cloud" / "sis_cloud_seed.db"
    if not seed.exists():
        print(f"[ERRO] seed ausente: {seed}")
        return 1
    reset_engine()
    dst = get_engine(force_refresh=True)
    if not is_postgres(str(dst.url)):
        print("[ERRO] DATABASE_URL não está em Postgres (ainda em fallback SQLite?).")
        print("Suba o DB: docker compose up -d db")
        return 1
    src = create_engine(f"sqlite:///{seed.as_posix()}")
    loaded = []
    skipped = []
    with src.connect() as conn:
        existing = {
            r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        }
        for table in TABLES:
            if table not in existing:
                skipped.append(table)
                continue
            df = pd.read_sql(text(f'SELECT * FROM "{table}"'), conn)
            df.to_sql(table, dst, index=False, if_exists="replace", method="multi", chunksize=500)
            loaded.append((table, len(df)))
    src.dispose()
    print(f"OK Postgres · {len(loaded)} tabelas · ausentes no seed: {len(skipped)}")
    for t, n in loaded[:20]:
        print(f"  {t}: {n}")
    if len(loaded) > 20:
        print(f"  ... +{len(loaded) - 20}")
    return 0 if loaded else 1


if __name__ == "__main__":
    raise SystemExit(main())
