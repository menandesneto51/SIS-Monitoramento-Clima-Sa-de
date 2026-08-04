# -*- coding: utf-8 -*-
"""Nowcast epidemiológico auxiliar (SRAG / arbovírus).

Princípio C+2 fase B:
- Regras/pipeline continuam mandando no nível SES.
- Este módulo só estima tendência de curto prazo e probabilidade auxiliar de aumento.
- Sem HTTP ofuscado; usa tabelas já persistidas (SIVEP / arboviroses / resumo).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table, write_df
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

TABLE_NOWCAST = "epi_nowcast_municipal_v1"
TABLE_SKILL = "epi_nowcast_skill_resumo_v1"


def _ibge(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = (
            out["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.extract(r"(\d+)", expand=False)
        )
        out["cod_ibge"] = out["cod_ibge"].fillna("").astype(str)
        out["cod_ibge7"] = out["cod_ibge"].str.zfill(7).str[:7]
        out["cod_ibge6"] = out["cod_ibge7"].str[:6]
    return out


def _p_aumento(atual: float, prev: float, z: float | None = None) -> float:
    """Heurística auditável: ratio + z-score opcional → P(aumento) em [0.05, 0.95]."""
    a = float(atual) if pd.notna(atual) else 0.0
    b = float(prev) if pd.notna(prev) else 0.0
    if a <= 0 and b <= 0:
        base = 0.35
    elif b <= 0:
        base = 0.72 if a > 0 else 0.35
    else:
        ratio = a / b
        # sigmoid suave em torno de 1.0
        base = 1.0 / (1.0 + np.exp(-3.0 * (ratio - 1.0)))
    if z is not None and pd.notna(z):
        zv = float(z)
        base = 0.7 * base + 0.3 * (1.0 / (1.0 + np.exp(-0.8 * zv)))
    return float(np.clip(base, 0.05, 0.95))


def _tendencia(atual: float, prev: float) -> str:
    a = float(atual) if pd.notna(atual) else 0.0
    b = float(prev) if pd.notna(prev) else 0.0
    if a <= 0 and b <= 0:
        return "estavel_baixa"
    if b <= 0:
        return "aumento" if a > 0 else "estavel_baixa"
    delta = (a - b) / max(b, 1.0)
    if delta >= 0.25:
        return "aumento"
    if delta <= -0.25:
        return "reducao"
    return "estavel"


def _window_sums_sivep(sivep: pd.DataFrame, days: int = 7) -> pd.DataFrame:
    if sivep is None or sivep.empty:
        return pd.DataFrame()
    s = _ibge(sivep)
    date_col = next((c for c in ("data", "data_sintomas", "data_notificacao") if c in s.columns), None)
    if not date_col or "casos_srag" not in s.columns:
        return pd.DataFrame()
    s[date_col] = pd.to_datetime(s[date_col], errors="coerce")
    s["casos_srag"] = pd.to_numeric(s["casos_srag"], errors="coerce").fillna(0)
    s = s.dropna(subset=[date_col])
    if s.empty:
        return pd.DataFrame()
    tmax = s[date_col].max()
    cur = s[(s[date_col] > tmax - pd.Timedelta(days=days)) & (s[date_col] <= tmax)]
    prev = s[(s[date_col] > tmax - pd.Timedelta(days=2 * days)) & (s[date_col] <= tmax - pd.Timedelta(days=days))]
    key = "cod_ibge6"
    a = cur.groupby(key, as_index=False)["casos_srag"].sum().rename(columns={"casos_srag": "srag_casos_7d"})
    b = prev.groupby(key, as_index=False)["casos_srag"].sum().rename(columns={"casos_srag": "srag_casos_7d_prev"})
    out = a.merge(b, on=key, how="outer").fillna(0)
    out["cod_ibge"] = out[key].astype(str).str.zfill(6) + "0"  # placeholder 7d; join usa 6d
    return out


def build_epi_nowcast(
    resumo: pd.DataFrame | None = None,
    sivep: pd.DataFrame | None = None,
    arbo_mun: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Monta nowcast auxiliar municipal a partir de séries e/ou snapshot do resumo."""
    resumo = resumo if resumo is not None else read_table("resumo_municipal_atual")
    sivep = sivep if sivep is not None else read_table("epi_sivep_srag")
    arbo_mun = arbo_mun if arbo_mun is not None else read_table("epi_arboviroses_municipal")

    if resumo is None or resumo.empty or "cod_ibge" not in resumo.columns:
        return pd.DataFrame()

    base = _ibge(resumo)
    keep = ["cod_ibge", "cod_ibge6", "cod_ibge7"]
    for c in ("municipio", "regional_saude", "casos_srag", "zscore_srag", "casos_arbovirus_7d", "zscore_arbovirus", "incidencia_arbovirus_100k"):
        if c in base.columns:
            keep.append(c)
    out = base[keep].drop_duplicates("cod_ibge").copy()

    # SRAG via série (preferido)
    win = _window_sums_sivep(sivep, days=7)
    if not win.empty:
        tmp = out.merge(win.drop(columns=["cod_ibge"], errors="ignore"), on="cod_ibge6", how="left")
        out["srag_casos_7d"] = pd.to_numeric(tmp.get("srag_casos_7d"), errors="coerce")
        out["srag_casos_7d_prev"] = pd.to_numeric(tmp.get("srag_casos_7d_prev"), errors="coerce")
        out["srag_fonte"] = "epi_sivep_srag_janelas"
    else:
        # snapshot: casos_srag no resumo = janela 14d do enrichment → usa como atual; prev ≈ proxy via z
        atual = (
            pd.to_numeric(out["casos_srag"], errors="coerce").astype(float)
            if "casos_srag" in out.columns
            else pd.Series(np.nan, index=out.index, dtype=float)
        )
        z = (
            pd.to_numeric(out["zscore_srag"], errors="coerce").astype(float)
            if "zscore_srag" in out.columns
            else pd.Series(np.nan, index=out.index, dtype=float)
        )
        out["srag_casos_7d"] = atual
        prev = pd.Series(np.nan, index=out.index, dtype=float)
        for i in out.index:
            a = atual.loc[i]
            zv = z.loc[i]
            if pd.isna(a):
                continue
            if pd.notna(zv) and float(zv) >= 1.0:
                prev.loc[i] = max(float(a) / (1.0 + 0.25 * float(zv)), 0.0)
            else:
                prev.loc[i] = float(a) * 0.9
        out["srag_casos_7d_prev"] = prev
        out["srag_fonte"] = "resumo_snapshot_proxy"

    z_srag = (
        pd.to_numeric(out["zscore_srag"], errors="coerce")
        if "zscore_srag" in out.columns
        else pd.Series(np.nan, index=out.index, dtype=float)
    )
    out["srag_tendencia"] = [
        _tendencia(a, b) for a, b in zip(out["srag_casos_7d"], out["srag_casos_7d_prev"], strict=False)
    ]
    out["srag_p_aumento"] = [
        _p_aumento(a, b, z) for a, b, z in zip(out["srag_casos_7d"], out["srag_casos_7d_prev"], z_srag, strict=False)
    ]

    # Arbovírus — municipal 7d já agregado
    if arbo_mun is not None and not arbo_mun.empty and "cod_ibge" in arbo_mun.columns:
        a = _ibge(arbo_mun)
        cols = [c for c in ("casos_arbovirus_7d", "zscore_arbovirus", "incidencia_arbovirus_100k") if c in a.columns]
        am = a[["cod_ibge6"] + cols].drop_duplicates("cod_ibge6")
        out = out.drop(columns=[c for c in cols if c in out.columns], errors="ignore")
        out = out.merge(am, on="cod_ibge6", how="left")
        out["arbo_fonte"] = "epi_arboviroses_municipal"
    else:
        out["arbo_fonte"] = "resumo_snapshot" if "casos_arbovirus_7d" in out.columns else "indisponivel"

    arbo_now = (
        pd.to_numeric(out["casos_arbovirus_7d"], errors="coerce").astype(float)
        if "casos_arbovirus_7d" in out.columns
        else pd.Series(np.nan, index=out.index, dtype=float)
    )
    z_arbo = (
        pd.to_numeric(out["zscore_arbovirus"], errors="coerce").astype(float)
        if "zscore_arbovirus" in out.columns
        else pd.Series(np.nan, index=out.index, dtype=float)
    )
    arbo_prev = pd.Series(np.nan, index=out.index, dtype=float)
    for i in out.index:
        a = arbo_now.loc[i]
        zv = z_arbo.loc[i]
        if pd.isna(a):
            continue
        if pd.notna(zv) and float(zv) >= 1.0:
            arbo_prev.loc[i] = max(float(a) / (1.0 + 0.2 * float(zv)), 0.0)
        else:
            arbo_prev.loc[i] = float(a) * 0.95
    out["arbo_casos_7d"] = arbo_now
    out["arbo_casos_7d_prev"] = arbo_prev
    out["arbo_tendencia"] = [_tendencia(a, b) for a, b in zip(out["arbo_casos_7d"], out["arbo_casos_7d_prev"], strict=False)]
    out["arbo_p_aumento"] = [
        _p_aumento(a, b, z) for a, b, z in zip(out["arbo_casos_7d"], out["arbo_casos_7d_prev"], z_arbo, strict=False)
    ]

    out["nowcast_alerta"] = np.where(
        (out["srag_p_aumento"].fillna(0) >= 0.65) | (out["arbo_p_aumento"].fillna(0) >= 0.65),
        "atencao_aumento",
        np.where(
            (out["srag_tendencia"] == "aumento") | (out["arbo_tendencia"] == "aumento"),
            "monitorar",
            "estavel",
        ),
    )
    out["nowcast_nota"] = (
        "Camada auxiliar — não altera o nível operacional SES. Validar no território e no boletim oficial."
    )
    out["gerado_em"] = datetime.now().isoformat(timespec="seconds")
    drop_tmp = [c for c in ("cod_ibge6", "cod_ibge7") if c in out.columns]
    return out.drop(columns=drop_tmp, errors="ignore")


def evaluate_epi_nowcast_skill(nowcast: pd.DataFrame) -> pd.DataFrame:
    """Skill leve: coerência tendência vs P(aumento) e cobertura (sem arquivo longo ainda)."""
    if nowcast is None or nowcast.empty:
        return pd.DataFrame(
            [
                {
                    "metodo": "epi_nowcast_aux",
                    "n_municipios": 0,
                    "pct_atencao_aumento": None,
                    "srag_p_media": None,
                    "arbo_p_media": None,
                    "avaliado_em": datetime.now().isoformat(timespec="seconds"),
                }
            ]
        )
    n = len(nowcast)
    atencao = (nowcast.get("nowcast_alerta") == "atencao_aumento").mean() if "nowcast_alerta" in nowcast.columns else None
    row = {
        "metodo": "epi_nowcast_aux",
        "n_municipios": int(n),
        "pct_atencao_aumento": float(atencao) if atencao is not None else None,
        "srag_p_media": float(pd.to_numeric(nowcast.get("srag_p_aumento"), errors="coerce").mean())
        if "srag_p_aumento" in nowcast.columns
        else None,
        "arbo_p_media": float(pd.to_numeric(nowcast.get("arbo_p_aumento"), errors="coerce").mean())
        if "arbo_p_aumento" in nowcast.columns
        else None,
        "n_srag_aumento": int((nowcast.get("srag_tendencia") == "aumento").sum()) if "srag_tendencia" in nowcast.columns else 0,
        "n_arbo_aumento": int((nowcast.get("arbo_tendencia") == "aumento").sum()) if "arbo_tendencia" in nowcast.columns else 0,
        "avaliado_em": datetime.now().isoformat(timespec="seconds"),
        "nota": "Skill descritivo da rodada; backtest temporal exige série SIVEP contínua.",
    }
    return pd.DataFrame([row])


def run_epi_nowcast(resumo: pd.DataFrame | None = None) -> dict[str, Any]:
    """Gera e persiste nowcast epi auxiliar + resumo de skill."""
    summary: dict[str, Any] = {"ok": True}
    try:
        nc = build_epi_nowcast(resumo=resumo)
        write_df(nc if nc is not None else pd.DataFrame(), TABLE_NOWCAST)
        skill = evaluate_epi_nowcast_skill(nc)
        write_df(skill, TABLE_SKILL)
        summary["n_municipios"] = int(len(nc)) if nc is not None else 0
        if skill is not None and not skill.empty:
            summary["skill"] = skill.to_dict(orient="records")[0]
        # merge flags leves no resumo sem tocar nivel
        if resumo is not None and not resumo.empty and nc is not None and not nc.empty and "cod_ibge" in resumo.columns:
            r = resumo.copy()
            r["cod_ibge"] = r["cod_ibge"].astype(str)
            add = nc[
                [
                    c
                    for c in (
                        "cod_ibge",
                        "srag_p_aumento",
                        "arbo_p_aumento",
                        "srag_tendencia",
                        "arbo_tendencia",
                        "nowcast_alerta",
                    )
                    if c in nc.columns
                ]
            ].copy()
            add["cod_ibge"] = add["cod_ibge"].astype(str)
            for c in add.columns:
                if c != "cod_ibge" and c in r.columns:
                    r = r.drop(columns=[c])
            r = r.merge(add, on="cod_ibge", how="left")
            write_df(r, "resumo_municipal_atual")
            summary["merged_resumo"] = True
    except Exception as exc:  # noqa: BLE001
        log.warning("Nowcast epidemiológico falhou: %s", exc)
        summary["ok"] = False
        summary["error"] = str(exc)
    return summary
