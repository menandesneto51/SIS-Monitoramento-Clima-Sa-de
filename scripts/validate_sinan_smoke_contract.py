from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sisclima.ingestion.sqlserver import read_sqlserver


DISCOVERY_SQL = Path("sql/dw_sinan_intoxicacao_schema_discovery.sql")
MAPPING_FILE = Path("config/sinan_smoke_contract.json")

REQUIRED_KEYS = (
    "numero_notificacao",
    "data_notificacao",
    "cod_ibge",
    "municipio",
    "agente_tox",
    "out_agente",
    "via_1",
    "via_2",
    "via_3",
    "circunstan",
    "circun_des",
)


@dataclass(frozen=True)
class ContractValidation:
    valid: bool
    missing_mappings: tuple[str, ...]
    missing_columns: tuple[str, ...]


def load_mapping() -> dict:
    return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))


def validate_mapping(columns: list[str], mapping_doc: dict) -> ContractValidation:
    mapping = mapping_doc.get("mapping") or {}
    discovered = {str(column) for column in columns}

    missing_mappings = tuple(
        key for key in REQUIRED_KEYS
        if not isinstance(mapping.get(key), str) or not mapping.get(key, "").strip()
    )

    missing_columns = tuple(
        mapping[key]
        for key in REQUIRED_KEYS
        if key not in missing_mappings and mapping[key] not in discovered
    )

    return ContractValidation(
        valid=not missing_mappings and not missing_columns,
        missing_mappings=missing_mappings,
        missing_columns=missing_columns,
    )


def discover_dw_columns() -> pd.DataFrame:
    sql = DISCOVERY_SQL.read_text(encoding="utf-8")
    return read_sqlserver("DW", sql)


def main() -> int:
    df = discover_dw_columns()
    if df.empty or "COLUMN_NAME" not in df.columns:
        print("SCHEMA_DISCOVERY_FAILED: nenhuma coluna retornada do DW.")
        return 2

    columns = [str(v) for v in df["COLUMN_NAME"].dropna().tolist()]
    mapping_doc = load_mapping()
    result = validate_mapping(columns, mapping_doc)

    print(f"DISCOVERED_COLUMNS={len(columns)}")
    print("MAPPING_STATUS=" + str(mapping_doc.get("status", "unknown")))

    if result.missing_mappings:
        print("MISSING_MAPPINGS=" + ",".join(result.missing_mappings))

    if result.missing_columns:
        print("MAPPED_COLUMNS_NOT_FOUND=" + ",".join(result.missing_columns))

    if result.valid:
        print("SMOKE_CONTRACT_SCHEMA=VALIDATED")
        return 0

    print("SMOKE_CONTRACT_SCHEMA=PENDING")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
