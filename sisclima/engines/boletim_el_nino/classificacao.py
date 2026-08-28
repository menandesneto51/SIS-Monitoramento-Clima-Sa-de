# -*- coding: utf-8 -*-
"""Fonte única de classificação municipal da rodada (CURRENT_MUNICIPAL_CLASSIFICATION).

Mapa 1, Mapa 2, Mapa 3, tabelas e textos territoriais consomem a mesma estrutura.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

import pandas as pd

from sisclima.engines.boletim_el_nino.maps import LEVEL_ORDER, normalize_cod_ibge

NIVEIS_PUBLICOS = ("verde", "amarela", "laranja", "vermelha", "roxa")


def _norm_nivel(v: Any) -> str:
    s = str(v or "").strip().lower()
    if s in LEVEL_ORDER:
        return s
    return "cinza"


def build_current_municipal_classification(
    resumo: pd.DataFrame,
    *,
    data_hora_rodada: str | None = None,
) -> dict[str, Any]:
    """Fecha a classificação municipal da rodada (142 municípios esperados)."""
    now = data_hora_rodada or datetime.now().strftime("%d/%m/%Y às %Hh%M")
    empty = {
        "disponivel": False,
        "df": pd.DataFrame(),
        "by_ibge6": {},
        "counts_atual": {k: 0 for k in NIVEIS_PUBLICOS},
        "counts_proj": {k: 0 for k in NIVEIS_PUBLICOS},
        "n": 0,
        "classification_hash": "",
        "data_hora_rodada": now,
        "MAP_REGEN_REQUIRED": True,
    }
    if resumo is None or resumo.empty or "cod_ibge" not in resumo.columns:
        return empty

    work = resumo.copy()
    work["codigo_ibge6"] = normalize_cod_ibge(work["cod_ibge"])
    work = work.dropna(subset=["codigo_ibge6"]).drop_duplicates("codigo_ibge6", keep="first")
    mun_col = "municipio" if "municipio" in work.columns else None
    reg_col = next((c for c in ("regional_saude", "regional") if c in work.columns), None)
    niv = work["nivel"] if "nivel" in work.columns else pd.Series(["cinza"] * len(work), index=work.index)
    pred = (
        work["nivel_predicao_7d"]
        if "nivel_predicao_7d" in work.columns
        else pd.Series(["cinza"] * len(work), index=work.index)
    )
    df = pd.DataFrame(
        {
            "codigo_ibge": work["codigo_ibge6"].astype(str),
            "municipio": work[mun_col].astype(str) if mun_col else work["codigo_ibge6"].astype(str),
            "regional": work[reg_col].astype(str) if reg_col else "",
            "classe_atual": [_norm_nivel(x) for x in niv],
            "classe_projetada_7d": [_norm_nivel(x) for x in pred],
            "data_hora_rodada": now,
        }
    )
    counts_atual = {k: int((df["classe_atual"] == k).sum()) for k in NIVEIS_PUBLICOS}
    counts_proj = {k: int((df["classe_projetada_7d"] == k).sum()) for k in NIVEIS_PUBLICOS}
    chash = classification_hash(df)
    by_ibge6 = {
        str(r["codigo_ibge"]): str(r["classe_atual"])
        for _, r in df.iterrows()
    }
    return {
        "disponivel": True,
        "df": df,
        "by_ibge6": by_ibge6,
        "counts_atual": counts_atual,
        "counts_proj": counts_proj,
        "n": int(len(df)),
        "classification_hash": chash,
        "data_hora_rodada": now,
        "MAP_REGEN_REQUIRED": True,
        "resumo_for_maps": _resumo_from_cmc(df),
    }


def classification_hash(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return ""
    rows = (
        df[["codigo_ibge", "classe_atual"]]
        .assign(codigo_ibge=lambda x: x["codigo_ibge"].astype(str))
        .sort_values("codigo_ibge")
    )
    payload = "|".join(f"{a}:{b}" for a, b in zip(rows["codigo_ibge"], rows["classe_atual"]))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _resumo_from_cmc(df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame mínimo compatível com _prep_merge / mapas (cod_ibge + nivel)."""
    out = pd.DataFrame(
        {
            "cod_ibge": df["codigo_ibge"].astype(str),
            "municipio": df["municipio"].astype(str),
            "nivel": df["classe_atual"].astype(str),
            "nivel_predicao_7d": df["classe_projetada_7d"].astype(str),
        }
    )
    if "regional" in df.columns:
        out["regional_saude"] = df["regional"].astype(str)
    return out


def counts_from_geodataframe(gdf: pd.DataFrame, col: str = "nivel") -> dict[str, int]:
    if gdf is None or gdf.empty or col not in gdf.columns:
        return {k: 0 for k in NIVEIS_PUBLICOS}
    s = gdf[col].astype(str).str.lower().str.strip()
    return {k: int((s == k).sum()) for k in NIVEIS_PUBLICOS}


def validate_map_vs_cmc(
    merged: pd.DataFrame,
    cmc: dict[str, Any],
    *,
    col: str = "nivel",
) -> dict[str, Any]:
    """Compara classes do mapa (merged) com CURRENT_MUNICIPAL_CLASSIFICATION."""
    out: dict[str, Any] = {
        "MAP3_CLASS_DISTRIBUTION_ERROR": 0,
        "MAP3_STALE_ERROR": 0,
        "MAP3_MUNICIPAL_DIFF_COUNT": 0,
        "MAP3_MUNICIPAL_DIFF": [],
        "map3_counts": {k: 0 for k in NIVEIS_PUBLICOS},
        "current_counts": dict(cmc.get("counts_atual") or {}),
    }
    if not cmc.get("disponivel") or merged is None or merged.empty:
        out["MAP3_CLASS_DISTRIBUTION_ERROR"] = 1
        out["MAP3_STALE_ERROR"] = 1
        return out

    map_counts = counts_from_geodataframe(merged, col)
    out["map3_counts"] = map_counts
    cur = cmc.get("counts_atual") or {}
    if any(int(map_counts.get(k, 0)) != int(cur.get(k, 0)) for k in NIVEIS_PUBLICOS):
        out["MAP3_CLASS_DISTRIBUTION_ERROR"] = 1
    if int(sum(map_counts.values())) != int(cmc.get("n") or 0):
        out["MAP3_CLASS_DISTRIBUTION_ERROR"] = 1

    by = cmc.get("by_ibge6") or {}
    diffs: list[dict[str, str]] = []
    if "_cod" not in merged.columns:
        out["MAP3_STALE_ERROR"] = 1
        out["MAP3_MUNICIPAL_DIFF_COUNT"] = max(1, len(by))
        return out
    for _, row in merged.iterrows():
        cod = str(row.get("_cod") or "")
        if not cod:
            continue
        classe_map = _norm_nivel(row.get(col))
        classe_araras = _norm_nivel(by.get(cod, "cinza"))
        if classe_map != classe_araras:
            diffs.append(
                {
                    "codigo_ibge": cod,
                    "municipio": str(row.get("municipio") or row.get("NM_MUN") or ""),
                    "classe_ARARAS": classe_araras,
                    "classe_Mapa3": classe_map,
                }
            )
    # municípios no CMC ausentes do mapa
    map_cods = set(merged["_cod"].astype(str))
    for cod, classe in by.items():
        if cod not in map_cods:
            diffs.append(
                {
                    "codigo_ibge": str(cod),
                    "municipio": "",
                    "classe_ARARAS": str(classe),
                    "classe_Mapa3": "ausente",
                }
            )
    out["MAP3_MUNICIPAL_DIFF"] = diffs
    out["MAP3_MUNICIPAL_DIFF_COUNT"] = len(diffs)
    if diffs:
        out["MAP3_STALE_ERROR"] = 1
    return out
