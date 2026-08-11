# -*- coding: utf-8 -*-
"""
Indicadores compostos para o painel ARARAS (leitura leiga + priorização).

Pesos e faixas: config/settings.yaml → indicadores_painel
Override opcional via env PANEL_W_* (ex.: PANEL_W_TENSAO_RISCO=0.40).

Persistidos em resumo_municipal_atual e indicadores_painel_municipal.
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.config import SETTINGS

LEVEL_RANK = {
    "cinza": -1,
    "verde": 0,
    "amarela": 1,
    "laranja": 2,
    "vermelha": 3,
    "roxa": 4,
}

KEY_FIELDS = [
    "tmax",
    "utci_proxy",
    "risco_cumulativo_3d",
    "umidade_media",
    "casos_srag",
    "casos_arbovirus_7d",
    "pm25_ugm3",
    "pressao_calor_pct",
    "ocupacao_leitos_pct",
    "populacao",
]

PANEL_INDICATOR_COLS = [
    "indice_tensao_climatica",
    "indice_carga_saude",
    "indice_vigilancia_bruta",
    "indice_vigilancia_integrada",
    "indice_adaptacao_climatica",
    "faixa_tensao_climatica",
    "faixa_vigilancia",
    "percentil_risco_estadual",
    "completude_dados_pct",
    "tendencia_7d",
    "orientacao_leiga",
    "orientacao_adaptasus",
    "risco_adaptasus_dominante",
    "risco_calor_vulneravel",
    "risco_ar_queimadas",
    "risco_vetorial_climatico",
    "pressao_rede_climatica",
    "pop_vulneravel_estimada",
    "pop_vulneravel_exposta",
    "indice_exposicao_vulneravel",
    "flag_vulneravel_exposto",
    "score_inteligencia",
    "delta_vigilancia_vs_vermelha_media",
]

# Defaults espelhados de settings.yaml
_DEFAULTS = {
    "tensao_climatica": {
        "risco_cumulativo": 0.50,
        "utci": 0.28,
        "tmax": 0.16,
        "umidade_seca": 0.06,
    },
    "carga_saude": {
        "srag": 0.34,
        "arbovirus": 0.18,
        "pm25": 0.10,
        "queimadas": 0.08,
        "pressao": 0.30,
    },
    "vigilancia_integrada": {
        # bruta = tensão+carga+pressão; depois alinha com nível operacional
        "tensao": 0.42,
        "carga": 0.28,
        "pressao": 0.12,
        "nivel_operacional": 0.18,
    },
    "faixas": {
        "baixa_max": 30,
        "moderada_max": 60,
        "alta_max": 80,
    },
    # piso mínimo por nível (0–100) para garantir Roxa ≥ Vermelha na média operacional
    "pisos_nivel": {
        "verde": 0,
        "amarela": 12,
        "laranja": 24,
        "vermelha": 38,
        "roxa": 48,
        "cinza": 0,
    },
}

# Mapa env → (grupo, chave)
_ENV_WEIGHT_MAP = {
    "PANEL_W_TENSAO_RISCO": ("tensao_climatica", "risco_cumulativo"),
    "PANEL_W_TENSAO_UTCI": ("tensao_climatica", "utci"),
    "PANEL_W_TENSAO_TMAX": ("tensao_climatica", "tmax"),
    "PANEL_W_TENSAO_UMIDADE": ("tensao_climatica", "umidade_seca"),
    "PANEL_W_CARGA_SRAG": ("carga_saude", "srag"),
    "PANEL_W_CARGA_ARBO": ("carga_saude", "arbovirus"),
    "PANEL_W_CARGA_PM25": ("carga_saude", "pm25"),
    "PANEL_W_CARGA_PRESSAO": ("carga_saude", "pressao"),
    "PANEL_W_VIG_TENSAO": ("vigilancia_integrada", "tensao"),
    "PANEL_W_VIG_CARGA": ("vigilancia_integrada", "carga"),
    "PANEL_W_VIG_PRESSAO": ("vigilancia_integrada", "pressao"),
    "PANEL_W_VIG_NIVEL": ("vigilancia_integrada", "nivel_operacional"),
}


def get_indicator_config() -> dict[str, Any]:
    """Mescla defaults + settings.yaml + overrides de ambiente."""
    raw = SETTINGS.get("indicadores_painel") or {}
    cfg: dict[str, Any] = {
        "tensao_climatica": {**_DEFAULTS["tensao_climatica"], **(raw.get("tensao_climatica") or {})},
        "carga_saude": {**_DEFAULTS["carga_saude"], **(raw.get("carga_saude") or {})},
        "vigilancia_integrada": {**_DEFAULTS["vigilancia_integrada"], **(raw.get("vigilancia_integrada") or {})},
        "faixas": {**_DEFAULTS["faixas"], **(raw.get("faixas") or {})},
        "pisos_nivel": {**_DEFAULTS["pisos_nivel"], **(raw.get("pisos_nivel") or {})},
        "aplicar_piso_nivel": bool(raw.get("aplicar_piso_nivel", True)),
        "notas_calibracao": str(raw.get("notas_calibracao") or "").strip(),
    }
    for env_key, (group, key) in _ENV_WEIGHT_MAP.items():
        val = os.getenv(env_key)
        if val is None or str(val).strip() == "":
            continue
        try:
            cfg[group][key] = float(val)
        except ValueError:
            continue
    return cfg


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _clip01(s: pd.Series) -> pd.Series:
    return _num(s).clip(lower=0, upper=1).fillna(0)


def _scale_0_100(parts: list[pd.Series], weights: list[float]) -> pd.Series:
    w = np.array(weights, dtype=float)
    w = w / w.sum() if w.sum() else w
    acc = np.zeros(len(parts[0]))
    for series, wi in zip(parts, w):
        acc = acc + series.to_numpy(dtype=float) * wi
    return pd.Series(np.clip(acc * 100.0, 0, 100), index=parts[0].index)


def _tendencia_label(atual: str, pred: str) -> str:
    a = LEVEL_RANK.get(str(atual).lower(), 0)
    p = LEVEL_RANK.get(str(pred).lower(), a)
    if p > a:
        return "subindo"
    if p < a:
        return "descendo"
    return "estável"


def _faixa_fn(faixas: dict) -> callable:
    baixa = float(faixas.get("baixa_max", 30))
    mod = float(faixas.get("moderada_max", 60))
    alta = float(faixas.get("alta_max", 80))

    def _faixa(v: float) -> str:
        if pd.isna(v):
            return "—"
        if v <= baixa:
            return "baixa"
        if v <= mod:
            return "moderada"
        if v <= alta:
            return "alta"
        return "muito alta"

    return _faixa


def _orientacao_leiga(row: pd.Series) -> str:
    nivel = str(row.get("nivel", "cinza")).lower()
    tensao = row.get("indice_tensao_climatica", np.nan)
    carga = row.get("indice_carga_saude", np.nan)
    tend = str(row.get("tendencia_7d", "estável"))
    bits = []
    if nivel in {"vermelha", "roxa"}:
        bits.append("Prioridade alta nesta rodada.")
    elif nivel == "laranja":
        bits.append("Manter sob observação reforçada.")
    elif nivel == "amarela":
        bits.append("Atenção preventiva.")
    else:
        bits.append("Situação habitual — monitorar.")
    try:
        if pd.notna(tensao) and float(tensao) >= 70:
            bits.append("Calor intenso/acumulado.")
    except Exception:
        pass
    try:
        focos = row.get("focos_queimadas_7d", np.nan)
        if pd.notna(focos) and float(focos) >= 20:
            bits.append("Focos de queimadas elevados (INPE).")
    except Exception:
        pass
    try:
        if pd.notna(row.get("onda_fria_2d")) and int(float(row.get("onda_fria_2d") or 0)) >= 1:
            bits.append("Onda de frio em curso (Tmín).")
    except Exception:
        pass
    try:
        if pd.notna(carga) and float(carga) >= 60:
            bits.append("Sinais sanitários elevados.")
    except Exception:
        pass
    if tend == "subindo":
        bits.append("Tendência de piora em ~7 dias.")
    elif tend == "descendo":
        bits.append("Tendência de melhora em ~7 dias.")
    return " ".join(bits)


def enrich_panel_indicators(resumo: pd.DataFrame, pred: pd.DataFrame | None = None) -> pd.DataFrame:
    """Acrescenta indicadores compostos e textos leigos ao resumo municipal."""
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()

    cfg = get_indicator_config()
    w_t = cfg["tensao_climatica"]
    w_c = cfg["carga_saude"]
    w_v = cfg["vigilancia_integrada"]
    faixa = _faixa_fn(cfg["faixas"])

    df = resumo.copy()
    n = len(df)

    risco = _clip01(_num(df["risco_cumulativo_3d"]) / 15.0) if "risco_cumulativo_3d" in df.columns else pd.Series(0.0, index=df.index)
    utci = _clip01((_num(df["utci_proxy"]) - 26.0) / 16.0) if "utci_proxy" in df.columns else pd.Series(0.0, index=df.index)
    tmax = _clip01((_num(df["tmax"]) - 30.0) / 12.0) if "tmax" in df.columns else pd.Series(0.0, index=df.index)
    umid_seca = (
        _clip01((55.0 - _num(df["umidade_media"])) / 40.0)
        if "umidade_media" in df.columns
        else pd.Series(0.0, index=df.index)
    )
    df["indice_tensao_climatica"] = _scale_0_100(
        [risco, utci, tmax, umid_seca],
        [float(w_t["risco_cumulativo"]), float(w_t["utci"]), float(w_t["tmax"]), float(w_t["umidade_seca"])],
    ).round(1)

    srag = (
        _clip01(_num(df["incidencia_srag_100k"]) / 40.0)
        if "incidencia_srag_100k" in df.columns
        else (
            _clip01(_num(df["casos_srag"]) / 40.0)
            if "casos_srag" in df.columns
            else pd.Series(0.0, index=df.index)
        )
    )
    arbo = (
        _clip01(_num(df["casos_arbovirus_7d"]) / 30.0)
        if "casos_arbovirus_7d" in df.columns
        else pd.Series(0.0, index=df.index)
    )
    pm = _clip01(_num(df["pm25_ugm3"]) / 75.0) if "pm25_ugm3" in df.columns else pd.Series(0.0, index=df.index)
    focos = (
        _clip01(_num(df["focos_queimadas_7d"]) / 80.0)
        if "focos_queimadas_7d" in df.columns
        else pd.Series(0.0, index=df.index)
    )
    press = (
        _clip01(_num(df["pressao_calor_pct"]) / 12.0)
        if "pressao_calor_pct" in df.columns
        else pd.Series(0.0, index=df.index)
    )
    df["indice_carga_saude"] = _scale_0_100(
        [srag, arbo, pm, focos, press],
        [
            float(w_c["srag"]),
            float(w_c["arbovirus"]),
            float(w_c["pm25"]),
            float(w_c.get("queimadas", 0.08)),
            float(w_c["pressao"]),
        ],
    ).round(1)

    # Vigilância bruta = só clima+saúde (sem nível oficial)
    df["indice_vigilancia_bruta"] = _scale_0_100(
        [
            df["indice_tensao_climatica"] / 100.0,
            df["indice_carga_saude"] / 100.0,
            press,
        ],
        [
            float(w_v.get("tensao", 0.42)),
            float(w_v.get("carga", 0.28)),
            float(w_v.get("pressao", 0.12)),
        ],
    ).round(1)

    # Componente do nível operacional (score 0–4 → 0–1)
    if "score" in df.columns:
        nivel_comp = (_num(df["score"]).fillna(0).clip(0, 4) / 4.0)
    elif "nivel" in df.columns:
        nivel_comp = df["nivel"].astype(str).str.lower().map(LEVEL_RANK).fillna(0).clip(0, 4) / 4.0
    else:
        nivel_comp = pd.Series(0.0, index=df.index)

    w_nivel = float(w_v.get("nivel_operacional", 0.18))
    # Renormaliza: bruta usa tensao+carga+pressao; integrada inclui nível
    w_bruta = float(w_v.get("tensao", 0.42)) + float(w_v.get("carga", 0.28)) + float(w_v.get("pressao", 0.12))
    if w_bruta + w_nivel <= 0:
        w_bruta, w_nivel = 0.82, 0.18
    df["indice_vigilancia_integrada"] = (
        (df["indice_vigilancia_bruta"] * (w_bruta / (w_bruta + w_nivel)))
        + (nivel_comp * 100.0 * (w_nivel / (w_bruta + w_nivel)))
    ).clip(0, 100).round(1)

    # Piso por nível oficial: garante que Roxa não fique sistematicamente abaixo de Vermelha
    if cfg.get("aplicar_piso_nivel", True) and "nivel" in df.columns:
        pisos = cfg.get("pisos_nivel") or {}
        piso_series = df["nivel"].astype(str).str.lower().map(
            {k: float(v) for k, v in pisos.items()}
        ).fillna(0)
        df["indice_vigilancia_integrada"] = pd.Series(
            np.maximum(
                df["indice_vigilancia_integrada"].to_numpy(dtype=float),
                piso_series.to_numpy(dtype=float),
            ),
            index=df.index,
        ).clip(0, 100).round(1)

    df["faixa_tensao_climatica"] = df["indice_tensao_climatica"].apply(faixa)
    df["faixa_vigilancia"] = df["indice_vigilancia_integrada"].apply(faixa)

    if "risco_cumulativo_3d" in df.columns:
        r = _num(df["risco_cumulativo_3d"])
        df["percentil_risco_estadual"] = (r.rank(pct=True, method="average") * 100).round(0)
    else:
        df["percentil_risco_estadual"] = np.nan

    present = [c for c in KEY_FIELDS if c in df.columns]
    if present:
        filled = pd.concat([df[c].notna().astype(float) for c in present], axis=1)
        df["completude_dados_pct"] = (filled.mean(axis=1) * 100).round(0)
    else:
        df["completude_dados_pct"] = 0.0

    pred_map = {}
    if pred is not None and not pred.empty and "cod_ibge" in pred.columns and "nivel_predicao_7d" in pred.columns:
        p = pred.copy()
        p["cod_ibge"] = p["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        pred_map = dict(zip(p["cod_ibge"], p["nivel_predicao_7d"].astype(str).str.lower()))

    if "cod_ibge" in df.columns:
        ibge = df["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False)
        if "nivel_predicao_7d" in df.columns:
            pred_series = df["nivel_predicao_7d"].astype(str).str.lower()
        else:
            pred_series = ibge.map(pred_map)
        df["tendencia_7d"] = [
            _tendencia_label(a, b) if pd.notna(b) and str(b) not in {"nan", "none", ""} else "—"
            for a, b in zip(df.get("nivel", pd.Series(["cinza"] * n)), pred_series)
        ]
    else:
        df["tendencia_7d"] = "—"

    df["orientacao_leiga"] = df.apply(_orientacao_leiga, axis=1)
    df["score_inteligencia"] = (
        (df["indice_vigilancia_integrada"] / 25.0).clip(0, 4).round(0).astype("Int64")
    )

    # Diagnóstico: quanto a vigilância de cada mun. está vs média dos vermelhos
    verm = df["nivel"].astype(str).str.lower().eq("vermelha") if "nivel" in df.columns else pd.Series(False, index=df.index)
    if verm.any():
        media_verm = float(_num(df.loc[verm, "indice_vigilancia_integrada"]).mean())
        df["delta_vigilancia_vs_vermelha_media"] = (
            _num(df["indice_vigilancia_integrada"]) - media_verm
        ).round(1)
    else:
        df["delta_vigilancia_vs_vermelha_media"] = np.nan

    return df


def panel_indicators_snapshot(resumo: pd.DataFrame) -> pd.DataFrame:
    """Tabela enxuta para persistência dedicada."""
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    keep = ["cod_ibge", "municipio", "regional_saude", "nivel", "score"] + [
        c for c in PANEL_INDICATOR_COLS if c in resumo.columns
    ]
    out = resumo[[c for c in keep if c in resumo.columns]].copy()
    out["gerado_em"] = pd.Timestamp.now().isoformat(timespec="seconds")
    cfg = get_indicator_config()
    out["pesos_versao"] = "settings.yaml:indicadores_painel"
    out["nota_calibracao"] = cfg.get("notas_calibracao") or ""
    return out


def state_indicator_summary(resumo: pd.DataFrame) -> dict:
    """KPIs estaduais dos novos indicadores."""
    if resumo is None or resumo.empty:
        return {}
    out: dict = {"municipios": int(resumo["cod_ibge"].nunique()) if "cod_ibge" in resumo.columns else len(resumo)}
    for c in [
        "indice_tensao_climatica",
        "indice_carga_saude",
        "indice_vigilancia_integrada",
        "completude_dados_pct",
        "percentil_risco_estadual",
    ]:
        if c in resumo.columns:
            s = _num(resumo[c])
            out[f"{c}_media"] = float(s.mean()) if s.notna().any() else None
            out[f"{c}_max"] = float(s.max()) if s.notna().any() else None
    if "tendencia_7d" in resumo.columns:
        vc = resumo["tendencia_7d"].astype(str).value_counts().to_dict()
        out["tendencia_subindo"] = int(vc.get("subindo", 0))
        out["tendencia_estavel"] = int(vc.get("estável", 0))
        out["tendencia_descendo"] = int(vc.get("descendo", 0))
    if "faixa_vigilancia" in resumo.columns:
        out["vigilancia_alta_ou_mais"] = int(
            resumo["faixa_vigilancia"].isin(["alta", "muito alta"]).sum()
        )
        out["vigilancia_moderada_ou_mais"] = int(
            resumo["faixa_vigilancia"].isin(["moderada", "alta", "muito alta"]).sum()
        )
    return out
