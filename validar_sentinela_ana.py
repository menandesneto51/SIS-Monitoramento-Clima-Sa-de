# -*- coding: utf-8 -*-
"""Valida sentinela SG + ANA (telemetria + risco hidro seca/cheia)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(".env"), override=False)  # variáveis já exportadas no shell prevalecem


from sisclima.core.db import init_db, read_table, write_df
from sisclima.engines.hidro_risco import compute_hidro_risco_from_ana
from sisclima.engines.sentinela_sg_ms import compute_sentinela_sg_indicators
from sisclima.ingestion.ana_hidroweb import load_ana_bundle
from sisclima.ingestion.local_csv import load_csv


def _report_hidro(hidro: pd.DataFrame, tel: pd.DataFrame) -> None:
    n_est = int(tel["codigo_estacao"].nunique()) if not tel.empty and "codigo_estacao" in tel.columns else 0
    pct_cota = 0.0
    if not tel.empty and "cota_cm" in tel.columns:
        cota = pd.to_numeric(tel["cota_cm"], errors="coerce")
        pct_cota = 100.0 * float(cota.notna().mean()) if len(cota) else 0.0
    print(f"ANA telemetria: leituras={len(tel)} estacoes={n_est} pct_com_cota={pct_cota:.1f}%")
    if hidro is None or hidro.empty:
        print("hidro_risco_municipal: vazio")
        return
    print(f"hidro_risco_municipal: municipios={len(hidro)}")
    if "situacao_hidro" in hidro.columns:
        vc = hidro["situacao_hidro"].astype(str).str.lower().value_counts()
        print("situacao_hidro:", dict(vc))
    if "risco_predominante" in hidro.columns:
        vc = hidro["risco_predominante"].astype(str).value_counts()
        print("risco_predominante:", dict(vc))
    if "cota_cm" in hidro.columns:
        n_cota = int(pd.to_numeric(hidro["cota_cm"], errors="coerce").notna().sum())
        print(f"municipios_com_cota_cm={n_cota}")


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

    ana = {}
    try:
        from sisclima.ingestion.ibge_municipios import get_municipios_operacionais

        mun = get_municipios_operacionais()
        ana = load_ana_bundle(mun if mun is not None and not mun.empty else None)
    except Exception:
        ana = load_ana_bundle()
    for k, v in ana.items():
        write_df(v if v is not None else pd.DataFrame(), k)
        print(k, 0 if v is None else len(v))
    tel = ana.get("ana_telemetria", pd.DataFrame())
    if tel is None:
        tel = pd.DataFrame()
    hidro = compute_hidro_risco_from_ana(tel)
    if hidro is None:
        hidro = pd.DataFrame()
    write_df(hidro, "hidro_risco_municipal")
    _report_hidro(hidro, tel)

    assert not read_table("ana_risco_municipal").empty or not read_table("ana_telemetria").empty
    if not hidro.empty:
        assert "situacao_hidro" in hidro.columns
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
