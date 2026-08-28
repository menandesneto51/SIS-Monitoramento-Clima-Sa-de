# -*- coding: utf-8 -*-
"""Snapshot estadual de risco operacional e pressão assistencial."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

_NIVEL_ORDEM = ["roxa", "vermelha", "laranja", "amarela", "verde", "cinza"]
_SEMAFORO_ORDEM = ["vermelha", "amarela", "verde"]


def _num(v: Any) -> float | None:
    try:
        x = float(pd.to_numeric(v, errors="coerce"))
    except (TypeError, ValueError):
        return None
    if pd.isna(x):
        return None
    return float(x)


def _br(v: float | None, nd: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:.{nd}f}".replace(".", ",")


def _tem_indice_pressao(df: pd.DataFrame) -> bool:
    if df is None or df.empty or "indice_pressao_saude" not in df.columns:
        return False
    return pd.to_numeric(df["indice_pressao_saude"], errors="coerce").notna().any()


def quadro_risco_pressao(resumo: pd.DataFrame | None = None) -> dict[str, Any]:
    """Registro estadual: distribuição de risco + pressão assistencial + ranking."""
    from_db = resumo is None
    if resumo is None:
        from sisclima.core.db import read_table

        resumo = read_table("resumo_municipal_atual")
    if resumo is None or resumo.empty:
        return {"disponivel": False, "motivo": "Resumo municipal ausente nesta rodada."}

    df = resumo.copy()
    if not _tem_indice_pressao(df):
        try:
            from sisclima.engines.indice_pressao_saude import persist_indice_pressao_resumo

            df = persist_indice_pressao_resumo(df, write=from_db)
        except Exception:
            pass
    n = len(df)
    dist_nivel: dict[str, int] = {}
    if "nivel" in df.columns:
        dist_nivel = (
            df["nivel"].astype(str).str.lower().str.strip().value_counts().to_dict()
        )
    dist_nivel_txt = (
        " · ".join(f"{k} {int(dist_nivel.get(k, 0))}" for k in _NIVEL_ORDEM if dist_nivel.get(k))
        or "—"
    )

    pressao = (
        pd.to_numeric(df["indice_pressao_saude"], errors="coerce")
        if "indice_pressao_saude" in df.columns
        else pd.Series(dtype=float)
    )
    ocup = (
        pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce")
        if "ocupacao_leitos_pct" in df.columns
        else pd.Series(dtype=float)
    )
    calor = (
        pd.to_numeric(df["pressao_calor_pct"], errors="coerce")
        if "pressao_calor_pct" in df.columns
        else pd.Series(dtype=float)
    )
    dist_semaforo: dict[str, int] = {}
    if "semaforo_pressao" in df.columns:
        dist_semaforo = (
            df["semaforo_pressao"].astype(str).str.lower().str.strip().value_counts().to_dict()
        )
    semaforo_txt = (
        " · ".join(
            f"{k} {int(dist_semaforo.get(k, 0))}" for k in _SEMAFORO_ORDEM if dist_semaforo.get(k)
        )
        or "—"
    )

    rank = df["nivel"].map(lambda x: STAGE_ORDER.get(str(x).lower().strip(), -1)) if "nivel" in df.columns else pd.Series([-1] * n)
    df = df.assign(_rank=rank)
    if pressao.notna().any():
        df["_pressao"] = pd.to_numeric(df["indice_pressao_saude"], errors="coerce")
    elif calor.notna().any():
        df["_pressao"] = pd.to_numeric(df["pressao_calor_pct"], errors="coerce")
    elif ocup.notna().any():
        df["_pressao"] = pd.to_numeric(df["ocupacao_leitos_pct"], errors="coerce")
    else:
        df["_pressao"] = 0.0
    top = df.sort_values(["_rank", "_pressao"], ascending=False).head(10)
    registros: list[dict[str, Any]] = []
    for _, row in top.iterrows():
        registros.append(
            {
                "municipio": str(row.get("municipio") or row.get("cod_ibge") or "—"),
                "cod_ibge": str(row.get("cod_ibge") or ""),
                "regional": str(row.get("regional_saude") or "—"),
                "nivel": str(row.get("nivel") or "cinza").lower().strip(),
                "indice_pressao_saude": _num(row.get("indice_pressao_saude")),
                "semaforo_pressao": str(row.get("semaforo_pressao") or "—").lower().strip(),
                "ocupacao_leitos_pct": _num(row.get("ocupacao_leitos_pct")),
                "pressao_calor_pct": _num(row.get("pressao_calor_pct")),
            }
        )

    return {
        "disponivel": True,
        "n_municipios": n,
        "dist_nivel": {k: int(dist_nivel.get(k, 0)) for k in _NIVEL_ORDEM},
        "dist_nivel_txt": dist_nivel_txt,
        "pressao_media": float(pressao.mean()) if pressao.notna().any() else None,
        "pressao_max": float(pressao.max()) if pressao.notna().any() else None,
        "pressao_n": int(pressao.notna().sum()),
        "ocupacao_media": float(ocup.mean()) if ocup.notna().any() else None,
        "ocupacao_max": float(ocup.max()) if ocup.notna().any() else None,
        "calor_media": float(calor.mean()) if calor.notna().any() else None,
        "calor_max": float(calor.max()) if calor.notna().any() else None,
        "dist_semaforo": {k: int(dist_semaforo.get(k, 0)) for k in _SEMAFORO_ORDEM},
        "semaforo_txt": semaforo_txt,
        "registros": registros,
        "pressao_media_txt": _br(float(pressao.mean()) if pressao.notna().any() else None),
        "pressao_max_txt": _br(float(pressao.max()) if pressao.notna().any() else None),
        "ocupacao_media_txt": _br(float(ocup.mean()) if ocup.notna().any() else None),
        "ocupacao_max_txt": _br(float(ocup.max()) if ocup.notna().any() else None),
        "calor_media_txt": _br(float(calor.mean()) if calor.notna().any() else None),
        "calor_max_txt": _br(float(calor.max()) if calor.notna().any() else None),
    }
