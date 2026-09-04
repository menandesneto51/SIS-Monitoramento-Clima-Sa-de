"""Passos ETL: e-SUS APS e catálogo STAR/GeoCalor (CDS ERA5 incremental)."""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT, as_bool, env
from sisclima.core.db import init_db, upsert_df, write_df
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def etl_esus_aps() -> dict[str, Any]:
    """Extrai/atualiza agregados e-SUS APS e cruza com classe ARARAS."""
    meta: dict[str, Any] = {"ok": False, "skipped": False}
    if not as_bool(env("USE_ESUS_APS", "false"), False):
        meta["skipped"] = True
        meta["erro"] = "USE_ESUS_APS=false"
        return meta
    try:
        from sisclima.ingestion.esus_aps_clima import (
            NIVEIS_CRITICOS,
            atualizar_esus_aps,
            cruzar_esus_classe_araras,
            persist_municipal,
            persist_prioridade,
        )

        meta = atualizar_esus_aps()
        if not meta.get("ok"):
            full = cruzar_esus_classe_araras(so_criticos=False)
            if full is not None and not full.empty:
                prio = (
                    full[full["classe_araras"].isin(NIVEIS_CRITICOS)].copy()
                    if "classe_araras" in full.columns
                    else full
                )
                meta = {
                    "ok": True,
                    "fallback_cruzar": True,
                    "n_municipal": persist_municipal(full),
                    "n_prioridade": persist_prioridade(prio),
                    "erro_extracao": meta.get("erro"),
                }
        try:
            from sisclima.engines.esus_clima_analise import analisar_esus_clima, cruzar_esus_clima

            cruz = cruzar_esus_clima()
            if cruz is not None and not cruz.empty:
                write_df(cruz, "ops_esus_aps_clima_cruzado")
            analise = analisar_esus_clima(cruz)
            out = ROOT / "data" / "output" / "esus_aps_analise_clima.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(analise, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            meta["analise_ok"] = bool(analise.get("ok"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Análise e-SUS×clima na ETL: %s", exc)
            meta["analise_erro"] = str(exc)
    except Exception as exc:  # noqa: BLE001
        log.warning("ETL e-SUS APS falhou: %s", exc)
        meta["erro"] = str(exc)
    return meta


def etl_star_geocalor() -> dict[str, Any]:
    """Atualiza catálogo STAR/EHF na ETL (janela curta ou cache).

    Carga histórica completa (ex.: 2020–2026) permanece em
    ``scripts/carregar_star_ondas_geocalor.py``.
    """
    meta: dict[str, Any] = {"ok": False, "skipped": False}
    if not as_bool(env("USE_STAR_GEOCALOR", "false"), False):
        meta["skipped"] = True
        meta["erro"] = "USE_STAR_GEOCALOR=false"
        return meta
    try:
        from sisclima.engines.ehf_geocalor import (
            METODOLOGIA,
            colunas_diario_persistencia,
            compute_ehf_geocalor,
            eventos_from_daily,
        )
        from sisclima.ingestion.ibge_municipios import get_municipios_operacionais

        out_dir = ROOT / "data" / "output" / "star"
        cache = out_dir / "STAR_geocalor_clima_bruto.csv"
        days = int(env("STAR_CDS_ETL_DAYS", "60") or 60)
        end = date.today()
        start = end - timedelta(days=max(14, days))
        fonte = (env("STAR_ETL_FONTE", "auto") or "auto").strip().lower()

        bruto = pd.DataFrame()
        if as_bool(env("STAR_ETL_SKIP_FETCH", "false"), False) and cache.exists():
            bruto = pd.read_csv(cache)
            meta["fonte"] = "cache_local"
        elif fonte in {"cds", "auto"}:
            try:
                from sisclima.ingestion.era5_cds import fetch_era5_land_municipal, has_cds_credentials

                use_cds = has_cds_credentials() and fonte in {"cds", "auto"}
                if cache.exists() and fonte == "auto":
                    bruto = pd.read_csv(cache)
                    meta["fonte"] = "cache_local_auto"
                elif use_cds:
                    mun = get_municipios_operacionais()
                    keep = [c for c in ["cod_ibge", "municipio", "lat", "lon"] if c in mun.columns]
                    mun = mun[keep].dropna(subset=["lat", "lon"]).drop_duplicates("cod_ibge")
                    bruto = fetch_era5_land_municipal(
                        mun,
                        start_date=start.isoformat(),
                        end_date=end.isoformat(),
                    )
                    meta["fonte"] = "copernicus_era5_land"
                elif cache.exists():
                    bruto = pd.read_csv(cache)
                    meta["fonte"] = "cache_local_fallback"
            except Exception as exc:  # noqa: BLE001
                log.warning("STAR CDS incremental falhou: %s", exc)
                meta["erro_cds"] = str(exc)
                if cache.exists():
                    bruto = pd.read_csv(cache)
                    meta["fonte"] = "cache_local_apos_erro"
        if bruto.empty and cache.exists():
            bruto = pd.read_csv(cache)
            meta["fonte"] = "cache_local"
        if bruto.empty:
            meta["erro"] = "sem_dados_climaticos_star"
            return meta

        out_dir.mkdir(parents=True, exist_ok=True)
        bruto.to_csv(cache, index=False, encoding="utf-8-sig")
        daily = compute_ehf_geocalor(bruto)
        eventos = eventos_from_daily(daily)
        init_db()
        cols = [c for c in colunas_diario_persistencia() if c in daily.columns]
        n_d = upsert_df(daily[cols], "star_clima_geocalor_diario", ["cod_ibge", "data"]) if cols else 0
        n_e = upsert_df(eventos, "star_ondas_calor_evento", ["cod_ibge", "data_inicio"]) if eventos is not None and not eventos.empty else 0
        hist_cols = [
            c
            for c in ["cod_ibge", "data", "tmax", "tmin", "umidade_media", "precipitacao_mm", "fonte", "atualizado_em"]
            if c in daily.columns
        ]
        n_h = upsert_df(daily[hist_cols], "hist_clima_municipal_diario", ["cod_ibge", "data"]) if hist_cols else 0
        if not daily.empty:
            daily.to_csv(out_dir / "STAR_geocalor_clima_diario.csv", index=False, encoding="utf-8-sig")
        if eventos is not None and not eventos.empty:
            eventos.to_csv(out_dir / "STAR_geocalor_ondas_eventos.csv", index=False, encoding="utf-8-sig")
        payload = {
            "metodologia": METODOLOGIA,
            "janela": [
                str(bruto["data"].min()) if "data" in bruto.columns else start.isoformat(),
                end.isoformat(),
            ],
            "n_municipios": int(daily["cod_ibge"].nunique()) if not daily.empty else 0,
            "n_dias": int(len(daily)),
            "n_eventos": int(len(eventos)) if eventos is not None else 0,
            "n_dias_onda": int(pd.to_numeric(daily.get("is_hw_day"), errors="coerce").fillna(0).sum())
            if not daily.empty and "is_hw_day" in daily.columns
            else 0,
            "persistencia": {"n_diario": n_d, "n_eventos": n_e, "n_hist_clima": n_h},
            "fonte_clima": meta.get("fonte"),
            "etl": True,
        }
        (out_dir / "STAR_geocalor_carga.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        meta["ok"] = True
        meta["persistencia"] = payload["persistencia"]
        meta["n_eventos"] = payload["n_eventos"]
    except Exception as exc:  # noqa: BLE001
        log.warning("ETL STAR/GeoCalor falhou: %s", exc)
        meta["erro"] = str(exc)
    return meta
