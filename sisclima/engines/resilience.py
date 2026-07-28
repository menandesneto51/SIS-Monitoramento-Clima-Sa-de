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


def vulnerability_index(municipios: pd.DataFrame, populacao: pd.DataFrame | None = None) -> pd.DataFrame:
    if municipios.empty:
        return pd.DataFrame()
    df = municipios.copy()
    if populacao is not None and not populacao.empty and 'cod_ibge' in df.columns and 'cod_ibge' in populacao.columns:
        df['cod_ibge'] = df['cod_ibge'].astype(str).str.extract(r'(\d+)')[0].str.zfill(7)
        pop = populacao.copy()
        pop['cod_ibge'] = pop['cod_ibge'].astype(str).str.extract(r'(\d+)')[0].str.zfill(7)
        df = df.merge(pop, on='cod_ibge', how='left')
    numeric_cols = [c for c in ['idosos_pct','pobreza_pct','sem_ar_condicionado_pct','rural_pct','pop_rua','densidade'] if c in df.columns]
    if not numeric_cols:
        df['indice_vulnerabilidade_calor'] = 50
        return df
    score = 0
    for c in numeric_cols:
        vals = pd.to_numeric(df[c], errors='coerce')
        mn, mx = vals.min(), vals.max()
        norm = (vals - mn) / (mx - mn) if mx != mn else pd.Series(0, index=df.index)
        score = score + norm.fillna(0)
    df['indice_vulnerabilidade_calor'] = (score / len(numeric_cols) * 100).round(1)
    return df
