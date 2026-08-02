# -*- coding: utf-8 -*-
"""Níveis de rios / cotas a partir da telemetria ANA (alinhado ao Vigibarragens/SIS).

Produz `niveis_rios_municipal` com cota/vazão recentes, tendência 7d e estágio
operacional. Não substitui réguas da Defesa Civil nem cotas de alerta nominais
por estação — usa percentil da série disponível como proxy (mesmo espírito do
IDAP A6 do Vigibarragens).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]


def _ibge7(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{7})", expand=False)


def _nivel_from_razao(razao: float | None) -> str:
    if razao is None or (isinstance(razao, float) and np.isnan(razao)):
        return "cinza"
    if razao < 0.70:
        return "verde"
    if razao < 0.90:
        return "amarela"
    if razao < 1.00:
        return "laranja"
    if razao < 1.20:
        return "vermelha"
    return "roxa"


def build_niveis_rios_municipal(
    telemetria: pd.DataFrame,
    estacoes: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Agrega telemetria ANA em snapshot municipal de nível de rio."""
    if telemetria is None or telemetria.empty:
        return pd.DataFrame()

    df = telemetria.copy()
    if "cod_ibge" not in df.columns:
        return pd.DataFrame()
    df["cod_ibge"] = _ibge7(df["cod_ibge"])
    df = df.dropna(subset=["cod_ibge"])
    if df.empty:
        return pd.DataFrame()

    if "data" not in df.columns and "data_hora" in df.columns:
        df["data"] = pd.to_datetime(df["data_hora"], errors="coerce").dt.strftime("%Y-%m-%d")
    df["data"] = pd.to_datetime(df.get("data"), errors="coerce")

    for c in ("cota_cm", "vazao_m3s", "chuva_mm"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Nome do rio/estação quando existir no inventário
    nome_map: dict[str, str] = {}
    if estacoes is not None and not estacoes.empty and "cod_ibge" in estacoes.columns:
        e = estacoes.copy()
        e["cod_ibge"] = _ibge7(e["cod_ibge"])
        name_col = next(
            (c for c in ("nome_rio", "rio", "nome_estacao", "estacao") if c in e.columns),
            None,
        )
        if name_col:
            for cod, grp in e.dropna(subset=["cod_ibge"]).groupby("cod_ibge"):
                nomes = [str(x).strip() for x in grp[name_col].dropna().astype(str) if str(x).strip()]
                if nomes:
                    nome_map[str(cod)] = nomes[0]

    rows: list[dict[str, Any]] = []
    for cod, grp in df.groupby("cod_ibge"):
        g = grp.sort_values("data") if "data" in grp.columns else grp
        cota = g["cota_cm"] if "cota_cm" in g.columns else pd.Series(dtype=float)
        vazao = g["vazao_m3s"] if "vazao_m3s" in g.columns else pd.Series(dtype=float)
        cota_valid = cota.dropna()
        vazao_valid = vazao.dropna()

        cota_atual = float(cota_valid.iloc[-1]) if not cota_valid.empty else np.nan
        vazao_atual = float(vazao_valid.iloc[-1]) if not vazao_valid.empty else np.nan
        # Proxy da cota de alerta = P90 da série local (enquanto não houver régua DC)
        cota_p90 = float(cota_valid.quantile(0.90)) if len(cota_valid) >= 3 else np.nan
        cota_p50 = float(cota_valid.median()) if len(cota_valid) >= 2 else np.nan
        razao = float(cota_atual / cota_p90) if pd.notna(cota_atual) and pd.notna(cota_p90) and cota_p90 > 0 else np.nan

        # Tendência 7d: comparar média dos 2 últimos dias vs 5 anteriores
        tend = "estavel"
        if "data" in g.columns and len(cota_valid) >= 4:
            g2 = g.dropna(subset=["cota_cm"]).copy()
            g2 = g2.sort_values("data")
            recent = g2.tail(2)["cota_cm"].mean()
            prev = g2.iloc[:-2].tail(5)["cota_cm"].mean() if len(g2) > 2 else np.nan
            if pd.notna(recent) and pd.notna(prev) and prev > 0:
                delta = (recent - prev) / prev
                if delta >= 0.05:
                    tend = "subindo"
                elif delta <= -0.05:
                    tend = "descendo"

        data_ref = ""
        if "data" in g.columns and g["data"].notna().any():
            data_ref = pd.Timestamp(g["data"].max()).strftime("%Y-%m-%d")

        n_est = int(g["codigo_estacao"].nunique()) if "codigo_estacao" in g.columns else 1
        nivel = _nivel_from_razao(razao if pd.notna(razao) else None)
        if nivel == "cinza" and pd.notna(cota_atual):
            nivel = "verde"  # tem cota mas série curta demais para P90

        rows.append(
            {
                "cod_ibge": str(cod),
                "municipio": str(g["municipio"].dropna().iloc[0]) if "municipio" in g.columns and g["municipio"].notna().any() else "",
                "nome_rio_estacao": nome_map.get(str(cod), ""),
                "n_estacoes": n_est,
                "data_referencia": data_ref,
                "cota_cm": cota_atual,
                "cota_p50_cm": cota_p50,
                "cota_p90_cm": cota_p90,
                "razao_nivel_cota_alerta": razao,
                "vazao_m3s": vazao_atual,
                "chuva_mm_serie": float(pd.to_numeric(g.get("chuva_mm"), errors="coerce").sum()) if "chuva_mm" in g.columns else np.nan,
                "tendencia_cota_7d": tend,
                "nivel_rio": nivel,
                "score_nivel_rio": LEVEL_ORDER.index(nivel) if nivel in LEVEL_ORDER else 0,
                "dias_com_cota": int(cota_valid.nunique()) if not cota_valid.empty else 0,
                "fonte": "ANA_telemetria",
                "nota": "razão vs P90 da série local (proxy cota de alerta) — alinhado Vigibarragens/IDAP A6",
                "atualizado_em": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["score_nivel_rio", "razao_nivel_cota_alerta"], ascending=[False, False]).reset_index(drop=True)


def merge_niveis_rios_into_resumo(resumo: pd.DataFrame, niveis: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty or niveis is None or niveis.empty:
        return resumo if resumo is not None else pd.DataFrame()
    keep = [
        c
        for c in (
            "cod_ibge",
            "cota_cm",
            "vazao_m3s",
            "razao_nivel_cota_alerta",
            "nivel_rio",
            "tendencia_cota_7d",
            "nome_rio_estacao",
        )
        if c in niveis.columns
    ]
    if len(keep) < 2:
        return resumo
    out = resumo.copy()
    out["cod_ibge"] = _ibge7(out["cod_ibge"]) if "cod_ibge" in out.columns else out.get("cod_ibge")
    m = niveis[keep].drop_duplicates("cod_ibge")
    m["cod_ibge"] = _ibge7(m["cod_ibge"])
    for col in keep:
        if col != "cod_ibge" and col in out.columns:
            out = out.drop(columns=[col])
    return out.merge(m, on="cod_ibge", how="left")
