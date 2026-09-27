from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from sisclima.ingestion.sqlserver import read_sqlserver


DISCOVERY_SQL = Path("sql/dw_sinan_intoxicacao_schema_discovery.sql")

# Semantic contract required by the downstream smoke-notification adapter.
CONTRACT = {
    "notification": {
        "numero_notificacao",
        "data_notificacao",
        "cod_ibge",
        "municipio",
    },
    "agent": {
        "agente_tox",
        "out_agente",
    },
    "route": {
        "via_1",
        "via_2",
        "via_3",
    },
    "circumstance": {
        "circunstan",
        "circun_des",
    },
}


@dataclass(frozen=True)
class ContractValidation:
    valid: bool
    discovered_columns: tuple[str, ...]
    matched: dict[str, tuple[str, ...]]
    missing_groups: tuple[str, ...]


def _norm(value: str) -> str:
    return (
        str(value)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def validate_columns(columns: list[str]) -> ContractValidation:
    normalized = {_norm(c): c for c in columns}
    matched: dict[str, tuple[str, ...]] = {}
    missing_groups: list[str] = []

    for group, expected in CONTRACT.items():
        hits = tuple(sorted(original for normalized_name, original in normalized.items() if normalized_name in expected))
        matched[group] = hits
        if not hits:
            missing_groups.append(group)

    return ContractValidation(
        valid=not missing_groups,
        discovered_columns=tuple(columns),
        matched=matched,
        missing_groups=tuple(missing_groups),
    )


def discover_dw_columns() -> pd.DataFrame:
    sql = DISCOVERY_SQL.read_text(encoding="utf-8")
    return read_sqlserver("DW", sql)


def main() -> int:
    df = discover_dw_columns()
    if df.empty or "COLUMN_NAME" not in df.columns:
        print("SCHEMA_DISCOVERY_FAILED: nenhuma coluna retornada do DW.")
        return 2

    # The discovery SQL returns two result sets in SQL Server clients, while
    # pandas/pyodbc reads the first. That first result set is sufficient.
    columns = [str(v) for v in df["COLUMN_NAME"].dropna().tolist()]
    result = validate_columns(columns)

    print(f"DISCOVERED_COLUMNS={len(result.discovered_columns)}")
    for group, hits in result.matched.items():
        print(f"{group.upper()}={','.join(hits) if hits else 'MISSING'}")

    if result.valid:
        print("SMOKE_CONTRACT_SCHEMA=READY_FOR_MANUAL_MAPPING")
        return 0

    print("SMOKE_CONTRACT_SCHEMA=INCOMPLETE")
    print("MISSING_GROUPS=" + ",".join(result.missing_groups))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
