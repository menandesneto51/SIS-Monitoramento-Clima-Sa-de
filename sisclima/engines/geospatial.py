from __future__ import annotations
from pathlib import Path
import pandas as pd
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def load_shapefile(path: str | Path):
    try:
        import geopandas as gpd
    except Exception as e:
        log.warning('geopandas indisponível: %s', e)
        return None
    p = Path(path)
    if not p.exists():
        log.warning('Shapefile não encontrado: %s', p)
        return None
    try:
        return gpd.read_file(p)
    except Exception as e:
        log.warning('Falha ao abrir shapefile %s: %s', p, e)
        return None


def join_indicators_to_geo(gdf, df: pd.DataFrame, geo_key='cod_ibge', data_key='cod_ibge'):
    if gdf is None or df.empty:
        return gdf
    gdf = gdf.copy()
    if geo_key not in gdf.columns:
        # tenta encontrar coluna parecida
        for c in gdf.columns:
            if 'CD_MUN' in c.upper() or 'COD' in c.upper():
                geo_key = c
                break
    return gdf.merge(df, left_on=geo_key, right_on=data_key, how='left')
