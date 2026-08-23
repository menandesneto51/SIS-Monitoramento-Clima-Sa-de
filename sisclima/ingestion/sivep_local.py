from __future__ import annotations
from pathlib import Path
import sqlite3
import pandas as pd
from sisclima.core.config import ROOT, env, as_bool
from sisclima.core.db import is_postgres, read_table, write_df
from sisclima.utils.io import normalize_cols
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

DATE_CANDIDATES = ['data_sintomas','dt_sin_pri','data_primeiros_sintomas','data_notificacao','dt_notific','data']
IBGE_CANDIDATES = ['cod_ibge','cod_ibge_residencia','co_mun_res','id_mn_resi','municipio_ibge']
MUN_CANDIDATES = ['municipio','municipio_residencia','nm_mun_res','id_municip','mun_res']


def _root_path(value: str | None, default: str) -> Path:
    p = Path(value or default)
    return p if p.is_absolute() else ROOT / p


def _use_unified_db() -> bool:
    if as_bool(env('SIVEP_USE_UNIFIED_DB', 'false')):
        return True
    return is_postgres()


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
    for a, b in [
        ("data_notificacao", "data_notificacao"),
        ("dt_notific", "data_notificacao"),
        ("evolucao", "evolucao"),
        ("uti", "uti"),
        ("suporte_ventilatorio", "suporte_ventilatorio"),
        ("suport_ven", "suporte_ventilatorio"),
        ("classificacao_final", "classificacao_final"),
        ("classi_fin", "classificacao_final"),
        ("virus", "virus"),
        ("etiologia", "virus"),
        ("obito", "obito"),
        ("idade", "idade"),
        ("cs_sexo", "sexo"),
        ("sexo", "sexo"),
    ]:
        if a in df.columns and b not in df.columns and b not in rename.values():
            rename[a] = b
        elif a in df.columns and b not in rename and a != b:
            rename.setdefault(a, b)
    df = df.rename(columns=rename)
    if 'cod_ibge' in df.columns:
        df['cod_ibge'] = df['cod_ibge'].astype(str).str.extract(r'(\d+)')[0].str[:7]
    for col in ['data_sintomas','data_notificacao']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def _keep_existing_sivep(table: str, db_path: Path) -> dict | None:
    """Não apaga SRAG já carregado quando a pasta de atualização está vazia."""
    if _use_unified_db():
        existing = read_table(table)
        if existing is not None and not existing.empty:
            log.warning(
                "SIVEP: sem arquivo novo em sivep_atualizacao; mantidos %s registros",
                len(existing),
            )
            return {"db": "unified", "table": table, "files": 0, "rows": int(len(existing)), "status": "kept"}
        return None
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(db_path) as conn:
            n = int(pd.read_sql(f"SELECT COUNT(*) AS n FROM {table}", conn)["n"].iloc[0])
        if n > 0:
            log.warning("SIVEP: sem arquivo novo em sivep_atualizacao; mantidos %s registros", n)
            return {"db_path": str(db_path), "table": table, "files": 0, "rows": n, "status": "kept"}
    except Exception:
        return None
    return None


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
    input_csv = _root_path(None, 'data/input') / (env('SIVEP_CSV') or 'sivep_srag.csv')
    if input_csv.exists() and input_csv not in files:
        files.append(input_csv)
    files = [f for f in files if f.is_file() and f.name != '.gitkeep']
    frames = []
    for f in files:
        df = _read_one_file(f)
        if df is not None and not df.empty:
            df = normalize_sivep_columns(df)
            df['arquivo_origem'] = f.name
            frames.append(df)
    if frames:
        out = pd.concat(frames, ignore_index=True, sort=False)
        subset = [c for c in ['data_sintomas','cod_ibge','municipio','idade','sexo','arquivo_origem'] if c in out.columns]
        if subset:
            out = out.drop_duplicates(subset=subset)
    else:
        kept = _keep_existing_sivep(table, db_path)
        if kept is not None:
            return kept
        out = pd.DataFrame(columns=['data_sintomas','cod_ibge','municipio','casos_srag','obitos_srag','internacoes_uti'])

    if _use_unified_db():
        write_df(out, table, if_exists='replace')
        return {'db': 'unified', 'table': table, 'files': len(files), 'rows': len(out)}

    with sqlite3.connect(db_path) as conn:
        out.to_sql(table, conn, if_exists='replace', index=False)
        try:
            conn.execute('CREATE INDEX IF NOT EXISTS idx_sivep_mun_data ON sivep_srag (cod_ibge, data_sintomas)')
        except Exception:
            pass
    return {'db_path': str(db_path), 'table': table, 'files': len(files), 'rows': len(out)}


def load_sivep_local() -> pd.DataFrame:
    if not as_bool(env('USE_SIVEP_LOCAL', 'true')):
        return pd.DataFrame()
    table = env('SIVEP_LOCAL_TABLE', 'sivep_srag') or 'sivep_srag'

    if _use_unified_db():
        if as_bool(env('SIVEP_REBUILD_ON_UPDATE', 'false')):
            try:
                rebuild_sivep_local_db()
            except Exception as e:
                log.warning('Falha ao atualizar SIVEP na base única: %s', e)
        df = read_table(table)
        if df.empty and as_bool(env('SIVEP_REBUILD_ON_UPDATE', 'true')):
            try:
                rebuild_sivep_local_db()
                df = read_table(table)
            except Exception as e:
                log.warning('Falha ao popular SIVEP na base única: %s', e)
        return normalize_sivep_columns(df) if not df.empty else df

    db_path = _root_path(env('SIVEP_LOCAL_DB_PATH'), 'data/local/sivep/sivep_srag_local.db')
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
