from __future__ import annotations
from pathlib import Path
import sqlite3
import pandas as pd
from sisclima.core.config import ROOT, env, as_bool
from sisclima.utils.io import normalize_cols, ensure_datetime
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DATE_CANDIDATES = ['data_sintomas','dt_sin_pri','data_primeiros_sintomas','data_notificacao','dt_notific','data']
IBGE_CANDIDATES = ['cod_ibge','cod_ibge_residencia','co_mun_res','id_mn_resi','municipio_ibge']
MUN_CANDIDATES = ['municipio','municipio_residencia','nm_mun_res','id_municip','mun_res']


def _root_path(value: str | None, default: str) -> Path:
    p = Path(value or default)
    return p if p.is_absolute() else ROOT / p


def _read_one_file(path: Path) -> pd.DataFrame:
    suf = path.suffix.lower()
    if suf == '.csv':
        for enc in ['utf-8-sig','latin1','cp1252']:
            try:
                return pd.read_csv(path, sep=None, engine='python', encoding=enc)
            except Exception:
                continue
        return pd.DataFrame()
    if suf == '.parquet':
        return pd.read_parquet(path)
    if suf in ['.xlsx', '.xls']:
        return pd.read_excel(path)
    if suf == '.dbf':
        try:
            from dbfread import DBF
            return pd.DataFrame(iter(DBF(path, encoding='latin1')))
        except Exception as e:
            log.warning('Não foi possível ler DBF %s: %s', path, e)
            return pd.DataFrame()
    return pd.DataFrame()


def normalize_sivep_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_cols(df)
    rename = {}
    for c in DATE_CANDIDATES:
        if c in df.columns:
            rename[c] = 'data_sintomas'; break
    for c in IBGE_CANDIDATES:
        if c in df.columns:
            rename[c] = 'cod_ibge'; break
    for c in MUN_CANDIDATES:
        if c in df.columns:
            rename[c] = 'municipio'; break
    for a,b in [('data_notificacao','data_notificacao'),('dt_notific','data_notificacao'),('evolucao','evolucao'),('uti','uti'),('suporte_ventilatorio','suporte_ventilatorio'),('classificacao_final','classificacao_final')]:
        if a in df.columns and b not in rename.values():
            rename[a]=b
    df = df.rename(columns=rename)
    if 'cod_ibge' in df.columns:
        df['cod_ibge'] = df['cod_ibge'].astype(str).str.extract(r'(\d+)')[0].str[:7]
    for col in ['data_sintomas','data_notificacao']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def rebuild_sivep_local_db() -> dict:
    folder = _root_path(env('SIVEP_UPDATE_FOLDER'), 'data/input/sivep_atualizacao')
    db_path = _root_path(env('SIVEP_LOCAL_DB_PATH'), 'data/local/sivep/sivep_srag_local.db')
    table = env('SIVEP_LOCAL_TABLE', 'sivep_srag') or 'sivep_srag'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    patterns = [p.strip() for p in (env('SIVEP_FILE_PATTERN', '*.csv;*.parquet;*.xlsx;*.dbf') or '').split(';') if p.strip()]
    files = []
    for pat in patterns:
        files.extend(sorted(folder.glob(pat)))
    frames = []
    for f in files:
        df = _read_one_file(f)
        if df is not None and not df.empty:
            df = normalize_sivep_columns(df)
            df['arquivo_origem'] = f.name
            frames.append(df)
    if frames:
        out = pd.concat(frames, ignore_index=True, sort=False)
        # deduplicação conservadora
        subset = [c for c in ['data_sintomas','cod_ibge','municipio','idade','sexo','arquivo_origem'] if c in out.columns]
        if subset:
            out = out.drop_duplicates(subset=subset)
    else:
        out = pd.DataFrame(columns=['data_sintomas','cod_ibge','municipio','casos_srag','obitos_srag','internacoes_uti'])
    with sqlite3.connect(db_path) as conn:
        out.to_sql(table, conn, if_exists='replace', index=False)
        conn.execute('CREATE INDEX IF NOT EXISTS idx_sivep_mun_data ON sivep_srag (cod_ibge, data_sintomas)')
    return {'db_path': str(db_path), 'table': table, 'files': len(files), 'rows': len(out)}


def load_sivep_local() -> pd.DataFrame:
    if not as_bool(env('USE_SIVEP_LOCAL', 'true')):
        return pd.DataFrame()
    db_path = _root_path(env('SIVEP_LOCAL_DB_PATH'), 'data/local/sivep/sivep_srag_local.db')
    table = env('SIVEP_LOCAL_TABLE', 'sivep_srag') or 'sivep_srag'
    if not db_path.exists() or as_bool(env('SIVEP_REBUILD_ON_UPDATE', 'false')):
        try:
            rebuild_sivep_local_db()
        except Exception as e:
            log.warning('Falha ao atualizar banco local SIVEP: %s', e)
    if not db_path.exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            df = pd.read_sql(f'SELECT * FROM {table}', conn)
        return normalize_sivep_columns(df)
    except Exception as e:
        log.warning('Falha ao ler banco local SIVEP: %s', e)
        return pd.DataFrame()
