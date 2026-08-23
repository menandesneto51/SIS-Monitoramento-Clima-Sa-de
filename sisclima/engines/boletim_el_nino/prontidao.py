# -*- coding: utf-8 -*-
"""Índice de prioridade de preparação municipal clima–saúde."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.engines.boletim_el_nino.constants import INDISPONIVEL, NAO_CALCULADO
from sisclima.engines.boletim_el_nino.formatters import fmt_num, md_table
from sisclima.engines.stages import STAGE_ORDER

_RISCO_100 = {nome: max(0, (int(ord_) + 1) * 20) for nome, ord_ in STAGE_ORDER.items()}
_NIVEL_PT = {
    "verde": "Verde",
    "amarela": "Amarela",
    "laranja": "Laranja",
    "vermelha": "Vermelha",
    "roxa": "Roxa",
    "cinza": "Cinza",
}


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _faixa(pr: float) -> str:
    if pr >= 75:
        return "Crítica"
    if pr >= 55:
        return "Alta"
    if pr >= 35:
        return "Moderada"
    return "Acompanhamento"


def _nivel_pt(v: Any) -> str:
    return _NIVEL_PT.get(str(v or "").lower().strip(), str(v or "—").title())


def _pick_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _rank_0_100(s: pd.Series) -> pd.Series:
    """Normaliza para 0–100 por percentil empírico (comparável entre dimensões)."""
    x = pd.to_numeric(s, errors="coerce")
    if x.notna().sum() < 3:
        return x
    # average rank → 0–100
    r = x.rank(method="average", pct=True) * 100.0
    return r


def compute_prontidao(resumo: pd.DataFrame) -> dict[str, Any]:
    """Calcula necessidade de preparação (maior = maior urgência de preparação).

    Gera internamente score_pressao, score_exposicao, score_vulnerabilidade e
    score_prioridade_operacional (todos 0–100 por percentil) antes de escolher
    o determinante, evitando que uma escala bruta (ex.: pressão mediana 53 vs
    alerta 0–4) domine artificialmente.
    """
    if resumo is None or resumo.empty or "nivel" not in resumo.columns:
        return {"disponivel": False, "tabela_md": INDISPONIVEL, "top": [], "validado": False}

    df = resumo.copy()
    df["_risco"] = df["nivel"].astype(str).str.lower().str.strip().map(_RISCO_100)

    pressao_col = _pick_col(df, ("indice_pressao_saude", "pressao_rede_climatica"))
    expos_col = _pick_col(df, ("indice_exposicao_vulneravel", "indice_tensao_climatica"))
    vulner_col = _pick_col(df, ("indice_vulnerabilidade_calor",))
    prio_col = _pick_col(df, ("indice_prioridade_global",))

    df["score_pressao"] = _rank_0_100(df[pressao_col]) if pressao_col else np.nan
    df["score_exposicao"] = _rank_0_100(df[expos_col]) if expos_col else np.nan
    df["score_vulnerabilidade"] = _rank_0_100(df[vulner_col]) if vulner_col else np.nan
    df["score_prioridade_operacional"] = _rank_0_100(df[prio_col]) if prio_col else np.nan

    # Score composto (média ponderada renormalizada dos disponíveis)
    pesos = {
        "score_prioridade_operacional": 0.30,
        "score_exposicao": 0.25,
        "score_vulnerabilidade": 0.20,
        "score_pressao": 0.25,
    }
    scores: list[float] = []
    dets: list[str] = []
    dets2: list[str] = []
    rotulos = {
        "score_pressao": "pressão assistencial",
        "score_exposicao": "exposição ambiental",
        "score_vulnerabilidade": "vulnerabilidade",
        "score_prioridade_operacional": "prioridade operacional",
    }

    for idx, row in df.iterrows():
        usados: list[tuple[str, float, float]] = []
        for col, peso in pesos.items():
            val = row.get(col)
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                usados.append((col, float(val), peso))
        if not usados:
            scores.append(float("nan"))
            dets.append(INDISPONIVEL)
            dets2.append("")
            continue
        soma_w = sum(w for _, _, w in usados)
        score = sum(v * w for _, v, w in usados) / soma_w
        scores.append(float(min(100.0, max(0.0, score))))

        ordenados = sorted(usados, key=lambda t: t[1], reverse=True)
        dets.append(rotulos.get(ordenados[0][0], ordenados[0][0]))
        dets2.append(rotulos.get(ordenados[1][0], ordenados[1][0]) if len(ordenados) > 1 else "")

    df["_prep"] = scores
    df["_determinante"] = dets
    df["_determinante2"] = dets2

    # Diagnóstico de monopolização
    vc = pd.Series([d for d in dets if d and d != INDISPONIVEL]).value_counts(normalize=True)
    monopolio = bool(len(vc) and float(vc.iloc[0]) >= 0.70)

    ranked = df.sort_values("_prep", ascending=False, na_position="last").head(15)
    rows: list[list[str]] = []
    top: list[dict[str, Any]] = []
    for _, row in ranked.iterrows():
        pr = row.get("_prep")
        if pr is None or (isinstance(pr, float) and pd.isna(pr)):
            continue
        pr_f = float(pr)
        det1 = str(row.get("_determinante") or "—")
        det2 = str(row.get("_determinante2") or "").strip()
        det_txt = det1 if not det2 else f"{det1}; 2º: {det2}"
        rows.append(
            [
                str(row.get("municipio") or "—"),
                str(row.get("regional_saude") or "—"),
                _nivel_pt(row.get("nivel")),
                fmt_num(pr_f, 1),
                _faixa(pr_f),
                det_txt,
            ]
        )
        top.append({"municipio": row.get("municipio"), "prontidao": pr_f, "faixa": _faixa(pr_f), "determinante": det1})

    n_calc = int(pd.Series(scores).notna().sum())
    n_sat = int((pd.Series(scores) >= 99.5).sum())
    validado = n_calc > 0 and (n_sat / max(n_calc, 1) < 0.8)

    nota = (
        "O **índice de prioridade de preparação** (0–100) expressa a **necessidade** de preparação "
        "clima–saúde (maior valor = maior urgência). Internamente combina `score_pressao`, "
        "`score_exposicao`, `score_vulnerabilidade` e `score_prioridade_operacional`, "
        "normalizados em percentil 0–100 antes da ponderação, para evitar domínio artificial "
        "de uma escala bruta. A classe climática atual é contexto territorial e não entra no score."
    )
    if monopolio:
        nota += (
            " **Nota metodológica:** uma dimensão ainda concentra a maioria dos determinantes "
            "desta rodada após normalização — revisar pesos/escalas nas próximas emissões."
        )
    if not validado:
        nota += " **Índice não publicado para decisão nesta rodada** (saturação ou dados insuficientes)."

    tabela = md_table(
        [
            "Município",
            "Regional",
            "Classe atual",
            "Prioridade de preparação (0–100)",
            "Faixa",
            "Determinantes (1º; 2º)",
        ],
        rows if validado else [],
        vazio=NAO_CALCULADO if not validado else INDISPONIVEL,
    )

    return {
        "disponivel": True,
        "validado": validado,
        "tabela_md": tabela,
        "nota": nota,
        "top": top if validado else [],
        "n_calculados": n_calc,
        "n_saturados_100": n_sat,
        "tem_determinante": True,
        "monopolio_determinante": monopolio,
        "titulo": "Índice de prioridade de preparação clima–saúde",
    }
