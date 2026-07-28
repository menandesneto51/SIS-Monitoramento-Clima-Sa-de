from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd


# ============================================================
# SIS MT CLIMA-SAÚDE
# Arquivo: sisclima/engines/stages.py
#
# Objetivo:
# - Classificar estágio operacional de calor/extremos climáticos.
# - Evitar falso "verde" quando indicadores essenciais estiverem indisponíveis.
# - Retornar "cinza" quando a classificação de risco não tiver base mínima.
#
# Lógica operacional:
# - Verde só é permitido quando houver ao menos um bloco essencial válido:
#   bloco climático ou bloco assistencial.
# - Sem bloco essencial válido e sem gatilho operacional relevante:
#   nível = cinza, status = dados insuficientes.
# ============================================================


STAGE_ORDER = {
    "cinza": -1,
    "verde": 0,
    "amarela": 1,
    "laranja": 2,
    "vermelha": 3,
    "roxa": 4,
}

STAGE_LABELS = {
    -1: "cinza",
    0: "verde",
    1: "amarela",
    2: "laranja",
    3: "vermelha",
    4: "roxa",
}


@dataclass
class StageResult:
    nivel: str
    score: int
    motivos: list[str]
    indicadores: dict[str, Any]


def _is_valid_number(v: Any) -> bool:
    if v is None:
        return False
    try:
        if pd.isna(v):
            return False
    except Exception:
        pass
    try:
        x = float(v)
    except Exception:
        return False
    if math.isnan(x) or math.isinf(x):
        return False
    return True


def _to_float(v: Any) -> float | None:
    if not _is_valid_number(v):
        return None
    try:
        return float(v)
    except Exception:
        return None


def _valid_any(latest: dict, keys: list[str]) -> bool:
    return any(_is_valid_number(latest.get(k)) for k in keys)


def _clean_motivos(motivos: list[str]) -> list[str]:
    seen = set()
    out = []
    for m in motivos:
        if not m:
            continue
        m = str(m).strip()
        if not m or m in seen:
            continue
        out.append(m)
        seen.add(m)
    return out


def _label(score: int) -> str:
    return STAGE_LABELS.get(int(score), "verde")


def stage_from_utci(v: float, thresholds: dict) -> tuple[int, str]:
    x = _to_float(v)
    if x is None:
        return 0, "UTCI/proxy indisponível"

    if x > thresholds.get("vermelha_max", 46):
        return 4, f"UTCI/proxy {x:.1f} > {thresholds.get('vermelha_max', 46)}"
    if x > thresholds.get("laranja_max", 38):
        return 3, f"UTCI/proxy {x:.1f} entre {thresholds.get('laranja_max', 38)} e {thresholds.get('vermelha_max', 46)}"
    if x > thresholds.get("amarela_max", 32):
        return 2, f"UTCI/proxy {x:.1f} entre {thresholds.get('amarela_max', 32)} e {thresholds.get('laranja_max', 38)}"
    if x > thresholds.get("verde_max", 26):
        return 1, f"UTCI/proxy {x:.1f} entre {thresholds.get('verde_max', 26)} e {thresholds.get('amarela_max', 32)}"

    return 0, f"UTCI/proxy {x:.1f} em normalidade"


def stage_from_tmax(tmax: float, thresholds: dict) -> tuple[int, str]:
    x = _to_float(tmax)
    if x is None:
        return 0, "Tmax indisponível"

    if x >= thresholds.get("roxa", 43):
        return 4, f'Tmax {x:.1f} >= {thresholds.get("roxa", 43)}'
    if x >= thresholds.get("vermelha", 41):
        return 3, f'Tmax {x:.1f} >= {thresholds.get("vermelha", 41)}'
    if x >= thresholds.get("laranja", 39):
        return 2, f'Tmax {x:.1f} >= {thresholds.get("laranja", 39)}'
    if x >= thresholds.get("amarela", 37):
        return 1, f'Tmax {x:.1f} >= {thresholds.get("amarela", 37)}'

    return 0, f"Tmax {x:.1f} sem gatilho"


def stage_from_value(
    v: float,
    thresholds: dict,
    higher_is_worse: bool = True,
    name: str = "indicador",
) -> tuple[int, str]:
    x = _to_float(v)
    if x is None:
        return 0, f"{name} indisponível"

    levels = [("roxa", 4), ("vermelha", 3), ("laranja", 2), ("amarela", 1)]

    for key, score in levels:
        if key not in thresholds:
            continue

        cut = thresholds[key]

        if higher_is_worse and x >= cut:
            return score, f"{name} {x:.2f} atingiu {key}"
        if not higher_is_worse and x <= cut:
            return score, f"{name} {x:.2f} atingiu {key}"

    return 0, f"{name} {x:.2f} sem gatilho"


def stage_from_stock_autonomy(days: float, thresholds: dict) -> tuple[int, str]:
    x = _to_float(days)

    if x is None:
        return 0, "Autonomia de insumos indisponível/infinita"

    if x <= thresholds.get("vermelha_min", 3):
        return 4, f"Autonomia crítica {x:.1f} dias"
    if x <= thresholds.get("laranja_min", 7):
        return 3, f"Autonomia abaixo do piso estratégico: {x:.1f} dias"
    if x <= thresholds.get("amarela_min", 10):
        return 2, f"Autonomia baixa: {x:.1f} dias"
    if x <= thresholds.get("verde_min", 14):
        return 1, f"Autonomia em atenção: {x:.1f} dias"

    return 0, f"Autonomia adequada: {x:.1f} dias"


def classify_stage(latest: dict, settings: dict) -> StageResult:
    latest = latest or {}
    settings = settings or {}

    motivos: list[str] = []
    candidates: list[int] = []
    indicadores = dict(latest)

    lim_calor = settings.get("limiares_calor", {})
    lim_assist = settings.get("limiares_assistenciais", {})
    lim_oper = settings.get("limiares_operacionais", {})
    cfg_aq = settings.get("qualidade_ar", {})

    # --------------------------------------------------------
    # Bloco climático
    # --------------------------------------------------------
    s, m = stage_from_utci(latest.get("utci_proxy"), lim_calor.get("utci", {}))
    candidates.append(s)
    motivos.append(m)

    s, m = stage_from_tmax(latest.get("tmax"), lim_calor.get("tmax_fallback", {}))
    candidates.append(s)
    motivos.append(m)

    s, m = stage_from_value(
        latest.get("risco_cumulativo_3d"),
        lim_calor.get("risco_cumulativo", {}),
        True,
        "risco cumulativo 3d",
    )
    candidates.append(s)
    motivos.append(m)

    # Campos compatíveis com próxima etapa P95/onda de calor.
    if _is_valid_number(latest.get("onda_calor_p95_2d")):
        if float(latest.get("onda_calor_p95_2d")) >= 1:
            candidates.append(max(1, int(latest.get("severidade_onda_calor", 1) or 1)))
            motivos.append("onda de calor P95 ≥ 2 dias detectada")
        else:
            candidates.append(0)
            motivos.append("onda de calor P95 ≥ 2 dias não detectada")

    # Saturação do solo (camada TITAN)
    lim_solo = lim_calor.get("saturacao_solo", {"amarela": 70, "laranja": 85, "vermelha": 95})
    s, m = stage_from_value(
        latest.get("indice_saturacao_solo"),
        lim_solo,
        True,
        "saturação do solo",
    )
    if _is_valid_number(latest.get("indice_saturacao_solo")):
        candidates.append(s)
        motivos.append(m)

    # Alertas oficiais já mesclados no resumo (INMET/Cemaden/hidro) quando presentes
    for key, label in [
        ("nivel_inmet", "alerta INMET"),
        ("nivel_cemaden", "alerta Cemaden"),
        ("nivel_alerta_hidro", "risco hidro ANA"),
    ]:
        niv = latest.get(key)
        if isinstance(niv, str) and niv.lower() in STAGE_ORDER:
            sc = STAGE_ORDER[niv.lower()]
            if sc >= 0:
                candidates.append(sc)
                motivos.append(f"{label} {niv.lower()}")

    # --------------------------------------------------------
    # Bloco assistencial
    # --------------------------------------------------------
    s, m = stage_from_value(
        latest.get("pressao_calor_pct"),
        lim_assist.get("pressao_calor_pct", {}),
        True,
        "pressão assistencial",
    )
    candidates.append(s)
    motivos.append(m)

    s, m = stage_from_value(
        latest.get("ocupacao_leitos_pct"),
        lim_assist.get("ocupacao_leitos_pct", {}),
        True,
        "ocupação de leitos",
    )
    candidates.append(s)
    motivos.append(m)

    s, m = stage_from_value(
        latest.get("zscore_pressao"),
        lim_assist.get("zscore", {}),
        True,
        "z-score assistencial",
    )
    candidates.append(s)
    motivos.append(m)

    # Campos epidemiológicos adicionais, sem quebrar compatibilidade.
    s, m = stage_from_value(
        latest.get("zscore_srag"),
        lim_assist.get("zscore_srag", lim_assist.get("zscore", {})),
        True,
        "z-score SRAG",
    )
    if _is_valid_number(latest.get("zscore_srag")):
        candidates.append(s)
        motivos.append(m)

    s, m = stage_from_value(
        latest.get("incidencia_srag_100k"),
        lim_assist.get("incidencia_srag_100k", {}),
        True,
        "incidência SRAG/100 mil",
    )
    if _is_valid_number(latest.get("incidencia_srag_100k")) and float(latest.get("incidencia_srag_100k") or 0) > 0:
        candidates.append(s)
        motivos.append(m)

    letal = latest.get("letalidade_srag_pct", latest.get("letalidade_pct"))
    s, m = stage_from_value(letal, lim_assist.get("letalidade_srag_pct", {}), True, "letalidade SRAG")
    if _is_valid_number(letal) and float(letal or 0) > 0:
        candidates.append(s)
        motivos.append(m)

    prop_uti = latest.get("prop_uti_pct", latest.get("prop_uti_srag_pct"))
    s, m = stage_from_value(prop_uti, lim_assist.get("prop_uti_srag_pct", {}), True, "proporção UTI em SRAG")
    if _is_valid_number(prop_uti) and float(prop_uti or 0) > 0:
        candidates.append(s)
        motivos.append(m)

    s, m = stage_from_value(
        latest.get("zscore_positividade"),
        lim_assist.get("zscore_positividade", lim_assist.get("zscore", {})),
        True,
        "z-score positividade",
    )
    if _is_valid_number(latest.get("zscore_positividade")):
        candidates.append(s)
        motivos.append(m)

    # Arboviroses (dengue, zika, chikungunya e correlatas)
    cfg_arbo = settings.get("arboviroses", {}) if isinstance(settings, dict) else {}
    if cfg_arbo.get("peso_no_estagio", True):
        s, m = stage_from_value(
            latest.get("zscore_arbovirus"),
            lim_assist.get("zscore_arbovirus", lim_assist.get("zscore", {})),
            True,
            "z-score arboviroses",
        )
        if _is_valid_number(latest.get("zscore_arbovirus")):
            candidates.append(s)
            motivos.append(m)

        s, m = stage_from_value(
            latest.get("casos_arbovirus_7d"),
            lim_assist.get("casos_arbovirus_7d", {}),
            True,
            "casos de arbovirose em 7 dias",
        )
        if _is_valid_number(latest.get("casos_arbovirus_7d")) and float(latest.get("casos_arbovirus_7d") or 0) > 0:
            candidates.append(s)
            motivos.append(m)

        s, m = stage_from_value(
            latest.get("incidencia_arbovirus_100k"),
            lim_assist.get("incidencia_arbovirus_100k", {}),
            True,
            "incidência arbovirose/100 mil",
        )
        if _is_valid_number(latest.get("incidencia_arbovirus_100k")):
            candidates.append(s)
            motivos.append(m)

        alerta_arbo = _to_float(latest.get("alerta_arbovirus"))
        if alerta_arbo is not None and alerta_arbo >= 1:
            z_arbo = _to_float(latest.get("zscore_arbovirus"))
            bump = 1
            if z_arbo is not None and z_arbo >= 2:
                bump = 2
            if z_arbo is not None and z_arbo >= 3:
                bump = 3
            candidates.append(bump)
            dominante = latest.get("agravo_dominante") or "arbovirose"
            motivos.append(f"aumento epidêmico de {dominante} detectado no SINAN")

        if cfg_arbo.get("agravar_se_chuva_e_calor", True):
            tmax = _to_float(latest.get("tmax"))
            precip = _to_float(latest.get("precipitacao_mm") or latest.get("chuva_mm") or latest.get("precipitacao"))
            casos7 = _to_float(latest.get("casos_arbovirus_7d"))
            if (
                tmax is not None
                and casos7 is not None
                and tmax >= 32
                and casos7 >= float(lim_assist.get("casos_arbovirus_7d", {}).get("amarela", 10))
            ):
                candidates.append(2)
                motivos.append("risco combinado calor + transmissão de arboviroses")
            elif precip is not None and casos7 is not None and precip >= 20 and casos7 >= 5:
                candidates.append(2)
                motivos.append("risco combinado chuva + transmissão de arboviroses")

    # --------------------------------------------------------
    # Qualidade do ar
    # --------------------------------------------------------
    aq_score = latest.get("iq_ar_score")

    if cfg_aq.get("peso_no_estagio", True):
        if _is_valid_number(aq_score):
            aq_score_int = max(0, min(4, int(float(aq_score))))
            candidates.append(aq_score_int)
            motivos.append(f"qualidade do ar atingiu {_label(aq_score_int)}")

        if cfg_aq.get("agravar_se_calor_e_ar_ruim", True):
            utci = _to_float(latest.get("utci_proxy"))
            aq = _to_float(aq_score)
            if utci is not None and aq is not None and utci >= 32 and aq >= 2:
                candidates.append(max(2, int(aq)))
                motivos.append("risco combinado calor + qualidade do ar ruim")

    # --------------------------------------------------------
    # Bloco operacional
    # --------------------------------------------------------
    s, m = stage_from_stock_autonomy(
        latest.get("autonomia_min_dias"),
        lim_oper.get("autonomia_insumos_dias", {}),
    )
    candidates.append(s)
    motivos.append(m)

    s, m = stage_from_value(
        latest.get("falhas_infra_pct"),
        lim_oper.get("falhas_infra_pct", {}),
        True,
        "falhas infraestrutura %",
    )
    candidates.append(s)
    motivos.append(m)

    lat = latest.get("latencia_comunicacao_horas")
    if _is_valid_number(lat):
        lat = float(lat)
        limite = lim_oper.get("comunicacao_tempo_max_horas", 2)
        if lat > 6:
            candidates.append(3)
            motivos.append(f"Comunicação atrasada {lat:.1f}h")
        elif lat > limite:
            candidates.append(2)
            motivos.append(f"Comunicação acima da meta {lat:.1f}h")
        else:
            candidates.append(0)
            motivos.append(f"Comunicação dentro da meta {lat:.1f}h")

    # --------------------------------------------------------
    # Bloqueio contra falso verde
    # --------------------------------------------------------
    climate_valid = _valid_any(
        latest,
        [
            "utci_proxy",
            "tmax",
            "risco_cumulativo_3d",
            "onda_calor_p95_2d",
            "severidade_onda_calor",
            "indice_saturacao_solo",
        ],
    )

    assist_valid = _valid_any(
        latest,
        [
            "pressao_calor_pct",
            "ocupacao_leitos_pct",
            "zscore_pressao",
            "zscore_srag",
            "zscore_positividade",
            "zscore_arbovirus",
            "casos_arbovirus_7d",
            "incidencia_arbovirus_100k",
        ],
    )

    aq_valid = _is_valid_number(aq_score)
    operational_valid = _valid_any(
        latest,
        [
            "autonomia_min_dias",
            "falhas_infra_pct",
            "latencia_comunicacao_horas",
        ],
    )

    core_valid = climate_valid or assist_valid
    score = max(candidates) if candidates else 0

    indicadores["climate_valid"] = climate_valid
    indicadores["assist_valid"] = assist_valid
    indicadores["aq_valid"] = aq_valid
    indicadores["operational_valid"] = operational_valid
    indicadores["core_valid"] = core_valid
    indicadores["dados_suficientes_classificacao"] = core_valid

    if not core_valid and score <= 0:
        motivos = [
            "Dados insuficientes para classificação de risco: bloco climático e bloco assistencial indisponíveis",
        ] + motivos

        indicadores["classificacao_bloqueada"] = True
        indicadores["status_classificacao"] = "dados_insuficientes"

        return StageResult(
            nivel="cinza",
            score=0,
            motivos=_clean_motivos(motivos),
            indicadores=indicadores,
        )

    if not core_valid and score > 0:
        motivos = [
            "Classificação parcial: há gatilho operacional/qualidade do ar, mas bloco climático e bloco assistencial estão indisponíveis",
        ] + motivos

        indicadores["classificacao_bloqueada"] = False
        indicadores["status_classificacao"] = "parcial_sem_bloco_essencial"
    else:
        indicadores["classificacao_bloqueada"] = False
        indicadores["status_classificacao"] = "classificacao_com_bloco_essencial"

    return StageResult(
        nivel=_label(score),
        score=int(score),
        motivos=_clean_motivos(motivos),
        indicadores=indicadores,
    )
