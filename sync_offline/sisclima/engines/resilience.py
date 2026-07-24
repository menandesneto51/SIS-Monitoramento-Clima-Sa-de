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

    Capacidade de leitos: prioriza ocupação IndicaSUS (livres%).
    Infraestrutura: prioriza índice CNES (capacidade instalada); senão CSV de falhas.
    """
    ocup = latest.get('ocupacao_leitos_pct', None)
    try:
        ocup_f = float(ocup) if ocup is not None and str(ocup) not in {'', 'nan', 'None'} else float('nan')
    except Exception:
        ocup_f = float('nan')
    if ocup_f == ocup_f:  # not NaN
        leitos_livres = max(0.0, 100.0 - ocup_f)
    else:
        # Sem ocupação real: usa capacidade CNES como proxy de folga operacional.
        try:
            leitos_livres = float(latest.get('indice_capacidade_cnes', 50) or 50)
        except Exception:
            leitos_livres = 50.0

    estoque = min(100, float(latest.get('autonomia_min_dias', 0) or 0) / 14 * 100)

    falhas = latest.get('falhas_infra_pct', None)
    try:
        falhas_f = float(falhas) if falhas is not None and str(falhas) not in {'', 'nan', 'None'} else float('nan')
    except Exception:
        falhas_f = float('nan')
    if falhas_f == falhas_f:
        infra = max(0.0, 100.0 - falhas_f)
    else:
        try:
            infra = float(latest.get('indice_capacidade_cnes', 50) or 50)
        except Exception:
            infra = 50.0

    busca = float(latest.get('cobertura_busca_pct', 0) or 0)
    lat = float(latest.get('latencia_comunicacao_horas', 99) or 99)
    comunicacao = 100 if lat <= 2 else max(0, 100 - (lat - 2) * 25)
    comps = {
        'capacidade_leitos': max(0, leitos_livres),
        'estoque': max(0, estoque),
        'infraestrutura': max(0, min(100, infra)),
        'busca_ativa': max(0, min(100, busca)),
        'comunicacao': max(0, min(100, comunicacao)),
    }
    total_w = sum(weights.values()) or 1
    score = sum(comps[k] * weights.get(k, 0) for k in comps) / total_w
    return {'indice_resiliencia': round(score, 1), **{f'resil_{k}': round(v, 1) for k, v in comps.items()}}


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
