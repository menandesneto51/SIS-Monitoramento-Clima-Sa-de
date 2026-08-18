# -*- coding: utf-8 -*-
"""Validação operacional da camada de arboviroses (dengue/zika/chikungunya)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sisclima.engines.epidemiology import (
    arbovirus_municipal_latest,
    arbovirus_summary,
    normalize_agravo_arbovirus,
    sinan_summary,
)
from sisclima.engines.stages import classify_stage
from sisclima.core.config import SETTINGS


def main() -> int:
    print("=== Validação Arboviroses ===")
    assert normalize_agravo_arbovirus("Dengue grave") == "Dengue"
    assert normalize_agravo_arbovirus("Doença pelo vírus Zika") == "Zika"
    assert normalize_agravo_arbovirus("Febre de Chikungunya") == "Chikungunya"

    sample = ROOT / "data" / "input" / "sinan_agravos.csv"
    if not sample.exists():
        sample = ROOT / "data" / "sample" / "sinan_agravos.csv"
    df = pd.read_csv(sample)
    pop_path = ROOT / "data" / "input" / "populacao_municipal_mt_2020_2025.csv"
    pop = pd.read_csv(pop_path) if pop_path.exists() else None

    sinan = sinan_summary(df)
    arbo = arbovirus_summary(df, pop)
    mun = arbovirus_municipal_latest(arbo)
    assert not arbo.empty, "arbovirus_summary vazio"
    assert set(arbo["agravo"]).issubset(
        {"Dengue", "Zika", "Chikungunya", "Febre Amarela", "Oropouche", "Mayaro", "Outras arboviroses"}
    )
    assert not mun.empty, "arbovirus_municipal_latest vazio"
    print(f"OK engine: sinan={len(sinan)} arbo={len(arbo)} mun={len(mun)}")
    print(arbo["agravo"].value_counts().to_string())

    latest = mun.sort_values("casos_arbovirus_7d", ascending=False).iloc[0].to_dict()
    latest.update({"tmax": 38.0, "utci_proxy": 34.0})
    stage = classify_stage(latest, SETTINGS)
    print(f"OK stage sample: nivel={stage.nivel} score={stage.score}")
    assert any("arbo" in m.lower() or "dengue" in m.lower() or "zika" in m.lower() or "chik" in m.lower() for m in stage.motivos)

    db = ROOT / "data" / "output" / "sis_integrado.db"
    if db.exists():
        with sqlite3.connect(db) as con:
            for t in ["epi_arboviroses", "epi_arboviroses_municipal"]:
                n = pd.read_sql(f"SELECT COUNT(*) n FROM {t}", con).iloc[0]["n"]
                print(f"OK sqlite {t}: {n}")
                assert n > 0
    else:
        print("AVISO: banco ainda não gerado (rode o pipeline).")

    print("=== Validação OK ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
