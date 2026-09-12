# -*- coding: utf-8 -*-
"""Indicadores compostos leves (sem ETL novo) — fumaça sem PM, pressão×RIT, completude Sala."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

COMPOSTOS_COLS = [
    "sinal_fumaca_sem_pm",
    "pressao_x_rit",
    "pressao_faixa",
    "completude_sala_pct",
    "gap_fumaca_nebulizacao",
    "pressao_x_resiliencia",
]

_IRM_ORDER = {
    "baixa": 0,
    "moderada": 1,
    "adequada": 2,
    "alta": 3,
    "muito_alta": 4,
}


def _faixa_0_100(v: float | None) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    x = float(v)
    if x < 25:
        return "verde"
    if x < 50:
        return "amarela"
    if x < 70:
        return "laranja"
    if x < 85:
        return "vermelha"
    return "roxa"


def _focos(row: pd.Series) -> float | None:
    for c in ("focos_queimadas_24h", "focos_24h", "focos_inpe_24h", "focos_queimadas_7d", "focos_7d"):
        if c in row.index:
            x = pd.to_numeric(row.get(c), errors="coerce")
            if pd.notna(x) and float(x) > 0:
                return float(x)
    return None


def _completude_row(row: pd.Series) -> float:
    """% de fontes críticas com dado útil nesta linha."""
    checks: list[bool] = []
    # clima
    checks.append(pd.notna(pd.to_numeric(row.get("tmax"), errors="coerce")))
    checks.append(pd.notna(pd.to_numeric(row.get("utci_proxy"), errors="coerce")))
    # ar
    pm = pd.to_numeric(row.get("pm25_ugm3"), errors="coerce")
    focos = _focos(row)
    checks.append(pd.notna(pm) or (focos is not None))
    # assistência
    checks.append(pd.notna(pd.to_numeric(row.get("ocupacao_leitos_pct"), errors="coerce")))
    checks.append(pd.notna(pd.to_numeric(row.get("indice_pressao_saude"), errors="coerce"))
                   or pd.notna(pd.to_numeric(row.get("kpi_sisreg_solicitacoes"), errors="coerce")))
    # internação CID clima (IndicaSUS/DW) — reforça pressão assistencial
    if "internacoes_cid_clima_7d" in row.index:
        checks.append(pd.notna(pd.to_numeric(row.get("internacoes_cid_clima_7d"), errors="coerce")))
    # EHF / RIT
    checks.append(pd.notna(pd.to_numeric(row.get("ehf_geocalor", row.get("ehf")), errors="coerce")))
    checks.append(pd.notna(pd.to_numeric(row.get("rit_0_100"), errors="coerce")))
    # vigilância opcional (conta se coluna existe)
    for c in ("sisagua_monitoramento_valido", "entomologia_iip", "denuncias_sla_ok", "n_intox_fumaca_7d", "casos_extras_clima_7d"):
        if c in row.index:
            checks.append(pd.notna(row.get(c)))
    n = len(checks) or 1
    return round(100.0 * sum(1 for x in checks if x) / n, 1)


def enrich_indicadores_compostos(resumo: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta sinal_fumaca_sem_pm, pressao_x_rit, completude_sala_pct.

    `sinal_fumaca_sem_pm` = 1 se (focos>0 e PM nulo) **ou** intoxicação fumaça DW > 0 (7d).
    """
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()
    out = resumo.copy()

    fumaca = []
    pressao_faixa = []
    pressao_x_rit = []
    gap_neb = []
    pressao_x_res = []
    completude = []

    for _, row in out.iterrows():
        pm = pd.to_numeric(row.get("pm25_ugm3"), errors="coerce")
        focos = _focos(row)
        intox_f = pd.to_numeric(row.get("n_intox_fumaca_7d"), errors="coerce")
        sinal_focos = focos is not None and focos > 0 and pd.isna(pm)
        sinal_dw = pd.notna(intox_f) and float(intox_f) > 0
        sinal = 1 if (sinal_focos or sinal_dw) else 0
        fumaca.append(sinal)

        neb = pd.to_numeric(row.get("equipamentos_nebulizacao"), errors="coerce")
        # Gap: sinal de fumaça e ausência explícita de nebulizadores (0 conhecido)
        if sinal == 1 and pd.notna(neb) and float(neb) <= 0:
            gap_neb.append(1)
        else:
            gap_neb.append(0)

        press = pd.to_numeric(row.get("indice_pressao_saude"), errors="coerce")
        pf = _faixa_0_100(float(press) if pd.notna(press) else None)
        pressao_faixa.append(pf)
        rf = str(row.get("rit_faixa") or "").strip().lower() or None
        if not rf and pd.notna(pd.to_numeric(row.get("rit_0_100"), errors="coerce")):
            rf = _faixa_0_100(float(row.get("rit_0_100")))
        if pf and rf and pf != rf:
            po = STAGE_ORDER.get(pf, -1)
            ro = STAGE_ORDER.get(rf, -1)
            if po >= 0 and ro >= 0:
                pressao_x_rit.append(f"{pf}>{rf}" if po > ro else f"{pf}<{rf}")
            else:
                pressao_x_rit.append(f"{pf}≠{rf}")
        else:
            pressao_x_rit.append(None)

        irm_f = str(row.get("irm_faixa") or "").strip().lower() or None
        if irm_f in ("—", "-", "nan", "none"):
            irm_f = None
        if pf and irm_f and irm_f in _IRM_ORDER:
            # Pressão alta + resiliência baixa = tensão
            po = STAGE_ORDER.get(pf, -1)
            io = _IRM_ORDER[irm_f]
            # Mapear IRM para escala 0–4 invertida (baixa capacidade ≈ risco)
            frag_ord = 4 - io
            if po >= 0 and po != frag_ord and (po >= 2 or frag_ord >= 2):
                pressao_x_res.append(f"pressao:{pf}|irm:{irm_f}")
            else:
                pressao_x_res.append(None)
        else:
            pressao_x_res.append(None)

        completude.append(_completude_row(row))

    out["sinal_fumaca_sem_pm"] = fumaca
    out["pressao_faixa"] = pressao_faixa
    out["pressao_x_rit"] = pressao_x_rit
    out["gap_fumaca_nebulizacao"] = gap_neb
    out["pressao_x_resiliencia"] = pressao_x_res
    out["completude_sala_pct"] = completude
    return out


def resumo_compostos_estadual(resumo: pd.DataFrame) -> dict[str, Any]:
    if resumo is None or resumo.empty:
        return {"disponivel": False}
    n = max(len(resumo), 1)
    n_fum = int(pd.to_numeric(resumo.get("sinal_fumaca_sem_pm"), errors="coerce").fillna(0).sum()) if "sinal_fumaca_sem_pm" in resumo.columns else 0
    n_px = int(resumo["pressao_x_rit"].notna().sum()) if "pressao_x_rit" in resumo.columns else 0
    n_gap = int(pd.to_numeric(resumo.get("gap_fumaca_nebulizacao"), errors="coerce").fillna(0).sum()) if "gap_fumaca_nebulizacao" in resumo.columns else 0
    n_pr = int(resumo["pressao_x_resiliencia"].notna().sum()) if "pressao_x_resiliencia" in resumo.columns else 0
    n_extras = int(pd.to_numeric(resumo.get("casos_extras_clima_7d"), errors="coerce").fillna(0).gt(0).sum()) if "casos_extras_clima_7d" in resumo.columns else 0
    irm_med = pd.to_numeric(resumo.get("indice_resiliencia_municipal_0_100"), errors="coerce").median() if "indice_resiliencia_municipal_0_100" in resumo.columns else None
    comp = pd.to_numeric(resumo.get("completude_sala_pct"), errors="coerce").median() if "completude_sala_pct" in resumo.columns else None
    return {
        "disponivel": True,
        "n_sinal_fumaca_sem_pm": n_fum,
        "n_pressao_x_rit": n_px,
        "n_gap_fumaca_nebulizacao": n_gap,
        "n_pressao_x_resiliencia": n_pr,
        "n_mun_extras_clima": n_extras,
        "irm_mediana": None if irm_med is None or pd.isna(irm_med) else float(irm_med),
        "completude_sala_mediana": None if comp is None or pd.isna(comp) else float(comp),
        "n_municipios": n,
    }
