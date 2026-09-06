# -*- coding: utf-8 -*-
"""Picos de Tmáx na janela da SE / últimos dias (hist_clima_municipal_diario)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

LIMIAR_41 = 41.0
LIMIAR_37 = 37.0
COD_CUIABA6 = "510340"


def resumo_picos_termicos(
    *,
    ref: date | None = None,
    janela_dias: int = 14,
    limiar_alto: float = LIMIAR_41,
    limiar_base: float = LIMIAR_37,
    top_n: int = 12,
) -> dict[str, Any]:
    """Ranking de picos municipais e contagens ≥41 / ≥37 na janela."""
    out: dict[str, Any] = {
        "ok": False,
        "janela_inicio": None,
        "janela_fim": None,
        "tmax_max_semana": None,
        "n_tmax_41": 0,
        "n_tmax_40": 0,
        "n_tmax_37": 0,
        "n_municipios_janela": 0,
        "ranking_41": [],
        "ranking_40": [],
        "ranking_37": [],
        "cuiaba_grade": None,
    }
    if not table_exists("hist_clima_municipal_diario"):
        return out
    hist = read_table("hist_clima_municipal_diario")
    if hist is None or hist.empty:
        return out

    fim = ref or date.today()
    ini = fim - timedelta(days=max(1, janela_dias) - 1)
    h = hist.copy()
    h["cod6"] = h["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str[:6]
    h["data"] = pd.to_datetime(h["data"], errors="coerce")
    h["tmax"] = pd.to_numeric(h.get("tmax"), errors="coerce")
    mun_col = next((c for c in ("municipio", "nome_municipio", "nm_mun") if c in h.columns), None)
    if mun_col is None:
        h["municipio"] = h["cod6"]
        mun_col = "municipio"
    h = h.dropna(subset=["data", "tmax"])
    mask = (h["data"] >= pd.Timestamp(ini)) & (h["data"] <= pd.Timestamp(fim))
    w = h.loc[mask].copy()
    if w.empty:
        return out

    # Um valor por município/dia (última fonte)
    sort_cols = ["cod6", "data"]
    if "fonte" in w.columns:
        sort_cols.append("fonte")
    w = w.sort_values(sort_cols).drop_duplicates(["cod6", "data"], keep="last")

    idx_max = w.groupby("cod6")["tmax"].idxmax()
    pico_det = w.loc[idx_max, ["cod6", "data", "tmax"]].rename(
        columns={"data": "data_pico", "tmax": "tmax_max"}
    )
    pico_det["data_pico"] = pico_det["data_pico"].dt.strftime("%Y-%m-%d")

    # Nomes a partir do resumo municipal
    nomes: dict[str, str] = {}
    try:
        if table_exists("resumo_municipal_atual"):
            res = read_table("resumo_municipal_atual")
            if res is not None and not res.empty:
                rc = res.copy()
                rc["cod6"] = rc["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True).str[:6]
                mun_c = next(
                    (c for c in ("municipio", "nome_municipio", "nm_mun") if c in rc.columns),
                    None,
                )
                if mun_c:
                    for _, row in rc.iterrows():
                        nomes[str(row["cod6"])] = str(row[mun_c])
    except Exception as exc:  # noqa: BLE001
        log.warning("Nomes municipais para picos indisponíveis: %s", exc)
    pico_det["municipio"] = pico_det["cod6"].map(lambda c: nomes.get(str(c), str(c)))
    pico_det = pico_det.sort_values("tmax_max", ascending=False)

    n_mun = int(pico_det["cod6"].nunique())
    n41 = int((pico_det["tmax_max"] >= limiar_alto).sum())
    n40 = int((pico_det["tmax_max"] >= 40.0).sum())
    n37 = int((pico_det["tmax_max"] >= limiar_base).sum())
    tmax_max = float(pico_det["tmax_max"].max()) if not pico_det.empty else None

    def _rank(limiar: float) -> list[dict[str, Any]]:
        return [
            {
                "municipio": str(r["municipio"]),
                "cod_ibge": str(r["cod6"]),
                "tmax_max": float(r["tmax_max"]),
                "data_pico": str(r["data_pico"]),
            }
            for _, r in pico_det[pico_det["tmax_max"] >= limiar].head(top_n).iterrows()
        ]

    ranking_41 = _rank(limiar_alto)
    ranking_40 = _rank(40.0)
    ranking_37 = _rank(limiar_base)

    cui = pico_det[pico_det["cod6"] == COD_CUIABA6]
    cuiaba_grade = None
    if not cui.empty:
        r = cui.iloc[0]
        cuiaba_grade = {
            "tmax_max": float(r["tmax_max"]),
            "data_pico": str(r["data_pico"]),
            "fonte": "grade_openmeteo",
        }

    out.update(
        {
            "ok": True,
            "janela_inicio": ini.isoformat(),
            "janela_fim": fim.isoformat(),
            "tmax_max_semana": tmax_max,
            "n_tmax_41": n41,
            "n_tmax_40": n40,
            "n_tmax_37": n37,
            "n_municipios_janela": n_mun,
            "ranking_41": ranking_41,
            "ranking_40": ranking_40,
            "ranking_37": ranking_37,
            "cuiaba_grade": cuiaba_grade,
        }
    )
    return out
