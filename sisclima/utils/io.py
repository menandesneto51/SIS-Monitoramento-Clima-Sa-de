from __future__ import annotations
from pathlib import Path
import unicodedata
import pandas as pd


def read_table_safe(path: Path, parse_dates=None) -> pd.DataFrame:
    """Lê CSV, XLSX, Parquet ou DBF; retorna DataFrame vazio se não existir."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    suffix = path.suffix.lower()
    try:
        if suffix in {'.xlsx', '.xls'}:
            # Primeiro sheet por padrão; para a base populacional do IBGE geralmente é Base_Dados_Pop_BR.
            try:
                return pd.read_excel(path, sheet_name='Base_Dados_Pop_BR', parse_dates=parse_dates)
            except Exception:
                return pd.read_excel(path, sheet_name=0, parse_dates=parse_dates)
        if suffix == '.parquet':
            return pd.read_parquet(path)
        if suffix == '.dbf':
            try:
                from dbfread import DBF
                return pd.DataFrame(iter(DBF(str(path), encoding='latin1')))
            except Exception:
                try:
                    import geopandas as gpd
                    return pd.DataFrame(gpd.read_file(path))
                except Exception:
                    return pd.DataFrame()
        try:
            return pd.read_csv(path, sep=None, engine='python', encoding='utf-8', parse_dates=parse_dates)
        except UnicodeDecodeError:
            return pd.read_csv(path, sep=None, engine='python', encoding='latin1', parse_dates=parse_dates)
    except Exception:
        return pd.DataFrame()


def read_csv_safe(path: Path, parse_dates=None) -> pd.DataFrame:
    return read_table_safe(path, parse_dates=parse_dates)


def _ascii_col(value: str) -> str:
    text = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode('ascii')
    return text.strip().lower().replace(' ', '_').replace('-', '_').replace('.', '').replace('/', '_')


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [_ascii_col(c) for c in df.columns]
    aliases = {
        'codibge_7': 'cod_ibge',
        'cod_ibge_7': 'cod_ibge',
        'codigo_ibge': 'cod_ibge',
        'codigo_municipio': 'cod_ibge',
        'cd_mun': 'cod_ibge',
        'cd_geocmu': 'cod_ibge',
        'geocodigo': 'cod_ibge',
        'municipio_residencia': 'municipio',
        'nm_mun': 'municipio',
        'nm_municip': 'municipio',
        'nome_municipio': 'municipio',
        'nome': 'municipio',
        'populacao': 'populacao',
        'populacao_2025': 'populacao_2025',
    }
    df = df.rename(columns={c: aliases.get(c, c) for c in df.columns})
    return df


def ensure_datetime(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    return df
