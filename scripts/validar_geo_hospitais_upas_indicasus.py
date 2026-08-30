# -*- coding: utf-8 -*-
"""Validação de geolocalização de hospitais e UPAs cadastrados no IndicaSUS/BdSES."""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=True)

from atualizar_ocupacao_indicasus import conectar_indicasus
from sisclima.core.db import read_table, table_exists
from sisclima.ingestion.cnes_geo import _LAT_MAX, _LAT_MIN, _LON_MAX, _LON_MIN, coords_validas_mt

OUT_DIR = ROOT / "data" / "output" / "validacao_geo_indicasus"

# Bounding box MT (mesmo do cnes_geo)
MT_LAT = (_LAT_MIN, _LAT_MAX)
MT_LON = (_LON_MIN, _LON_MAX)

# Distância máxima aceitável ao centroide municipal (km) antes de marcar suspeito.
# Municípios grandes (ex.: Cuiabá) ultrapassam 40 km com pontos urbanos válidos.
LIMIAR_KM_CENTROIDE = 80.0


def _haversine_km(lat1, lon1, lat2, lon2) -> float | None:
    try:
        la1, lo1, la2, lo2 = map(float, (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return None
    if any(math.isnan(x) for x in (la1, lo1, la2, lo2)):
        return None
    r = 6371.0
    p1, p2 = math.radians(la1), math.radians(la2)
    dp = math.radians(la2 - la1)
    dl = math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _ibge6(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str.extract(r"(\d{6,7})", expand=False).str.slice(0, 6)


def _norm_cnes(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\D", "", regex=True).str.zfill(7)


def _classificar_nome(nome: str) -> str:
    t = str(nome or "").casefold()
    if re.search(r"\bupa\b|pronto\s+atend|pronto.?socorro(?!\s+hospital)", t):
        return "UPA_PA"
    if re.search(r"hospital|maternidade|pronto.?socorro hospital", t):
        return "Hospital"
    return "Outro"


SQL_HOSP_UPA = r"""
SELECT
    h.FormHospitalId AS unidade_id,
    h.Nome AS nome,
    h.TipoUnidadeSaude AS tipo_cadastro,
    h.CNes AS cnes,
    h.LocalidadeId AS localidade_hospital,
    h.Natureza,
    h.EsferaAdministrativa,
    h.AtendeSUS,
    us.UnidadeSaudeId,
    us.NomeUnidade AS nome_unidade_saude,
    us.LocalidadeId AS localidade_unidade_saude,
    us.Latitude AS lat_unidade_saude,
    us.Longitude AS lon_unidade_saude,
    us.HtmlMaps,
    COALESCE(
        l0h.CodigoIBGE, l1h.CodigoIBGE, l2h.CodigoIBGE, l3h.CodigoIBGE, l4h.CodigoIBGE
    ) AS cod_ibge_6_hospital,
    COALESCE(
        CASE WHEN l0h.CodigoIBGE IS NOT NULL THEN l0h.Nome END,
        CASE WHEN l1h.CodigoIBGE IS NOT NULL THEN l1h.Nome END,
        CASE WHEN l2h.CodigoIBGE IS NOT NULL THEN l2h.Nome END,
        CASE WHEN l3h.CodigoIBGE IS NOT NULL THEN l3h.Nome END,
        CASE WHEN l4h.CodigoIBGE IS NOT NULL THEN l4h.Nome END
    ) AS municipio_hospital,
    COALESCE(
        l0u.CodigoIBGE, l1u.CodigoIBGE, l2u.CodigoIBGE, l3u.CodigoIBGE, l4u.CodigoIBGE
    ) AS cod_ibge_6_unidade_saude,
    COALESCE(
        CASE WHEN l0u.CodigoIBGE IS NOT NULL THEN l0u.Nome END,
        CASE WHEN l1u.CodigoIBGE IS NOT NULL THEN l1u.Nome END,
        CASE WHEN l2u.CodigoIBGE IS NOT NULL THEN l2u.Nome END,
        CASE WHEN l3u.CodigoIBGE IS NOT NULL THEN l3u.Nome END,
        CASE WHEN l4u.CodigoIBGE IS NOT NULL THEN l4u.Nome END
    ) AS municipio_unidade_saude
FROM form.Hospital h
LEFT JOIN dbo.UnidadeSaude us
    ON us.UnidadeSaudeId = h.FormHospitalId AND ISNULL(us.Excluido, 0) = 0
LEFT JOIN dbo.Localidade l0h ON l0h.LocalidadeId = h.LocalidadeId
LEFT JOIN dbo.Localidade l1h ON l1h.LocalidadeId = l0h.PaiLocalidadeId
LEFT JOIN dbo.Localidade l2h ON l2h.LocalidadeId = l1h.PaiLocalidadeId
LEFT JOIN dbo.Localidade l3h ON l3h.LocalidadeId = l2h.PaiLocalidadeId
LEFT JOIN dbo.Localidade l4h ON l4h.LocalidadeId = l3h.PaiLocalidadeId
LEFT JOIN dbo.Localidade l0u ON l0u.LocalidadeId = us.LocalidadeId
LEFT JOIN dbo.Localidade l1u ON l1u.LocalidadeId = l0u.PaiLocalidadeId
LEFT JOIN dbo.Localidade l2u ON l2u.LocalidadeId = l1u.PaiLocalidadeId
LEFT JOIN dbo.Localidade l3u ON l3u.LocalidadeId = l2u.PaiLocalidadeId
LEFT JOIN dbo.Localidade l4u ON l4u.LocalidadeId = l3u.PaiLocalidadeId
WHERE ISNULL(h.Excluido, 0) = 0
  AND (
        h.TipoUnidadeSaude IN (N'Hospital', N'UPA')
     OR h.Nome LIKE N'%HOSPITAL%'
     OR h.Nome LIKE N'%UPA%'
     OR h.Nome LIKE N'%PRONTO ATEND%'
     OR h.Nome LIKE N'%MATERNIDADE%'
  )
"""


def carregar_indicasus() -> pd.DataFrame:
    con = conectar_indicasus()
    df = pd.read_sql(SQL_HOSP_UPA, con)
    try:
        con.close()
    except Exception:
        pass
    return df


def enriquecer(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["grupo"] = out.apply(
        lambda r: r["tipo_cadastro"]
        if str(r.get("tipo_cadastro") or "") in {"Hospital", "UPA"}
        else _classificar_nome(r.get("nome")),
        axis=1,
    )
    out.loc[out["grupo"].isin(["UPA_PA"]), "grupo"] = "UPA"
    out = out[out["grupo"].isin(["Hospital", "UPA"])].copy()

    out["cod_ibge_6"] = _ibge6(out["cod_ibge_6_hospital"].fillna(out["cod_ibge_6_unidade_saude"]))
    out["municipio"] = out["municipio_hospital"].fillna(out["municipio_unidade_saude"])
    out["cnes_norm"] = _norm_cnes(out["cnes"])

    # Coordenada preferencial: UnidadeSaude com mesmo Id (quando existe)
    out["lat_indicasus"] = pd.to_numeric(out["lat_unidade_saude"], errors="coerce")
    out["lon_indicasus"] = pd.to_numeric(out["lon_unidade_saude"], errors="coerce")

    # Cruzar CNES operacional
    cnes = pd.DataFrame()
    if table_exists("cnes_unidades_geo"):
        cnes = read_table("cnes_unidades_geo")
    if cnes is not None and not cnes.empty:
        c = cnes.copy()
        cnes_col = next((x for x in ("cnes", "codigo_cnes", "CNES") if x in c.columns), None)
        lat_col = next((x for x in ("lat", "latitude", "Latitude") if x in c.columns), None)
        lon_col = next((x for x in ("lon", "longitude", "Longitude") if x in c.columns), None)
        if cnes_col and lat_col and lon_col:
            c["cnes_norm"] = _norm_cnes(c[cnes_col])
            c["lat_cnes"] = pd.to_numeric(c[lat_col], errors="coerce")
            c["lon_cnes"] = pd.to_numeric(c[lon_col], errors="coerce")
            keep = ["cnes_norm", "lat_cnes", "lon_cnes"]
            if "fonte" in c.columns:
                keep.append("fonte")
                c = c.rename(columns={"fonte": "fonte_cnes"})
                keep[-1] = "fonte_cnes"
            if "grupo_tipo" in c.columns:
                keep.append("grupo_tipo")
            c = c[keep].drop_duplicates("cnes_norm")
            out = out.merge(c, on="cnes_norm", how="left")
        else:
            out["lat_cnes"] = pd.NA
            out["lon_cnes"] = pd.NA
    else:
        out["lat_cnes"] = pd.NA
        out["lon_cnes"] = pd.NA

    # Centroide municipal do resumo
    resumo = read_table("resumo_municipal_atual") if table_exists("resumo_municipal_atual") else pd.DataFrame()
    if resumo is not None and not resumo.empty:
        r = resumo.copy()
        r["cod_ibge_6"] = _ibge6(r["cod_ibge"] if "cod_ibge" in r.columns else pd.Series(dtype=str))
        lat_r = next((x for x in ("lat", "latitude", "centroid_lat", "y") if x in r.columns), None)
        lon_r = next((x for x in ("lon", "longitude", "centroid_lon", "x") if x in r.columns), None)
        # geojson malha often has lat/lon
        if lat_r and lon_r:
            rc = r[["cod_ibge_6", lat_r, lon_r]].dropna(subset=["cod_ibge_6"]).drop_duplicates("cod_ibge_6")
            rc = rc.rename(columns={lat_r: "lat_centroid", lon_r: "lon_centroid"})
            rc["lat_centroid"] = pd.to_numeric(rc["lat_centroid"], errors="coerce")
            rc["lon_centroid"] = pd.to_numeric(rc["lon_centroid"], errors="coerce")
            out = out.merge(rc, on="cod_ibge_6", how="left")
        else:
            out["lat_centroid"] = pd.NA
            out["lon_centroid"] = pd.NA
        nome_r = next((x for x in ("municipio", "municipio_base") if x in r.columns), None)
        if nome_r:
            nm = r[["cod_ibge_6", nome_r]].dropna(subset=["cod_ibge_6"]).drop_duplicates("cod_ibge_6")
            nm = nm.rename(columns={nome_r: "municipio_araras"})
            out = out.merge(nm, on="cod_ibge_6", how="left")
            out["municipio"] = out["municipio_araras"].fillna(out["municipio"])
    else:
        out["lat_centroid"] = pd.NA
        out["lon_centroid"] = pd.NA

    # Colisão Id Hospital × UnidadeSaude (municípios diferentes) — antes de escolher coord
    ibge_h = _ibge6(out["cod_ibge_6_hospital"])
    ibge_u = _ibge6(out["cod_ibge_6_unidade_saude"])
    out["flag_colisao_id"] = (
        out["UnidadeSaudeId"].notna()
        & ibge_h.notna()
        & ibge_u.notna()
        & (ibge_h != ibge_u)
    )

    # Coordenada final:
    # 1) UnidadeSaude só se NÃO houver colisão de município
    # 2) senão CNES operacional
    # (não inventar centroide como coordenada oficial)
    out["lat"] = pd.NA
    out["lon"] = pd.NA
    out["fonte_coord"] = pd.NA
    mask_us = (
        ~out["flag_colisao_id"]
        & out["lat_indicasus"].notna()
        & out["lon_indicasus"].notna()
    )
    out.loc[mask_us, "lat"] = out.loc[mask_us, "lat_indicasus"]
    out.loc[mask_us, "lon"] = out.loc[mask_us, "lon_indicasus"]
    out.loc[mask_us, "fonte_coord"] = "UnidadeSaude_IndicaSUS"

    mask_cnes = out["lat"].isna() & out["lat_cnes"].notna() & out["lon_cnes"].notna()
    out.loc[mask_cnes, "lat"] = out.loc[mask_cnes, "lat_cnes"]
    out.loc[mask_cnes, "lon"] = out.loc[mask_cnes, "lon_cnes"]
    if "fonte_cnes" in out.columns:
        out.loc[mask_cnes, "fonte_coord"] = out.loc[mask_cnes, "fonte_cnes"].fillna("CNES_operacional")
    else:
        out.loc[mask_cnes, "fonte_coord"] = "CNES_operacional"

    out["flag_coord_indicasus_descartada_colisao"] = out["flag_colisao_id"] & out["lat_indicasus"].notna()

    # Corrige lat/lon invertidos
    swapped = out["lat"].between(MT_LON[0], MT_LON[1]) & out["lon"].between(MT_LAT[0], MT_LAT[1])
    out["flag_lat_lon_invertidos"] = False
    out.loc[swapped, ["lat", "lon"]] = out.loc[swapped, ["lon", "lat"]].to_numpy()
    out.loc[swapped, "flag_lat_lon_invertidos"] = True

    out["coord_ok_mt"] = coords_validas_mt(out["lat"], out["lon"])
    out["tem_coord"] = out["lat"].notna() & out["lon"].notna()
    out["sem_coord"] = ~out["tem_coord"]
    out["fora_mt"] = out["tem_coord"] & ~out["coord_ok_mt"]

    # Distância ao centroide
    dists = []
    for _, r in out.iterrows():
        dists.append(_haversine_km(r.get("lat"), r.get("lon"), r.get("lat_centroid"), r.get("lon_centroid")))
    out["dist_centroide_km"] = dists
    out["longe_centroide"] = out["dist_centroide_km"].notna() & (out["dist_centroide_km"] > LIMIAR_KM_CENTROIDE)

    # Sem localidade / sem IBGE
    out["sem_ibge"] = out["cod_ibge_6"].isna()
    out["sem_cnes"] = out["cnes_norm"].isna() | (out["cnes_norm"].str.replace("0", "", regex=False) == "")

    # Status consolidado (prioridade)
    def _status(r) -> str:
        if bool(r["flag_colisao_id"]) and bool(r["sem_coord"]):
            return "COLISAO_ID_SEM_COORD_CONFIAVEL"
        if bool(r["flag_colisao_id"]) and bool(r["tem_coord"]):
            # Coordenada veio do CNES após descartar UnidadeSaude errada
            if bool(r["longe_centroide"]):
                return "COLISAO_ID_COORD_CNES_LONGE"
            return "COLISAO_ID_COORD_CNES_OK"
        if bool(r["sem_ibge"]):
            return "SEM_IBGE"
        if bool(r["sem_coord"]):
            return "SEM_COORDENADA"
        if bool(r["fora_mt"]):
            return "FORA_MT"
        if bool(r["longe_centroide"]):
            return "LONGE_CENTROIDE"
        return "OK"

    out["status_geo"] = out.apply(_status, axis=1)
    # Para totais "problemas": tudo que não é OK nem COLISAO_ID_COORD_CNES_OK
    out["problema"] = ~out["status_geo"].isin(["OK", "COLISAO_ID_COORD_CNES_OK"])
    return out


def gerar_relatorio(df: pd.DataFrame) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    cols = [
        "unidade_id",
        "nome",
        "grupo",
        "tipo_cadastro",
        "cnes",
        "cnes_norm",
        "municipio",
        "cod_ibge_6",
        "lat",
        "lon",
        "fonte_coord",
        "lat_indicasus",
        "lon_indicasus",
        "lat_cnes",
        "lon_cnes",
        "dist_centroide_km",
        "status_geo",
        "problema",
        "flag_colisao_id",
        "flag_coord_indicasus_descartada_colisao",
        "flag_lat_lon_invertidos",
        "sem_coord",
        "fora_mt",
        "longe_centroide",
        "sem_ibge",
        "sem_cnes",
        "localidade_hospital",
        "localidade_unidade_saude",
        "municipio_hospital",
        "municipio_unidade_saude",
        "nome_unidade_saude",
    ]
    cols = [c for c in cols if c in df.columns]
    detalhe = df[cols].sort_values(["problema", "status_geo", "grupo", "municipio", "nome"], ascending=[False, True, True, True, True])

    path_all = OUT_DIR / "geo_hospitais_upas_indicasus.csv"
    path_ts = OUT_DIR / f"geo_hospitais_upas_indicasus_{ts}.csv"
    path_prob = OUT_DIR / "geo_hospitais_upas_problemas.csv"
    detalhe.to_csv(path_all, index=False, encoding="utf-8-sig")
    detalhe.to_csv(path_ts, index=False, encoding="utf-8-sig")
    probs = detalhe.loc[detalhe["problema"] == True]  # noqa: E712
    probs.to_csv(path_prob, index=False, encoding="utf-8-sig")

    resumo_status = detalhe["status_geo"].value_counts(dropna=False).to_dict()
    detalhe2 = df.copy()
    by_g = []
    for g, sub in detalhe2.groupby("grupo"):
        by_g.append(
            {
                "grupo": g,
                "n": int(len(sub)),
                "com_coord": int(sub["tem_coord"].sum()),
                "ok": int((~sub["problema"]).sum()),
                "problemas": int(sub["problema"].sum()),
                "sem_coord": int(sub["sem_coord"].sum()),
                "colisao_id": int(sub["flag_colisao_id"].sum()),
                "longe_centroide": int(sub["longe_centroide"].sum()),
                "fora_mt": int(sub["fora_mt"].sum()),
                "sem_ibge": int(sub["sem_ibge"].sum()),
            }
        )
    resumo_g = pd.DataFrame(by_g)
    resumo_g.to_csv(OUT_DIR / "geo_resumo_por_grupo.csv", index=False, encoding="utf-8-sig")

    meta = {
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "universo": "form.Hospital TipoUnidadeSaude in (Hospital, UPA) + nomes hospital/UPA/PA/maternidade",
        "regras": {
            "bbox_mt": {"lat": list(MT_LAT), "lon": list(MT_LON)},
            "limiar_km_centroide": LIMIAR_KM_CENTROIDE,
            "prioridade_coord": [
                "UnidadeSaude_IndicaSUS (só sem colisão de município)",
                "CNES_operacional",
            ],
            "nao_usa_centroide_como_oficial": True,
            "colisao_id": "FormHospitalId = UnidadeSaudeId com IBGE municipal diferente → descarta lat/lon UnidadeSaude",
        },
        "totais": {
            "n": int(len(detalhe2)),
            "hospital": int((detalhe2["grupo"] == "Hospital").sum()),
            "upa": int((detalhe2["grupo"] == "UPA").sum()),
            "com_coord": int(detalhe2["tem_coord"].sum()),
            "ok": int((~detalhe2["problema"]).sum()),
            "problemas": int(detalhe2["problema"].sum()),
            "status": {str(k): int(v) for k, v in resumo_status.items()},
            "por_grupo": by_g,
        },
        "arquivos": {
            "todos": str(path_all.relative_to(ROOT)).replace("\\", "/"),
            "problemas": str(path_prob.relative_to(ROOT)).replace("\\", "/"),
            "resumo_grupo": "data/output/validacao_geo_indicasus/geo_resumo_por_grupo.csv",
        },
    }
    (OUT_DIR / "00_metodo_geo.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    lines = [
        "# Validação de geolocalização — Hospitais e UPAs (IndicaSUS)",
        "",
        f"Gerado em: {meta['gerado_em']}",
        "",
        "## Totais",
        "",
        f"- Unidades no universo: **{meta['totais']['n']}** (Hospital {meta['totais']['hospital']} · UPA {meta['totais']['upa']})",
        f"- Com coordenada utilizável: **{meta['totais']['com_coord']}**",
        f"- Status aceitável (OK ou CNES após colisão): **{meta['totais']['ok']}**",
        f"- Com problema: **{meta['totais']['problemas']}**",
        "",
        "### Por status",
        "",
        "| Status | N |",
        "|---|---:|",
    ]
    for k, v in sorted(resumo_status.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "### Por grupo",
        "",
        "| Grupo | N | Coord | OK | Problemas | Sem coord | Colisão Id | Longe centroide |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in by_g:
        lines.append(
            f"| {g['grupo']} | {g['n']} | {g['com_coord']} | {g['ok']} | {g['problemas']} | "
            f"{g['sem_coord']} | {g['colisao_id']} | {g['longe_centroide']} |"
        )
    lines += [
        "",
        "## Regras",
        "",
        f"- BBox MT: lat {MT_LAT}, lon {MT_LON}",
        f"- Longe do centroide municipal: > {LIMIAR_KM_CENTROIDE:.0f} km",
        "- Coordenada: UnidadeSaude (sem colisão) → CNES; centroide **não** é oficial",
        "- COLISAO_ID: FormHospitalId = UnidadeSaudeId com municípios diferentes → descarta lat/lon IndicaSUS da UnidadeSaude",
        "",
        f"Arquivos: `{path_all.name}`, `{path_prob.name}`",
        "",
        "## Principais problemas (amostra)",
        "",
    ]
    top = probs.head(50)
    if top.empty:
        lines.append("_Nenhum problema listado._")
    else:
        for _, r in top.iterrows():
            lines.append(
                f"- **{r.get('status_geo')}** · {r.get('grupo')} · {r.get('nome')} "
                f"({r.get('municipio') or 'sem mun.'}) · Id {r.get('unidade_id')} · CNES {r.get('cnes') or '—'}"
            )
    md = "\n".join(lines)
    (OUT_DIR / "relatorio_geo_hospitais_upas.md").write_text(md, encoding="utf-8")
    try:
        import markdown

        html = (
            "<!DOCTYPE html><html lang='pt-BR'><head><meta charset='utf-8'>"
            "<title>Validação geo Hospitais/UPAs IndicaSUS</title>"
            "<style>body{font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem}"
            "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:.35rem .5rem;text-align:left}"
            "th{background:#ecfdf5}</style></head><body>"
            + markdown.markdown(md, extensions=["tables"])
            + "</body></html>"
        )
    except Exception:
        html = f"<pre>{md}</pre>"
    (OUT_DIR / "relatorio_geo_hospitais_upas.html").write_text(html, encoding="utf-8")
    meta["markdown"] = str((OUT_DIR / "relatorio_geo_hospitais_upas.md").relative_to(ROOT)).replace("\\", "/")
    return meta


def main() -> int:
    print("Consultando IndicaSUS (hospitais/UPAs)...")
    raw = carregar_indicasus()
    print(f"Linhas brutas: {len(raw)}")
    df = enriquecer(raw)
    print(f"Após filtro Hospital/UPA: {len(df)}")
    meta = gerar_relatorio(df)
    print(json.dumps(meta["totais"], ensure_ascii=False, indent=2))
    print("OUT", OUT_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
