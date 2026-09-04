"""Carga STAR: clima histórico (CDS ERA5-Land ou Open-Meteo) + ondas EHF (GeoCalor)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from sisclima.core.db import init_db, upsert_df
from sisclima.core.logging_utils import get_logger
from sisclima.engines.ehf_geocalor import (
    METODOLOGIA,
    colunas_diario_persistencia,
    compute_ehf_geocalor,
    eventos_from_daily,
)
from sisclima.ingestion.era5_cds import fetch_era5_land_municipal, has_cds_credentials
from sisclima.ingestion.ibge_municipios import get_municipios_operacionais
from sisclima.ingestion.openmeteo_archive import default_window, fetch_openmeteo_archive_municipios

log = get_logger(__name__)
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "output" / "star"


def _municipios() -> pd.DataFrame:
    mun = get_municipios_operacionais()
    if mun is None or mun.empty:
        raise SystemExit("Catálogo municipal vazio.")
    keep = [c for c in ["cod_ibge", "municipio", "lat", "lon", "regional_saude"] if c in mun.columns]
    return mun[keep].dropna(subset=["lat", "lon"]).drop_duplicates("cod_ibge")


def persistir(daily: pd.DataFrame, eventos: pd.DataFrame) -> dict:
    init_db()
    cols = [c for c in colunas_diario_persistencia() if c in daily.columns]
    n_d = upsert_df(daily[cols], "star_clima_geocalor_diario", ["cod_ibge", "data"])
    n_e = 0
    if eventos is not None and not eventos.empty:
        n_e = upsert_df(eventos, "star_ondas_calor_evento", ["cod_ibge", "data_inicio"])

    hist_cols = [
        c
        for c in ["cod_ibge", "data", "tmax", "tmin", "umidade_media", "precipitacao_mm", "fonte", "atualizado_em"]
        if c in daily.columns
    ]
    n_h = upsert_df(daily[hist_cols], "hist_clima_municipal_diario", ["cod_ibge", "data"]) if hist_cols else 0
    return {"n_diario": n_d, "n_eventos": n_e, "n_hist_clima": n_h}


def exportar(daily: pd.DataFrame, eventos: pd.DataFrame, meta: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not daily.empty:
        daily.to_csv(OUT_DIR / "STAR_geocalor_clima_diario.csv", index=False, encoding="utf-8-sig")
    if eventos is not None and not eventos.empty:
        eventos.to_csv(OUT_DIR / "STAR_geocalor_ondas_eventos.csv", index=False, encoding="utf-8-sig")
        anual = (
            eventos.assign(ano=eventos["data_inicio"].astype(str).str[:4])
            .groupby(["ano", "cod_ibge", "municipio"], dropna=False)
            .agg(
                n_eventos=("data_inicio", "count"),
                dias_onda=("duracao_dias", "sum"),
                ehf_max=("ehf_max", "max"),
            )
            .reset_index()
        )
        anual.to_csv(OUT_DIR / "STAR_geocalor_ondas_anual.csv", index=False, encoding="utf-8-sig")
    (OUT_DIR / "STAR_geocalor_carga.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga STAR de ondas de calor (método GeoCalor / EHF)")
    parser.add_argument("--years", type=int, default=5, help="Anos de arquivo (padrão 5)")
    parser.add_argument("--start-date", type=str, default="", help="Início YYYY-MM-DD")
    parser.add_argument("--end-date", type=str, default="", help="Fim YYYY-MM-DD")
    parser.add_argument("--max-municipios", type=int, default=0)
    parser.add_argument(
        "--fonte",
        choices=("cds", "openmeteo", "auto"),
        default="cds",
        help="Fonte climática: CDS ERA5-Land (padrão), Open-Meteo Archive ou auto",
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Usa CSV já baixado em data/output/star")
    args = parser.parse_args()

    start, end = default_window(args.years)
    if args.start_date:
        start = args.start_date
    if args.end_date:
        end = args.end_date

    fonte = args.fonte
    if fonte == "auto":
        fonte = "cds" if has_cds_credentials() else "openmeteo"

    cache = OUT_DIR / "STAR_geocalor_clima_bruto.csv"
    if args.skip_fetch and cache.exists():
        bruto = pd.read_csv(cache)
        fonte_label = "cache_local"
        log.info("Lendo cache %s (%s linhas)", cache, len(bruto))
    else:
        mun = _municipios()
        max_m = args.max_municipios or None
        if max_m:
            mun = mun.head(max_m)
        log.info("Fonte=%s · %s municípios · %s a %s", fonte, len(mun), start, end)
        if fonte == "cds":
            bruto = fetch_era5_land_municipal(mun, start_date=start, end_date=end)
            fonte_label = "Copernicus CDS ERA5-Land (derived daily statistics)"
        else:
            bruto = fetch_openmeteo_archive_municipios(
                mun,
                start_date=start,
                end_date=end,
                max_municipios=None,
            )
            fonte_label = "Open-Meteo Archive (ERA5)"
        if bruto.empty:
            raise SystemExit(f"Nenhuma linha retornada da fonte {fonte}.")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        bruto.to_csv(cache, index=False, encoding="utf-8-sig")

    daily = compute_ehf_geocalor(bruto)
    eventos = eventos_from_daily(daily)
    stats = persistir(daily, eventos)
    meta = {
        "metodologia": METODOLOGIA,
        "janela": [start, end],
        "n_municipios": int(daily["cod_ibge"].nunique()) if not daily.empty else 0,
        "n_dias": int(len(daily)),
        "n_eventos": int(len(eventos)),
        "n_dias_onda": int(pd.to_numeric(daily.get("is_hw_day"), errors="coerce").fillna(0).sum()) if not daily.empty else 0,
        "persistencia": stats,
        "fonte_clima": fonte_label,
        "nota": (
            "GeoCalor Fiocruz não publica Cuiabá/MT (RMs Centro-Oeste: Brasília, Campo Grande, Goiânia). "
            "Esta carga aplica o mesmo EHF aos 142 municípios de Mato Grosso."
        ),
    }
    exportar(daily, eventos, meta)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
