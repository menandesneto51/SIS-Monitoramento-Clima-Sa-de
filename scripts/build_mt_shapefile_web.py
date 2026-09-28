from __future__ import annotations

import hashlib
import json
from pathlib import Path

import geopandas as gpd

CONFIG_PATH = Path("config/mt_shapefile_web.json")
MANIFEST_PATH = Path("data/public/municipios_mt_2025_shapefile_web.manifest.json")

SHAPE_COMPONENTS = (
    "MT_Municipios_2025.shp",
    "MT_Municipios_2025.shx",
    "MT_Municipios_2025.dbf",
    "MT_Municipios_2025.prj",
    "MT_Municipios_2025.cpg",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def discover_schema(shapefile: Path) -> dict:
    gdf = gpd.read_file(shapefile)
    return {
        "feature_count": int(len(gdf)),
        "crs": str(gdf.crs) if gdf.crs else None,
        "columns": [str(column) for column in gdf.columns],
        "geometry_types": sorted({str(value) for value in gdf.geometry.geom_type.dropna().unique()}),
    }


def validate_mapping(gdf: gpd.GeoDataFrame, config: dict) -> tuple[str, str]:
    fields = config.get("fields") or {}
    cod_ibge = fields.get("cod_ibge")
    municipio = fields.get("municipio")

    missing = [
        key
        for key, value in (("cod_ibge", cod_ibge), ("municipio", municipio))
        if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        raise RuntimeError(
            "SHAPEFILE_MAPPING_PENDING: configure explicit fields for "
            + ", ".join(missing)
            + f". Available columns: {list(gdf.columns)}"
        )

    absent = [column for column in (cod_ibge, municipio) if column not in gdf.columns]
    if absent:
        raise RuntimeError(f"SHAPEFILE_MAPPING_INVALID: columns not found: {absent}")

    return cod_ibge, municipio


def build_web_geojson(config: dict) -> dict:
    shapefile = Path(config["shapefile"])
    gdf = gpd.read_file(shapefile)

    expected_count = int(config["expected_feature_count"])
    if len(gdf) != expected_count:
        raise RuntimeError(f"FEATURE_COUNT_MISMATCH: expected {expected_count}, got {len(gdf)}")

    expected_crs = str(config["expected_crs"])
    if gdf.crs is None or gdf.crs.to_string().upper() != expected_crs.upper():
        raise RuntimeError(f"CRS_MISMATCH: expected {expected_crs}, got {gdf.crs}")

    cod_field, name_field = validate_mapping(gdf, config)

    work = gdf[[cod_field, name_field, "geometry"]].copy()
    work[cod_field] = work[cod_field].astype(str).str.strip()
    work[name_field] = work[name_field].astype(str).str.strip()

    if work[cod_field].duplicated().any():
        duplicated = sorted(work.loc[work[cod_field].duplicated(), cod_field].unique())
        raise RuntimeError(f"DUPLICATE_IBGE_CODES: {duplicated}")

    if work[cod_field].nunique() != expected_count:
        raise RuntimeError("IBGE_CODE_COUNT_MISMATCH")

    if work.geometry.isna().any() or work.geometry.is_empty.any():
        raise RuntimeError("EMPTY_GEOMETRY")

    invalid = ~work.geometry.is_valid
    if invalid.any():
        work.loc[invalid, "geometry"] = work.loc[invalid, "geometry"].buffer(0)
        if (~work.geometry.is_valid).any():
            raise RuntimeError("INVALID_GEOMETRY_AFTER_REPAIR")

    tolerance = float(config.get("simplify_tolerance_degrees", 0))
    if tolerance > 0:
        work["geometry"] = work.geometry.simplify(tolerance, preserve_topology=True)

    work = work.rename(columns={cod_field: "cod_ibge", name_field: "municipio"})
    work = work.sort_values(["municipio", "cod_ibge"]).reset_index(drop=True)

    raw = json.loads(work.to_json(drop_id=True))
    precision = int(config.get("coordinate_precision", 5))

    def round_coords(value):
        if isinstance(value, list):
            if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
                return [round(item, precision) if isinstance(item, (int, float)) else item for item in value]
            return [round_coords(item) for item in value]
        return value

    for feature in raw["features"]:
        feature["geometry"]["coordinates"] = round_coords(feature["geometry"]["coordinates"])

    raw["source"] = {
        "kind": "IBGE Municipal Digital Mesh 2025 shapefile",
        "shapefile": config["shapefile"],
        "crs": expected_crs,
        "feature_count": expected_count,
        "simplify_tolerance_degrees": tolerance,
        "coordinate_precision": precision,
    }
    return raw


def main() -> int:
    config = load_config()
    shapefile = Path(config["shapefile"])

    print(json.dumps(discover_schema(shapefile), ensure_ascii=False, indent=2))

    web_geojson = build_web_geojson(config)
    output = Path(config["output"])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(web_geojson, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    component_dir = shapefile.parent
    manifest = {
        "status": "generated",
        "config": str(CONFIG_PATH),
        "source": {
            name: {
                "path": str(component_dir / name),
                "sha256": sha256(component_dir / name),
            }
            for name in SHAPE_COMPONENTS
            if (component_dir / name).exists()
        },
        "output": {
            "path": str(output),
            "sha256": sha256(output),
            "feature_count": len(web_geojson["features"]),
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"GENERATED={output}")
    print(f"MANIFEST={MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
