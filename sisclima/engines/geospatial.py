from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

CENTER_MT = {"lat": -12.9, "lon": -55.8}
LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]
LEVEL_COLOR_MAP = {
    "cinza": "#6b7280",
    "verde": "#16803c",
    "amarela": "#e6b800",
    "laranja": "#d97706",
    "vermelha": "#dc2626",
    "roxa": "#5b21b6",
}

_COD_CANDIDATES = [
    "cod_ibge",
    "CD_MUN",
    "CD_MUNGE",
    "CD_GEOCMU",
    "GEOCODIGO",
    "GEOCODIG_M",
    "cod_mun",
    "codigo_ibge",
    "CodigoIBGE",
    "codigo",
]
_MUN_CANDIDATES = [
    "municipio",
    "NM_MUN",
    "NM_MUNICIP",
    "NOME",
    "Nome",
    "name",
    "nome_municipio",
    "municipio_x",
    "municipio_y",
    "municipio_shape",
]


def _first_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def normalize_cod_ibge(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{7})", expand=False)


def shapefile_candidates() -> list[Path]:
    """Ordem de busca do shapefile municipal de MT."""
    candidates: list[Path] = []
    try:
        from sisclima.core.config import APP_CONFIG

        candidates.append(Path(APP_CONFIG.shapefile_municipios))
    except Exception:
        pass

    candidates.extend(
        [
            Path("data/geo/municipios_mt/MT_Municipios_2025.shp"),
            Path("data/geo/MT_Municipios_2025.shp"),
            Path("data/input/MT_Municipios_2025.shp"),
            Path("MT_Municipios_2025.shp"),
            Path("data/geo/municipios_mt/MT_Municipios_2024.shp"),
            Path("data/geo/MT_Municipios_2024.shp"),
        ]
    )

    data_root = Path("data")
    if data_root.exists():
        candidates.extend(data_root.rglob("*Municipios*.shp"))
        candidates.extend(data_root.rglob("*MUNICIP*.shp"))

    out: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def geojson_file_candidates() -> list[Path]:
    return [
        Path("data/processed/municipios_mt_2025_simplificado.geojson"),
        Path("data/processed/municipios_mt_2025.geojson"),
        Path("data/raw/ibge/malha_municipios_mt.geojson"),
        Path("data/geo/municipios_mt/MT_Municipios_2025.geojson"),
    ]


def load_shapefile(path: str | Path | None = None):
    try:
        import geopandas as gpd
    except Exception as e:
        log.warning("geopandas indisponível para shapefile: %s", e)
        return None

    if path is None:
        for cand in shapefile_candidates():
            if cand.exists():
                path = cand
                break
    if path is None:
        log.warning("Shapefile municipal não encontrado.")
        return None

    p = Path(path)
    if not p.exists():
        log.warning("Shapefile não encontrado: %s", p)
        return None
    try:
        gdf = gpd.read_file(p)
        if gdf.crs is not None:
            gdf = gdf.to_crs(epsg=4326)
        return gdf
    except Exception as e:
        log.warning("Falha ao abrir shapefile %s: %s", p, e)
        return None


def _normalize_municipal_gdf(gdf, source_label: str) -> tuple[Optional[Any], pd.DataFrame, str]:
    if gdf is None or getattr(gdf, "empty", True):
        return None, pd.DataFrame(), f"Geometria municipal vazia: {source_label}"

    cod_col = _first_col(gdf, _COD_CANDIDATES)
    if cod_col is None:
        for c in gdf.columns:
            if c == "geometry":
                continue
            vals = gdf[c].astype(str).str.extract(r"(\d{7})", expand=False)
            if vals.notna().sum() >= 100:
                cod_col = c
                break
    if cod_col is None:
        return None, pd.DataFrame(), f"Não encontrei coluna de código IBGE em: {source_label}"

    gdf = gdf.copy()
    gdf["cod_ibge"] = normalize_cod_ibge(gdf[cod_col])
    gdf = gdf[gdf["cod_ibge"].notna()].copy()
    gdf = gdf.drop_duplicates("cod_ibge")

    mun_col = _first_col(gdf, _MUN_CANDIDATES)
    if mun_col:
        gdf["municipio_shape"] = gdf[mun_col].astype(str)
    else:
        gdf["municipio_shape"] = gdf["cod_ibge"]

    geojson = json.loads(gdf[["cod_ibge", "municipio_shape", "geometry"]].to_json())
    # Garante featureidkey estável como string
    for feat in geojson.get("features", []):
        props = feat.setdefault("properties", {})
        if props.get("cod_ibge") is not None:
            props["cod_ibge"] = str(props["cod_ibge"])
    attrs = pd.DataFrame(gdf.drop(columns="geometry"))
    attrs["cod_ibge"] = attrs["cod_ibge"].astype(str)
    return geojson, attrs, f"Shapefile carregado: {source_label} | municípios: {len(attrs)}"


def _normalize_geojson_dict(geojson: dict, source_label: str) -> tuple[Optional[dict], pd.DataFrame, str]:
    """Normaliza GeoJSON puro (sem geopandas) para properties.cod_ibge."""
    if not geojson or "features" not in geojson:
        return None, pd.DataFrame(), f"GeoJSON inválido: {source_label}"

    rows = []
    features_out = []
    for feat in geojson.get("features", []):
        props = dict(feat.get("properties") or {})
        cod = None
        for key in _COD_CANDIDATES:
            if key in props and props[key] is not None:
                m = pd.Series([str(props[key])]).str.extract(r"(\d{7})", expand=False).iloc[0]
                if pd.notna(m):
                    cod = str(m)
                    break
        if cod is None:
            # tenta qualquer propriedade com 7 dígitos
            for v in props.values():
                m = pd.Series([str(v)]).str.extract(r"(\d{7})", expand=False).iloc[0]
                if pd.notna(m):
                    cod = str(m)
                    break
        if cod is None:
            continue
        mun = None
        for key in _MUN_CANDIDATES:
            if key in props and props[key]:
                mun = str(props[key])
                break
        props["cod_ibge"] = cod
        props["municipio_shape"] = mun or cod
        feat2 = dict(feat)
        feat2["properties"] = props
        features_out.append(feat2)
        rows.append({"cod_ibge": cod, "municipio_shape": mun or cod})

    if not features_out:
        return None, pd.DataFrame(), f"GeoJSON sem códigos IBGE: {source_label}"

    out = {"type": "FeatureCollection", "features": features_out}
    attrs = pd.DataFrame(rows).drop_duplicates("cod_ibge")
    return out, attrs, f"GeoJSON municipal carregado: {source_label} | municípios: {len(attrs)}"


def _load_geojson_pure() -> tuple[Optional[dict], pd.DataFrame, str]:
    """Fallback sem geopandas: lê GeoJSON processado via json."""
    for path in geojson_file_candidates():
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            geojson, attrs, status = _normalize_geojson_dict(raw, str(path))
            if geojson is not None:
                return geojson, attrs, status
        except Exception as exc:
            log.warning("Falha ao ler GeoJSON puro %s: %s", path, exc)
    return None, pd.DataFrame(), "GeoJSON municipal não encontrado em data/processed."


def _load_geojson_fallback() -> tuple[Optional[dict], pd.DataFrame, str]:
    """Fallback: GeoJSON processado (geopandas se houver; senão json puro)."""
    try:
        import geopandas as gpd
    except Exception:
        return _load_geojson_pure()

    for path in geojson_file_candidates():
        if not path.exists():
            continue
        try:
            gdf = gpd.read_file(path)
            if gdf.crs is not None:
                gdf = gdf.to_crs(epsg=4326)
            geojson, attrs, status = _normalize_municipal_gdf(gdf, str(path))
            if geojson is not None:
                status = status.replace("Shapefile carregado", "GeoJSON municipal carregado (fallback)")
                return geojson, attrs, status
        except Exception as exc:
            log.warning("Falha ao ler GeoJSON %s: %s", path, exc)
    return _load_geojson_pure()


@lru_cache(maxsize=1)
def load_municipal_geojson(prefer_shapefile: bool = True) -> tuple[Optional[dict], pd.DataFrame, str]:
    """
    Carrega geometria municipal para todos os mapas.
    Prioridade: shapefile MT (geopandas) → GeoJSON processado (com ou sem geopandas).
    """
    has_gpd = True
    try:
        import geopandas as gpd  # noqa: F401
    except Exception as exc:
        has_gpd = False
        log.warning("geopandas indisponível (%s) — usando GeoJSON processado sem shapefile.", exc)

    if prefer_shapefile and has_gpd:
        for path in shapefile_candidates():
            if not path.exists():
                continue
            gdf = load_shapefile(path)
            if gdf is None:
                continue
            geojson, attrs, status = _normalize_municipal_gdf(gdf, str(path))
            if geojson is not None:
                return geojson, attrs, status

    return _load_geojson_fallback()


def prepare_map_dataframe(
    resumo: pd.DataFrame,
    geojson: Optional[dict] = None,
    attrs: Optional[pd.DataFrame] = None,
    status: Optional[str] = None,
) -> tuple[pd.DataFrame, Optional[dict], str]:
    if geojson is None or attrs is None or status is None:
        geojson, attrs, status = load_municipal_geojson()

    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame(), geojson, status

    df = resumo.copy()
    if "cod_ibge" in df.columns:
        df["cod_ibge"] = normalize_cod_ibge(df["cod_ibge"]).astype(str)

    if attrs is not None and not attrs.empty and "cod_ibge" in attrs.columns and "cod_ibge" in df.columns:
        keep_attrs = [c for c in ["cod_ibge", "municipio_shape"] if c in attrs.columns]
        attrs2 = attrs[keep_attrs].drop_duplicates("cod_ibge").copy()
        attrs2["cod_ibge"] = attrs2["cod_ibge"].astype(str)
        df = df.merge(attrs2, on="cod_ibge", how="left")
        if "municipio_shape" in df.columns:
            if "municipio" not in df.columns:
                df["municipio"] = df["municipio_shape"]
            else:
                df["municipio"] = df["municipio"].fillna(df["municipio_shape"])
    return df, geojson, status


def join_indicators_to_geo(gdf, df: pd.DataFrame, geo_key="cod_ibge", data_key="cod_ibge"):
    if gdf is None or df.empty:
        return gdf
    gdf = gdf.copy()
    if geo_key not in gdf.columns:
        for c in gdf.columns:
            if "CD_MUN" in c.upper() or "COD" in c.upper():
                geo_key = c
                break
    return gdf.merge(df, left_on=geo_key, right_on=data_key, how="left")


def make_choropleth_or_points(
    df: pd.DataFrame,
    geojson: Optional[dict],
    color_col: str,
    title: str,
    hover_cols: Optional[list[str]] = None,
    categorical: bool = False,
    height: int = 660,
    zoom: float = 4.5,
    allow_points_fallback: bool = False,
) -> Optional[go.Figure]:
    """Gera cloropleta municipal (shapefile/GeoJSON). Pontos só se allow_points_fallback=True."""
    if df is None or df.empty:
        return None
    if not color_col or color_col not in df.columns:
        return None

    hover_cols = hover_cols or []
    plot_base = df.copy()
    if "cod_ibge" in plot_base.columns:
        plot_base["cod_ibge"] = normalize_cod_ibge(plot_base["cod_ibge"]).astype(str)

    for c in [color_col] + hover_cols:
        if c in plot_base.columns and c not in [
            "nivel",
            "municipio",
            "cod_ibge",
            "fonte_ocupacao",
            "regional_saude",
            "qualidade_ar_nivel",
            "poluente_dominante",
            "classe_saturacao_solo",
            "componente_dominante",
            "nivel_alerta_integrado",
            "nivel_sis",
        ]:
            plot_base[c] = pd.to_numeric(plot_base[c], errors="coerce")

    if categorical and color_col in plot_base.columns:
        plot_base[color_col] = (
            plot_base[color_col]
            .astype(str)
            .str.strip()
            .str.lower()
            .where(lambda s: s.isin(LEVEL_ORDER), "cinza")
        )

    if geojson is not None and "cod_ibge" in plot_base.columns:
        plot_df = plot_base[plot_base["cod_ibge"].notna() & (plot_base["cod_ibge"] != "nan")].copy()
        plot_df["cod_ibge"] = plot_df["cod_ibge"].astype(str)
        if plot_df.empty:
            return None
        # Dedup para evitar polígonos sobrepostos
        plot_df = plot_df.drop_duplicates("cod_ibge", keep="first")
        common = dict(
            data_frame=plot_df,
            geojson=geojson,
            locations="cod_ibge",
            featureidkey="properties.cod_ibge",
            color=color_col,
            hover_name="municipio" if "municipio" in plot_df.columns else None,
            hover_data=[c for c in hover_cols if c in plot_df.columns],
            center=CENTER_MT,
            zoom=zoom,
            opacity=0.78,
            height=height,
            mapbox_style="carto-positron",
            title=title,
        )
        try:
            if categorical:
                fig = px.choropleth_mapbox(
                    **common,
                    category_orders={color_col: LEVEL_ORDER},
                    color_discrete_map=LEVEL_COLOR_MAP,
                )
            else:
                fig = px.choropleth_mapbox(
                    **common,
                    color_continuous_scale="Reds",
                )
            fig.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
            fig.update_traces(marker_line_width=0.4, marker_line_color="#334155")
            return fig
        except Exception as exc:
            log.warning("Falha cloropleta mapbox: %s", exc)

    if allow_points_fallback and {"lat", "lon"}.issubset(plot_base.columns):
        plot_df = plot_base.dropna(subset=["lat", "lon"]).copy()
        if plot_df.empty:
            return None
        fig = px.scatter_mapbox(
            plot_df,
            lat="lat",
            lon="lon",
            color=color_col if color_col in plot_df.columns else None,
            color_discrete_map=LEVEL_COLOR_MAP if categorical else None,
            color_continuous_scale=None if categorical else "Reds",
            hover_name="municipio" if "municipio" in plot_df.columns else None,
            hover_data=[c for c in hover_cols if c in plot_df.columns],
            center=CENTER_MT,
            zoom=zoom,
            height=height,
            mapbox_style="carto-positron",
            title=title,
        )
        fig.update_layout(margin={"r": 0, "t": 50, "l": 0, "b": 0})
        return fig

    return None
