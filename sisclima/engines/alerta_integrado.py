# -*- coding: utf-8 -*-
"""Alerta integrado SIS + TITAN (clima + INMET + Cemaden + solo + ANA)."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.engines.stages import STAGE_ORDER

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]

ACAO = {
    "verde": "Monitoramento de rotina SIS+TITAN.",
    "amarela": "Atenção — reforçar vigilância climática e checar alertas oficiais.",
    "laranja": "Alerta — articular regional, assistência e acompanhar INMET/Cemaden.",
    "vermelha": "Resposta intensificada — sala de situação e comunicação à população.",
    "roxa": "Situação excepcional — mobilização plena CIEVS + canais de alerta.",
    "cinza": "Dados insuficientes — priorizar coleta antes de comunicar.",
}


def _nivel_from_score(score: int) -> str:
    s = max(-1, min(4, int(score)))
    return LEVEL_ORDER[s + 1] if s >= 0 else "cinza"


def _score_of(nivel: Any) -> int:
    if nivel is None or (isinstance(nivel, float) and np.isnan(nivel)):
        return -1
    return int(STAGE_ORDER.get(str(nivel).lower().strip(), -1))


def _inmet_nivel_from_row(row: pd.Series) -> str | None:
    for col in ["nivel_alerta", "nivel_sis", "severidade", "risco", "nivel"]:
        if col in row.index and pd.notna(row.get(col)):
            txt = str(row.get(col)).lower()
            if "rox" in txt or "grande perigo" in txt or "muito alto" in txt:
                return "roxa"
            if "vermelh" in txt or "vermelho" in txt:
                return "vermelha"
            if "laranja" in txt or ( "perigo" in txt and "potencial" not in txt):
                return "laranja"
            if "amarel" in txt or "potencial" in txt or "moderad" in txt:
                return "amarela"
    blob = " ".join(str(v) for v in row.values if pd.notna(v)).lower()
    if "grande perigo" in blob or "vermelho" in blob:
        return "vermelha"
    if "laranja" in blob or ("perigo" in blob and "potencial" not in blob):
        return "laranja"
    if "amarelo" in blob or "perigo potencial" in blob:
        return "amarela"
    return None


def _inmet_by_municipio(inmet: pd.DataFrame) -> pd.DataFrame:
    if inmet is None or inmet.empty:
        return pd.DataFrame(columns=["cod_ibge", "municipio", "nivel_inmet", "motivo_inmet"])
    df = inmet.copy()
    rows = []
    for _, r in df.iterrows():
        niv = _inmet_nivel_from_row(r)
        if not niv:
            continue
        rows.append(
            {
                "cod_ibge": str(r.get("cod_ibge") or "").strip() or pd.NA,
                "municipio": r.get("municipio"),
                "nivel_inmet": niv,
                "motivo_inmet": f"INMET {niv}: {r.get('evento') or r.get('descricao') or r.get('nivel_alerta') or 'alerta oficial'}",
            }
        )
    if not rows:
        return pd.DataFrame(columns=["cod_ibge", "municipio", "nivel_inmet", "motivo_inmet"])
    out = pd.DataFrame(rows)
    # pior nível por município (e sem município = estadual)
    out["_ord"] = out["nivel_inmet"].map(STAGE_ORDER).fillna(-1)
    out = out.sort_values("_ord", ascending=False)
    return out


def build_alerta_integrado_municipal(
    resumo: pd.DataFrame,
    inmet_alertas: pd.DataFrame | None = None,
    cemaden_alertas: pd.DataFrame | None = None,
    hidro_risco: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Une estágio SIS (clima/saúde) com camadas TITAN oficiais:
    INMET + Cemaden + saturação do solo + risco hidro ANA.
    nivel_alerta_integrado = max(componentes).
    """
    if resumo is None or resumo.empty:
        return pd.DataFrame()

    base = resumo.copy()
    base["cod_ibge"] = base["cod_ibge"].astype(str)

    inmet_m = _inmet_by_municipio(inmet_alertas if inmet_alertas is not None else pd.DataFrame())
    # Match por IBGE e por nome
    inmet_ibge = inmet_m.dropna(subset=["cod_ibge"]).drop_duplicates("cod_ibge", keep="first")
    inmet_nome = inmet_m.copy()
    if "municipio" in inmet_nome.columns:
        inmet_nome["municipio_key"] = inmet_nome["municipio"].astype(str).str.lower().str.strip()
        inmet_nome = inmet_nome.dropna(subset=["municipio_key"]).drop_duplicates("municipio_key", keep="first")

    cem = cemaden_alertas.copy() if cemaden_alertas is not None and not cemaden_alertas.empty else pd.DataFrame()
    if not cem.empty:
        if "nivel_sis" not in cem.columns and "nivel_alerta" in cem.columns:
            cem["nivel_sis"] = cem["nivel_alerta"]
        cem["cod_ibge"] = cem.get("cod_ibge", pd.Series(dtype=str)).astype(str)
        cem["_ord"] = cem.get("nivel_sis", pd.Series(dtype=str)).astype(str).str.lower().map(STAGE_ORDER).fillna(-1)
        cem = cem.sort_values("_ord", ascending=False).drop_duplicates("cod_ibge", keep="first")

    hidro = hidro_risco.copy() if hidro_risco is not None and not hidro_risco.empty else pd.DataFrame()
    if not hidro.empty and "cod_ibge" in hidro.columns:
        hidro["cod_ibge"] = hidro["cod_ibge"].astype(str)
        hidro = hidro.drop_duplicates("cod_ibge", keep="first")

    # INMET estadual (sem município) eleva todos se for o pior
    inmet_estado = None
    if not inmet_m.empty:
        sem_mun = inmet_m[inmet_m["cod_ibge"].isna() | (inmet_m["cod_ibge"].astype(str).isin(["", "nan", "<NA>"]))]
        if not sem_mun.empty and (inmet_m["municipio"].isna().all() if "municipio" in inmet_m.columns else True):
            inmet_estado = sem_mun.iloc[0]["nivel_inmet"]
        elif not inmet_ibge.empty and inmet_ibge["cod_ibge"].isna().all():
            inmet_estado = inmet_m.iloc[0]["nivel_inmet"]

    rows = []
    for _, row in base.iterrows():
        cod = str(row.get("cod_ibge"))
        mun = row.get("municipio")
        componentes: dict[str, str] = {}
        motivos: list[str] = []

        niv_sis = str(row.get("nivel") or "cinza").lower()
        componentes["sis_estagio"] = niv_sis
        if niv_sis not in ("verde", "cinza"):
            motivos.append(f"SIS estágio {niv_sis}")

        # INMET
        niv_in = None
        if not inmet_ibge.empty and cod in set(inmet_ibge["cod_ibge"].astype(str)):
            hit = inmet_ibge[inmet_ibge["cod_ibge"].astype(str) == cod].iloc[0]
            niv_in = hit["nivel_inmet"]
            motivos.append(str(hit.get("motivo_inmet") or f"INMET {niv_in}"))
        elif mun and not inmet_nome.empty:
            key = str(mun).lower().strip()
            hit2 = inmet_nome[inmet_nome["municipio_key"] == key]
            if not hit2.empty:
                niv_in = hit2.iloc[0]["nivel_inmet"]
                motivos.append(str(hit2.iloc[0].get("motivo_inmet") or f"INMET {niv_in}"))
        if niv_in is None and inmet_estado:
            niv_in = inmet_estado
            motivos.append(f"INMET estadual {inmet_estado}")
        if niv_in:
            componentes["titan_inmet"] = niv_in

        # Cemaden
        if not cem.empty and cod in set(cem["cod_ibge"].astype(str)):
            c = cem[cem["cod_ibge"].astype(str) == cod].iloc[0]
            niv_c = str(c.get("nivel_sis") or c.get("nivel_alerta") or "").lower()
            if niv_c in STAGE_ORDER:
                componentes["titan_cemaden"] = niv_c
                motivos.append(f"Cemaden {niv_c}: {c.get('evento') or c.get('tipo_risco') or ''}".strip())

        # Solo TITAN
        solo = pd.to_numeric(row.get("indice_saturacao_solo"), errors="coerce")
        classe = str(row.get("classe_saturacao_solo") or "").lower()
        if pd.notna(solo):
            if solo >= 85 or classe in ("critica", "crítica"):
                componentes["titan_solo"] = "laranja"
                motivos.append(f"Saturação do solo crítica ({solo:.0f})")
            elif solo >= 70 or classe == "alta":
                componentes["titan_solo"] = "amarela"
                motivos.append(f"Saturação do solo alta ({solo:.0f})")

        # Hidro ANA
        niv_h = row.get("nivel_alerta_hidro")
        if (not niv_h or str(niv_h) in ("nan", "None")) and not hidro.empty:
            h = hidro[hidro["cod_ibge"].astype(str) == cod]
            if not h.empty:
                niv_h = h.iloc[0].get("nivel_alerta_hidro")
        if isinstance(niv_h, str) and niv_h.lower() in STAGE_ORDER and niv_h.lower() != "verde":
            componentes["titan_hidro"] = niv_h.lower()
            motivos.append(f"Hidro ANA {niv_h}")

        # Clima (reforço explícito TITAN)
        utci = pd.to_numeric(row.get("utci_proxy"), errors="coerce")
        risco3 = pd.to_numeric(row.get("risco_cumulativo_3d"), errors="coerce")
        if pd.notna(utci) and utci >= 38:
            componentes["titan_calor"] = "vermelha" if utci >= 46 else "laranja"
            motivos.append(f"UTCI/proxy {utci:.1f}")
        elif pd.notna(utci) and utci >= 32:
            componentes["titan_calor"] = "amarela"
            motivos.append(f"UTCI/proxy {utci:.1f}")
        if pd.notna(risco3) and risco3 >= 12:
            componentes["titan_risco3d"] = "vermelha" if risco3 >= 18 else "laranja"
            motivos.append(f"Risco cumulativo 3d {risco3:.1f}")
        elif pd.notna(risco3) and risco3 >= 7:
            componentes.setdefault("titan_risco3d", "amarela")
            motivos.append(f"Risco cumulativo 3d {risco3:.1f}")

        scores = [_score_of(v) for v in componentes.values()]
        score = max(scores) if scores else _score_of(niv_sis)
        nivel = _nivel_from_score(score) if score >= 0 else "cinza"
        # se só cinza/verde sis e nada titan
        if not componentes:
            nivel = niv_sis if niv_sis in STAGE_ORDER else "cinza"
            score = _score_of(nivel)

        dominante = max(componentes.items(), key=lambda kv: _score_of(kv[1]))[0] if componentes else "sis_estagio"
        rows.append(
            {
                "cod_ibge": cod,
                "municipio": mun,
                "regional_saude": row.get("regional_saude"),
                "nivel_sis": niv_sis,
                "nivel_alerta_integrado": nivel,
                "score_alerta_integrado": int(max(score, 0)),
                "componente_dominante": dominante,
                "componentes_json": str(componentes),
                "motivo_integrado": "; ".join(motivos[:8]) if motivos else "sem gatilho integrado",
                "acao_recomendada": ACAO.get(nivel, ACAO["cinza"]),
                "fonte": "SIS+TITAN",
                "indice_saturacao_solo": row.get("indice_saturacao_solo"),
                "utci_proxy": row.get("utci_proxy"),
                "risco_cumulativo_3d": row.get("risco_cumulativo_3d"),
                "tmax": row.get("tmax"),
                "ocupacao_leitos_pct": row.get("ocupacao_leitos_pct"),
                "pressao_calor_pct": row.get("pressao_calor_pct"),
            }
        )

    out = pd.DataFrame(rows)
    out["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    out["nota_tecnica"] = (
        "Alerta integrado SIS+TITAN: max(estágio SIS, INMET, Cemaden, solo, hidro, calor). "
        "Ecológico/operacional — validar com CIEVS antes de comunicação oficial."
    )
    return out.sort_values(["score_alerta_integrado", "municipio"], ascending=[False, True])
