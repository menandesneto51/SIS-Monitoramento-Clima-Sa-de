from __future__ import annotations
from pathlib import Path
import pandas as pd
from sisclima.core.config import APP_CONFIG, SETTINGS, env, resolve_path
from sisclima.utils.io import read_table_safe, normalize_cols, ensure_datetime

ENV_BY_KEY = {
    'meteorologia_csv': 'METEOROLOGIA_CSV',
    'inmet_alertas_csv': 'INMET_ALERTAS_CSV',
    'indicasus_csv': 'INDICASUS_LEITOS_CSV',
    'sivep_csv': 'SIVEP_CSV',
    'lacen_csv': 'LACEN_GAL_CSV',
    'sinan_csv': 'SINAN_AGRAVOS_CSV',
    'sim_csv': 'SIM_OBITOS_CSV',
    'sentinela_csv': 'SENTINELA_EVENTOS_CSV',
    'infraestrutura_csv': 'INFRAESTRUTURA_CSV',
    'estoque_csv': 'ESTOQUE_INSUMOS_CSV',
    'busca_ativa_csv': 'BUSCA_ATIVA_CSV',
    'comunicacao_csv': 'COMUNICACAO_CSV',
    'municipios_csv': 'MUNICIPIOS_CSV',
    'populacao_csv': 'POPULACAO_CSV',
    'qualidade_ar_csv': 'QUALIDADE_AR_CSV',
}

ROOT_FALLBACKS = {
    'municipios_csv': ['municipios_mt.csv', 'Municípios MT lat long.csv', 'Municipios MT lat long.csv'],
    'populacao_csv': ['População Municípios Brasil 2020-2025.xlsx', 'População Municípios Brasil 2020-2025(2).xlsx', 'populacao_municipal_mt_2020_2025.csv'],
}


def csv_path(key: str) -> Path:
    env_key = ENV_BY_KEY.get(key)
    filename = env(env_key) if env_key else None
    if not filename:
        filename = SETTINGS.get('data_sources', {}).get(key)
    if not filename:
        raise KeyError(f'Chave {key} não configurada em settings.yaml')
    candidates = ROOT_FALLBACKS.get(key, [])
    # Caminho normal em data/input + fallback para raiz do projeto.
    p = Path(filename)
    if not p.is_absolute():
        normal = APP_CONFIG.input_dir / filename
        if normal.exists():
            return normal
    return resolve_path(str(filename), candidates=candidates)


def load_csv(key: str, date_cols: list[str] | None = None) -> pd.DataFrame:
    df = read_table_safe(csv_path(key))
    df = normalize_cols(df)
    for col in date_cols or []:
        df = ensure_datetime(df, col)
    # Ajuste específico da planilha de população IBGE 2020-2025.
    if key == 'populacao_csv' and not df.empty:
        if 'ano' in df.columns and 'uf' in df.columns:
            df = df[df['uf'].astype(str).str.upper().eq('MT')].copy()
        if 'cod_ibge' not in df.columns:
            for c in ['codibge_7', 'cod_ibge_7', 'codigo_ibge']:
                if c in df.columns:
                    df = df.rename(columns={c: 'cod_ibge'}); break
        if 'municipio' not in df.columns:
            for c in ['municipio', 'nome_municipio', 'nome']:
                if c in df.columns:
                    df = df.rename(columns={c: 'municipio'}); break
        if 'populacao' in df.columns and 'ano' in df.columns:
            # Mantém série histórica, mas cria populacao_2025 para o motor de vulnerabilidade quando possível.
            try:
                latest = df.sort_values('ano').groupby('cod_ibge', as_index=False).tail(1)[['cod_ibge','populacao']].rename(columns={'populacao':'populacao_2025'})
                df = df.merge(latest, on='cod_ibge', how='left')
            except Exception:
                pass
    return df


def load_all_inputs() -> dict[str, pd.DataFrame]:
    return {
        'meteorologia': load_csv('meteorologia_csv', ['data']),
        'inmet_alertas': load_csv('inmet_alertas_csv', ['data_emissao']),
        'indicasus_leitos': load_csv('indicasus_csv', ['data']),
        'sivep_srag': load_csv('sivep_csv', ['data_notificacao','data_sintomas']),
        'lacen_gal': load_csv('lacen_csv', ['data_coleta','data_resultado']),
        'sinan_agravos': load_csv('sinan_csv', ['data_notificacao']),
        'sim_obitos': load_csv('sim_csv', ['data_obito']),
        'sentinela_rumores': load_csv('sentinela_csv', ['data_captura']),
        'infraestrutura': load_csv('infraestrutura_csv', ['data']),
        'estoque': load_csv('estoque_csv', ['data']),
        'busca_ativa': load_csv('busca_ativa_csv', ['data']),
        'comunicacao': load_csv('comunicacao_csv', []),
        'municipios': load_csv('municipios_csv'),
        'populacao': load_csv('populacao_csv'),
        'qualidade_ar': load_csv('qualidade_ar_csv', ['data'])
    }
