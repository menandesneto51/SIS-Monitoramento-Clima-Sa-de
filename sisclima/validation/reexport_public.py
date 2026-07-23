# -*- coding: utf-8 -*-
"""
Corrige pressão assistencial proxy e reclassifica níveis para exportação cloud.

Uso:
    python -m sisclima.validation.reexport_public
    python -m sisclima.validation.reexport_public --source db
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.core.config import SETTINGS
from sisclima.core.db import read_table, sqlite_path_from_url
from sisclima.engines.stages import classify_stage, STAGE_LABELS
from sisclima.pipeline import _prepare_latest_for_stage
from sisclima.engines.resilience import resilience_index


PUBLIC = ROOT / "data" / "public"
PROXY_SOURCES = {"PROXY_OCUPACAO_INDICASUS_CLIMA", "PROXY_OCUPACAO", "PROXY"}


def _is_proxy_pressao(row: dict) -> bool:
    fonte = str(row.get("fonte_pressao") or "")
    if any(p in fonte.upper() for p in PROXY_SOURCES):
        return True
    pressao = row.get("pressao_calor_pct")
    try:
        if pressao is not None and float(pressao) > 15:
            # Valores >15% sem fonte real são quase sempre proxy legado.
            if fonte not in ("INDICASUS_ATENDIMENTOS", ""):
                return True
            if not fonte:
                return True
    except (TypeError, ValueError):
        pass
    return False


def _clear_proxy_pressao(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "pressao_calor_pct" not in out.columns:
        return out

    mask = out.apply(lambda r: _is_proxy_pressao(r.to_dict()), axis=1)
    out.loc[mask, "pressao_calor_pct"] = np.nan
    if "pressao_assistencial_pct" in out.columns:
        out.loc[mask, "pressao_assistencial_pct"] = np.nan
    if "fonte_pressao" in out.columns:
        out.loc[mask, "fonte_pressao"] = "PRESSAO_INDISPONIVEL"
    return out


def _reclassify_row(row: dict) -> dict:
    latest = _prepare_latest_for_stage(row)
    stage = classify_stage(latest, SETTINGS)

    if latest.get("obitos_calor_suspeitos", 0) and latest.get("obitos_calor_suspeitos", 0) >= 1:
        if stage.score < 3:
            stage.score = 3
            stage.nivel = "vermelha"

    if latest.get("score_sentinela", 0) and latest.get("score_sentinela", 0) >= 10 and stage.score < 2:
        stage.score = 2
        stage.nivel = "laranja"

    resil = resilience_index(latest, SETTINGS.get("pesos_resiliencia", {}))
    out = {**row, **resil}
    out["nivel"] = stage.nivel
    out["score"] = stage.score
    out["motivo"] = "; ".join(stage.motivos[:14])
    return out


def fix_resumo(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cleaned = _clear_proxy_pressao(df)
    rows = [_reclassify_row(r.to_dict()) for _, r in cleaned.iterrows()]
    return pd.DataFrame(rows)


def load_resumo(source: str) -> pd.DataFrame:
    if source == "db":
        df = read_table("resumo_municipal_atual")
        if not df.empty:
            return df
    path = PUBLIC / "resumo_municipal_atual.csv"
    if path.exists():
        return pd.read_csv(path)
    raise FileNotFoundError("Nenhuma fonte de resumo_municipal_atual encontrada")


def export_public_tables(resumo: pd.DataFrame) -> dict[str, int]:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    counts = {}

    resumo_path = PUBLIC / "resumo_municipal_atual.csv"
    resumo.to_csv(resumo_path, index=False, encoding="utf-8-sig")
    counts["resumo_municipal_atual.csv"] = len(resumo)

    ops_path = PUBLIC / "ops_resumo_operacional_cnes.csv"
    if ops_path.exists():
        ops = pd.read_csv(ops_path)
        if "cod_ibge" in ops.columns and "cod_ibge" in resumo.columns:
            cols_fix = ["nivel", "score", "motivo", "pressao_calor_pct", "pressao_assistencial_pct", "fonte_pressao", "indice_resiliencia"]
            cols_fix = [c for c in cols_fix if c in resumo.columns]
            patch = resumo[["cod_ibge"] + cols_fix].drop_duplicates("cod_ibge")
            ops = ops.drop(columns=[c for c in cols_fix if c in ops.columns], errors="ignore")
            ops = ops.merge(patch, on="cod_ibge", how="left")
        else:
            ops = fix_resumo(ops)
        ops.to_csv(ops_path, index=False, encoding="utf-8-sig")
        counts["ops_resumo_operacional_cnes.csv"] = len(ops)

    return counts


def main():
    parser = argparse.ArgumentParser(description="Corrige proxy de pressão e reexporta data/public")
    parser.add_argument("--source", choices=["csv", "db"], default="csv", help="Fonte do resumo municipal")
    args = parser.parse_args()

    print(f"Carregando resumo de: {args.source}")
    resumo = load_resumo(args.source)
    print(f"Municípios: {len(resumo)}")

    before = resumo["nivel"].value_counts().to_dict() if "nivel" in resumo.columns else {}
    fixed = fix_resumo(resumo)
    after = fixed["nivel"].value_counts().to_dict()

    counts = export_public_tables(fixed)

    print("\nDistribuição ANTES:", before)
    print("Distribuição DEPOIS:", after)
    print("\nArquivos exportados:")
    for name, n in counts.items():
        print(f"  {name}: {n} linhas")

    proxy_remaining = fixed["fonte_pressao"].astype(str).str.contains("PROXY", case=False, na=False).sum() if "fonte_pressao" in fixed.columns else 0
    pressao_valid = pd.to_numeric(fixed.get("pressao_calor_pct"), errors="coerce").notna().sum()
    print(f"\nProxies restantes: {proxy_remaining}")
    print(f"Pressões reais válidas: {pressao_valid}")


if __name__ == "__main__":
    main()
