from __future__ import annotations

import numpy as np
import pandas as pd


def normalize_positive(value, min_v=0, max_v=100):
    try:
        v = float(value)
    except Exception:
        return np.nan
    if max_v == min_v:
        return 0
    return max(0, min(1, (v - min_v) / (max_v - min_v)))


def resilience_index(latest: dict, weights: dict) -> dict:
    """Índice 0-100. Quanto maior, maior resiliência operacional.

    Capacidade de leitos: livres % (ocupação). Se houver `indice_capacidade_cnes`
    ou leitos CNES per capita, mistura 60% livres + 40% capacidade instalada.
    """
    ocup = latest.get('ocupacao_leitos_pct', 100)
    try:
        ocup_f = float(ocup) if ocup is not None else 100.0
    except Exception:
        ocup_f = 100.0
    leitos_livres = 100.0 - ocup_f

    cap_cnes = latest.get('indice_capacidade_cnes')
    try:
        cap_cnes_f = float(cap_cnes) if cap_cnes is not None and str(cap_cnes) not in ('', 'nan', 'None') else np.nan
    except Exception:
        cap_cnes_f = np.nan
    if pd.isna(cap_cnes_f):
        # Fallback leve a partir de leitos/10k (ref operacional 25)
        try:
            l10k = float(latest.get('cnes_leitos_per_10k') or np.nan)
            cap_cnes_f = max(0.0, min(100.0, l10k / 25.0 * 100.0)) if not pd.isna(l10k) else np.nan
        except Exception:
            cap_cnes_f = np.nan

    if not pd.isna(cap_cnes_f):
        capacidade = 0.6 * max(0.0, leitos_livres) + 0.4 * max(0.0, min(100.0, cap_cnes_f))
    else:
        capacidade = max(0.0, leitos_livres)

    estoque = min(100, float(latest.get('autonomia_min_dias', 0) or 0) / 14 * 100)
    infra = 100 - float(latest.get('falhas_infra_pct', 100) or 100)
    busca = float(latest.get('cobertura_busca_pct', 0) or 0)
    lat = float(latest.get('latencia_comunicacao_horas', 99) or 99)
    comunicacao = 100 if lat <= 2 else max(0, 100 - (lat-2)*25)
    comps = {
        'capacidade_leitos': max(0, capacidade),
        'estoque': max(0, estoque),
        'infraestrutura': max(0, infra),
        'busca_ativa': max(0, min(100, busca)),
        'comunicacao': max(0, min(100, comunicacao))
    }
    total_w = sum(weights.values()) or 1
    score = sum(comps[k] * weights.get(k,0) for k in comps) / total_w
    out = {'indice_resiliencia': round(score, 1), **{f'resil_{k}': round(v,1) for k,v in comps.items()}}
    if not pd.isna(cap_cnes_f):
        out['resil_capacidade_cnes_componente'] = round(float(cap_cnes_f), 1)
    return out


# Pesos relativos do índice (só entram colunas presentes). Demografia IBGE primeiro.
_VULN_WEIGHTS = {
    "idosos_pct": 0.34,
    "criancas_0_4_pct": 0.18,
    "criancas_0_9_pct": 0.08,
    "pobreza_pct": 0.16,
    "sem_ar_condicionado_pct": 0.10,
    "rural_pct": 0.10,
    "pop_rua": 0.06,
    "densidade": 0.08,
}


def vulnerability_index(municipios: pd.DataFrame, populacao: pd.DataFrame | None = None) -> pd.DataFrame:
    if municipios.empty:
        return pd.DataFrame()
    df = municipios.copy()
    if "cod_ibge" in df.columns:
        df["cod_ibge"] = df["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
    if populacao is not None and not populacao.empty and "cod_ibge" in df.columns and "cod_ibge" in populacao.columns:
        pop = populacao.copy()
        pop["cod_ibge"] = pop["cod_ibge"].astype(str).str.extract(r"(\d+)")[0].str.zfill(7)
        # evita colunas duplicadas com sufixo _x/_y
        overlap = [c for c in pop.columns if c != "cod_ibge" and c in df.columns]
        pop = pop.drop(columns=overlap, errors="ignore")
        df = df.merge(pop, on="cod_ibge", how="left")

    # Preferir proxy 0–4; se só houver 0–9, não duplicar peso
    numeric_cols = [c for c in _VULN_WEIGHTS if c in df.columns]
    if "criancas_0_4_pct" in numeric_cols and "criancas_0_9_pct" in numeric_cols:
        numeric_cols = [c for c in numeric_cols if c != "criancas_0_9_pct"]
    if not numeric_cols:
        df["indice_vulnerabilidade_calor"] = 50.0
        df["cobertura_vulnerabilidade_pct"] = 0.0
        return df

    weighted = pd.Series(0.0, index=df.index)
    w_sum = 0.0
    covered = pd.Series(0.0, index=df.index)
    for c in numeric_cols:
        vals = pd.to_numeric(df[c], errors="coerce")
        mn, mx = vals.min(skipna=True), vals.max(skipna=True)
        if pd.isna(mn) or pd.isna(mx) or mx == mn:
            norm = pd.Series(0.0, index=df.index)
        else:
            norm = ((vals - mn) / (mx - mn)).clip(0, 1)
        w = float(_VULN_WEIGHTS.get(c, 0.1))
        present = vals.notna().astype(float)
        weighted = weighted + norm.fillna(0.0) * w * present
        covered = covered + present * w
        w_sum += w
    # Renormaliza pelo peso efetivo por município (evita 0 artificial quando falta coluna)
    denom = covered.replace(0, np.nan)
    score = (weighted / denom * 100.0).fillna(50.0)
    df["indice_vulnerabilidade_calor"] = score.round(1)
    df["cobertura_vulnerabilidade_pct"] = (covered / (w_sum or 1.0) * 100.0).round(1)
    return df
