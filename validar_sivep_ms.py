# -*- coding: utf-8 -*-
"""Valida cálculo e persistência dos indicadores MS/SIVEP."""
from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(".env"), override=True)

import pandas as pd

from sisclima.core.db import init_db, read_table, write_df
from sisclima.engines.sivep_ms_indicators import catalog_as_dataframe, compute_all_sivep_ms_outputs
from sisclima.ingestion.local_csv import load_csv


def main() -> int:
    cat = catalog_as_dataframe()
    assert not cat.empty and len(cat) >= 10, "Catálogo MS incompleto"
    print("catalog_rows=", len(cat))

    raw = load_csv("sivep_csv", ["data_notificacao", "data_sintomas"])
    if raw.empty:
        raw = pd.read_csv("data/sample/sivep_srag.csv")
    print("raw_rows=", len(raw), "cols=", list(raw.columns)[:12])

    try:
        pop = load_csv("populacao_csv")
    except Exception:
        pop = pd.DataFrame()

    outs = compute_all_sivep_ms_outputs(raw, pop if not pop.empty else None)
    init_db()
    for name, frame in outs.items():
        write_df(frame if frame is not None else pd.DataFrame(), name)
        print(name, 0 if frame is None else len(frame))

    daily = read_table("epi_sivep_srag")
    assert not daily.empty, "epi_sivep_srag vazia"
    for col in ["casos_srag", "letalidade_pct", "prop_uti_pct", "zscore_srag"]:
        assert col in daily.columns, f"faltou {col}"
    weekly = read_table("epi_sivep_se_municipal")
    assert not weekly.empty, "epi_sivep_se_municipal vazia"
    assert "se_label" in weekly.columns
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
