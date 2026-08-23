# -*- coding: utf-8 -*-
"""Correlações exploratórias clima–saúde (Spearman) — motor reutilizável."""
from __future__ import annotations

import math
from math import erfc

import pandas as pd

EXPOSICOES = [
    "tmax",
    "tmedia",
    "utci_proxy",
    "heat_index",
    "risco_calor_diario",
    "risco_cumulativo_3d",
    "ehf_adaptado",
    "pm25_ugm3",
    "pm10_ugm3",
    "o3_ugm3",
    "iq_ar_score",
    "precipitacao_mm",
    "chuva_mm",
    "chuva_mm_ana",
    "nivel_chuva",
    "indice_vulnerabilidade_calor",
]

DESFECHOS = [
    "casos_srag",
    "incidencia_srag_100k",
    "zscore_srag",
    "letalidade_pct",
    "prop_uti_pct",
    "casos_arbovirus_7d",
    "incidencia_arbovirus_100k",
    "zscore_arbovirus",
    "obitos",
    "obitos_calor_suspeitos",
    "positividade_pct",
    "positividade_lacen_pct",
    "positividade_viral_pct",
    "ocupacao_leitos_pct",
    "pressao_calor_pct",
    "score",
]


def compute_spearman_pairs(df: pd.DataFrame, min_n: int = 12) -> pd.DataFrame:
    """Calcula pares exposição→desfecho com rho de Spearman no corte municipal."""
    if df is None or df.empty:
        return pd.DataFrame()

    work = df.copy()
    if "cod_ibge" in work.columns:
        work = work.drop_duplicates("cod_ibge", keep="first")

    expos = [c for c in EXPOSICOES if c in work.columns]
    desf = [c for c in DESFECHOS if c in work.columns]
    if not expos or not desf:
        return pd.DataFrame()

    for c in expos + desf:
        work[c] = pd.to_numeric(work[c], errors="coerce")

    rows: list[dict] = []
    for exp in expos:
        for des in desf:
            if exp == des:
                continue
            pair = work[[exp, des]].dropna()
            n = len(pair)
            if n < min_n:
                continue
            if pair[exp].nunique() < 2 or pair[des].nunique() < 2:
                continue
            ranked = pair.rank(method="average")
            rho = ranked[exp].corr(ranked[des], method="pearson")
            if pd.isna(rho):
                continue
            z = 0.5 * math.log((1 + abs(rho) - 1e-9) / (1 - abs(rho) + 1e-9)) if abs(rho) < 0.999 else 3.0
            se = 1.0 / math.sqrt(max(n - 3, 1))
            p_approx = float(erfc(abs(z) / se / math.sqrt(2)))
            rows.append(
                {
                    "exposicao": exp,
                    "desfecho": des,
                    "metodo": "spearman_municipal",
                    "rho": float(rho),
                    "abs_rho": float(abs(rho)),
                    "p_valor_approx": p_approx,
                    "n_municipios": n,
                    "nota": "Exploratório ecológico — não implica causalidade individual",
                }
            )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("abs_rho", ascending=False).reset_index(drop=True)
