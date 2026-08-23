from __future__ import annotations
import numpy as np
import pandas as pd
from sisclima.utils.municipios import ensure_municipality, group_cols


def stock_autonomy(estoque: pd.DataFrame) -> pd.DataFrame:
    if estoque.empty:
        return pd.DataFrame(columns=['data','cod_ibge','municipio','item','estoque_total','consumo_medio_diario','autonomia_dias'])
    df = ensure_municipality(estoque)
    df['data'] = pd.to_datetime(df['data'], errors='coerce').dt.date.astype(str)
    for c in ['estoque_total','consumo_medio_diario']:
        df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
    if 'item' not in df.columns:
        df['item'] = 'insumo_critico'
    df['autonomia_dias'] = np.where(df['consumo_medio_diario'] > 0, df['estoque_total'] / df['consumo_medio_diario'], np.inf)
    return df


def infrastructure_status(infra: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if infra.empty:
        return pd.DataFrame(columns=['data','cod_ibge','municipio','unidade','falha_critica']), pd.DataFrame(columns=['data','cod_ibge','municipio','falhas_infra_pct'])
    df = ensure_municipality(infra)
    df['data'] = pd.to_datetime(df['data'], errors='coerce').dt.date.astype(str)
    for c in ['energia_ok','agua_ok','climatizacao_ok','gerador_ok']:
        if c not in df.columns:
            df[c] = 1
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
    if 'unidade' not in df.columns:
        df['unidade'] = 'NAO_INFORMADA'
    df['falha_critica'] = ((df['energia_ok'] == 0) | (df['agua_ok'] == 0) | (df['climatizacao_ok'] == 0) | (df['gerador_ok'] == 0)).astype(int)
    g = df.groupby(group_cols(df), as_index=False).agg(unidades=('unidade','nunique'), unidades_falha=('falha_critica','sum'))
    g['falhas_infra_pct'] = np.where(g['unidades'] > 0, g['unidades_falha']/g['unidades']*100, 0)
    return df, g


def active_search(busca: pd.DataFrame) -> pd.DataFrame:
    if busca.empty:
        return pd.DataFrame(columns=['data','cod_ibge','municipio','grupo','cadastrados','contatados','cobertura_pct'])
    df = ensure_municipality(busca)
    df['data'] = pd.to_datetime(df['data'], errors='coerce').dt.date.astype(str)
    if 'grupo' not in df.columns:
        df['grupo'] = 'prioritarios'
    for c in ['cadastrados','contatados']:
        df[c] = pd.to_numeric(df.get(c, 0), errors='coerce').fillna(0)
    g = df.groupby(group_cols(df, extras=['grupo']), as_index=False).agg(cadastrados=('cadastrados','sum'), contatados=('contatados','sum'))
    g['cobertura_pct'] = np.where(g['cadastrados'] > 0, g['contatados']/g['cadastrados']*100, 0)
    return g


def communication_latency(com: pd.DataFrame) -> pd.DataFrame:
    if com.empty:
        return pd.DataFrame(columns=['data','cod_ibge','municipio','latencia_horas'])
    df = ensure_municipality(com)
    for c in ['hora_alerta_inmet','hora_boletim_municipal']:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors='coerce')
    if {'hora_alerta_inmet','hora_boletim_municipal'}.issubset(df.columns):
        df['latencia_horas'] = (df['hora_boletim_municipal'] - df['hora_alerta_inmet']).dt.total_seconds()/3600
        df['data'] = df['hora_boletim_municipal'].dt.date.astype(str)
    else:
        df['data'] = pd.Timestamp.now().date().isoformat()
        df['latencia_horas'] = np.nan
    return df
