from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from scripts.build_mt_shapefile_web import validate_mapping


def test_mapping_requires_explicit_fields():
    gdf = gpd.GeoDataFrame(
        {"REAL_CODE": ["1"], "REAL_NAME": ["Municipio"]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])],
        crs="EPSG:4674",
    )

    try:
        validate_mapping(gdf, {"fields": {"cod_ibge": None, "municipio": None}})
    except RuntimeError as exc:
        assert "SHAPEFILE_MAPPING_PENDING" in str(exc)
    else:
        raise AssertionError("mapping pending should fail")


def test_mapping_accepts_only_existing_explicit_columns():
    gdf = gpd.GeoDataFrame(
        {"REAL_CODE": ["1"], "REAL_NAME": ["Municipio"]},
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 0)])],
        crs="EPSG:4674",
    )

    assert validate_mapping(
        gdf,
        {"fields": {"cod_ibge": "REAL_CODE", "municipio": "REAL_NAME"}},
    ) == ("REAL_CODE", "REAL_NAME")
