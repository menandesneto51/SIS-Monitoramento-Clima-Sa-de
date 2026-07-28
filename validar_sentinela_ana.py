# -*- coding: utf-8 -*-
"""Valida sentinela SG + ANA."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=True)

from sisclima.core.db import init_db, read_table, write_df
from sisclima.engines.sentinela_sg_ms import compute_sentinela_sg_indicators
from sisclima.ingestion.ana_hidroweb import load_ana_bundle
from sisclima.ingestion.local_csv import load_csv


def main() -> int:
    init_db()
    agg = load_csv("sentinela_sg_agregado_csv", [])
    ams = load_csv("sentinela_sg_amostras_csv", [])
    print("agregado", len(agg), "amostras", len(ams))
    outs = compute_sentinela_sg_indicators(agg, ams)
    for k, v in outs.items():
        write_df(v, k)
        print(k, len(v))
    assert not outs["epi_sentinela_sg_indicadores"].empty
    assert "SG-10" in set(outs["epi_sentinela_sg_indicadores"]["indicador_id"])

    ana = load_ana_bundle()
    for k, v in ana.items():
        write_df(v if v is not None else __import__("pandas").DataFrame(), k)
        print(k, 0 if v is None else len(v))
    assert not read_table("ana_risco_municipal").empty or not read_table("ana_telemetria").empty
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
