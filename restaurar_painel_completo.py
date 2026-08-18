# -*- coding: utf-8 -*-
"""Restaura clima Open-Meteo + predição 7d + indicadores para todos os municípios do resumo."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env", override=True)


def _centroids_from_geojson() -> pd.DataFrame:
    path = ROOT / "data" / "processed" / "municipios_mt_2025_simplificado.geojson"
    if not path.exists():
        path = ROOT / "data" / "processed" / "municipios_mt_2025.geojson"
    if not path.exists():
        return pd.DataFrame()
    gj = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for feat in gj.get("features") or []:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        cod = str(props.get("CD_MUN") or props.get("cod_ibge") or props.get("codigo_ibge") or "").replace(".0", "")
        nome = props.get("NM_MUN") or props.get("municipio") or props.get("name") or ""
        if len(cod) == 6:
            # try keep as is; IBGE often 7
            pass
        coords = []
        gtype = geom.get("type")
        raw = geom.get("coordinates")
        if gtype == "Polygon" and raw:
            ring = raw[0]
            coords = ring
        elif gtype == "MultiPolygon" and raw:
            ring = raw[0][0]
            coords = ring
        if not coords or not cod:
            continue
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        rows.append(
            {
                "cod_ibge": cod if len(cod) >= 7 else cod,
                "municipio": nome,
                "lon": sum(xs) / len(xs),
                "lat": sum(ys) / len(ys),
            }
        )
    return pd.DataFrame(rows)


def _centroids_from_shapefile() -> pd.DataFrame:
    shp = ROOT / "data" / "geo" / "municipios_mt" / "MT_Municipios_2025.shp"
    if not shp.exists():
        return pd.DataFrame()
    try:
        import geopandas as gpd
    except Exception:
        return pd.DataFrame()
    gdf = gpd.read_file(shp)
    cod_col = next((c for c in ("CD_MUN", "cod_ibge", "COD_IBGE") if c in gdf.columns), None)
    nome_col = next((c for c in ("NM_MUN", "municipio", "NOME") if c in gdf.columns), None)
    if not cod_col:
        return pd.DataFrame()
    cent = gdf.geometry.centroid
    out = pd.DataFrame(
        {
            "cod_ibge": gdf[cod_col].astype(str).str.replace(r"\.0$", "", regex=True),
            "municipio": gdf[nome_col].astype(str) if nome_col else "",
            "lon": cent.x,
            "lat": cent.y,
        }
    )
    return out


def main() -> int:
    from sisclima.core.db import get_engine, read_table, write_df, table_count
    from sisclima.engines.biometeo import add_biometeo_indicators
    from sisclima.engines.soil_saturation import enrich_soil_saturation
    from sisclima.ingestion.openmeteo import fetch_openmeteo_for_municipios
    from sisclima.engines.operational_enrichment import run_operational_enrichment, build_predicao_7d
    from sisclima.engines.prioridade_global import enrich_prioridade_global
    from sisclima.engines.saude_calor_consolida import run_saude_calor_consolidation
    from sisclima.core.config import SETTINGS

    get_engine(force_refresh=True)
    resumo = read_table("resumo_municipal_atual")
    if resumo.empty:
        print("ERRO: resumo_municipal_atual vazio")
        return 1

    geo = _centroids_from_shapefile()
    if geo.empty:
        geo = _centroids_from_geojson()
    print(f"centroids: {len(geo)}")
    if geo.empty:
        print("ERRO: sem geometria municipal")
        return 1

    resumo = resumo.copy()
    resumo["cod_ibge"] = resumo["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    geo["cod_ibge"] = geo["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    # match 6->7
    if geo["cod_ibge"].str.len().median() == 6:
        lookup = resumo[["cod_ibge"]].drop_duplicates()
        lookup["cod6"] = lookup["cod_ibge"].str[:6]
        geo = geo.rename(columns={"cod_ibge": "cod6"}).merge(lookup, on="cod6", how="left")
        geo["cod_ibge"] = geo["cod_ibge"].fillna(geo["cod6"])

    mun = (
        resumo[["cod_ibge", "municipio"]]
        .drop_duplicates("cod_ibge")
        .merge(geo[["cod_ibge", "lat", "lon"]].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
    )
    print(f"munis com lat/lon: {mun[['lat','lon']].notna().all(axis=1).sum()} / {len(mun)}")

    # injeta lat/lon no resumo
    for c in ("lat", "lon"):
        if c in resumo.columns:
            resumo = resumo.drop(columns=[c])
    resumo = resumo.merge(mun[["cod_ibge", "lat", "lon"]], on="cod_ibge", how="left")
    write_df(resumo, "resumo_municipal_atual", if_exists="replace")
    write_df(mun.dropna(subset=["lat", "lon"]), "geo_vulnerabilidade_municipal", if_exists="replace")

    print("Open-Meteo para todos os municípios...")
    t0 = time.time()
    om = fetch_openmeteo_for_municipios(mun.dropna(subset=["lat", "lon"]), days=7)
    print(f"openmeteo rows={len(om)} munis={om['cod_ibge'].nunique() if not om.empty else 0} elapsed={time.time()-t0:.0f}s")
    if om.empty:
        print("ERRO: Open-Meteo vazio")
        return 1

    try:
        om = add_biometeo_indicators(om, SETTINGS if isinstance(SETTINGS, dict) else {})
    except Exception as exc:
        print(f"[AVISO] biometeo: {exc}")
    om = enrich_soil_saturation(om)
    write_df(om, "met_biometeo", if_exists="replace")
    print("met_biometeo", table_count("met_biometeo"))

    pred, pred_reg = build_predicao_7d(om, resumo)
    write_df(pred, "predicao_calor_7d_municipal_v6", if_exists="replace")
    write_df(pred_reg, "predicao_calor_7d_regional_v6", if_exists="replace")
    print("pred_7d", len(pred), "reg", len(pred_reg))

    print("Enriquecimento operacional...")
    summary = run_operational_enrichment(reclassify=True)
    print({k: summary.get(k) for k in ("municipios", "predicao_7d", "alerta_integrado", "com_pressao")})

    print("Saúde-calor + GeoCalor status...")
    print(run_saude_calor_consolidation(include_geocalor=True, try_dw=False))

    # Pressão + prioridade
    from sisclima.engines.indice_pressao_saude import build_indice_pressao_municipal

    resumo = read_table("resumo_municipal_atual")
    pred = read_table("predicao_calor_7d_municipal_v6")
    sis = read_table("ops_sisreg_municipio")
    sim = read_table("sim_obitos_calor_municipal_v6")
    saude = read_table("saude_calor_municipio")
    press = build_indice_pressao_municipal(
        resumo,
        sim_mun=sim if not sim.empty else None,
        saude_calor_mun=saude if not saude.empty else None,
        pred_7d=pred if not pred.empty else None,
        sisreg=sis if not sis.empty else None,
    )
    keep = [c for c in press.columns if c == "cod_ibge" or c.startswith(("kpi_", "indice_pressao", "semaforo_pressao", "pred_indice", "pred_nivel", "tendencia_pressao")) or c == "pilares_disponiveis"]
    write_df(press[keep], "indice_pressao_saude_municipal_v1", if_exists="replace")
    base = resumo.copy()
    drop = [c for c in keep if c != "cod_ibge" and c in base.columns]
    if drop:
        base = base.drop(columns=drop, errors="ignore")
    base["cod_ibge"] = base["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    m = press[keep].copy()
    m["cod_ibge"] = m["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
    base = base.merge(m, on="cod_ibge", how="left")
    base = enrich_prioridade_global(base)
    write_df(base, "resumo_municipal_atual", if_exists="replace")

    print("FINAL resumo", table_count("resumo_municipal_atual"), "pred", table_count("predicao_calor_7d_municipal_v6"), "met munis", read_table("met_biometeo")["cod_ibge"].nunique())
    print("prioridade media", float(pd.to_numeric(base["indice_prioridade_global"], errors="coerce").mean()))
    print("nivel", base["nivel"].value_counts().to_dict() if "nivel" in base.columns else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
