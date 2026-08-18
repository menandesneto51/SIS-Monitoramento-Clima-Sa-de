from __future__ import annotations
import pandas as pd
from sisclima.core.config import APP_CONFIG

ID_COLS = ['cod_ibge', 'municipio']

def ensure_municipality(df: pd.DataFrame, municipio: str | None = None, cod_ibge: int | None = None) -> pd.DataFrame:
    """Garante colunas municipais mínimas sem alterar bases já municipalizadas."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    out = df.copy()
    if 'municipio' not in out.columns:
        out['municipio'] = municipio or APP_CONFIG.municipio
    if 'cod_ibge' not in out.columns:
        out['cod_ibge'] = cod_ibge if cod_ibge is not None else None
    out['municipio'] = out['municipio'].fillna(municipio or APP_CONFIG.municipio).astype(str)
    return out


def municipality_cols(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for c in ['cod_ibge', 'municipio']:
        if c in df.columns:
            cols.append(c)
    return cols


def group_cols(df: pd.DataFrame, date: bool = True, extras: list[str] | None = None) -> list[str]:
    cols = []
    if date:
        cols.append('data')
    cols.extend(municipality_cols(df))
    cols.extend(extras or [])
    # mantém ordem sem duplicar
    seen = set(); ordered = []
    for c in cols:
        if c in df.columns and c not in seen:
            seen.add(c); ordered.append(c)
    return ordered


def latest_by_municipio(df: pd.DataFrame, date_col: str = 'data') -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if date_col in out.columns:
        out[date_col] = pd.to_datetime(out[date_col], errors='coerce')
    gcols = municipality_cols(out)
    if not gcols:
        return out.sort_values(date_col).tail(1) if date_col in out.columns else out.tail(1)
    sort_cols = gcols + ([date_col] if date_col in out.columns else [])
    out = out.sort_values(sort_cols)
    return out.groupby(gcols, dropna=False, as_index=False).tail(1)
