from __future__ import annotations
import pandas as pd
from sisclima.ingestion.sqlserver import read_sqlserver, use_dw_source, use_sqlserver
from sisclima.core.config import ROOT
from sisclima.utils.io import normalize_cols


def _load_dw_query(sql_filename: str, fonte: str) -> pd.DataFrame:
    if not use_sqlserver() or not use_dw_source(fonte):
        return pd.DataFrame()
    path = ROOT / 'sql' / sql_filename
    if not path.exists():
        return pd.DataFrame()
    return normalize_cols(read_sqlserver('DW', path.read_text(encoding='utf-8')))


def load_dw_indicasus_leitos() -> pd.DataFrame:
    return _load_dw_query('dw_indicasus_leitos.sql', 'INDICASUS')


def load_dw_cnes_estabelecimentos() -> pd.DataFrame:
    return _load_dw_query('dw_cnes_estabelecimentos.sql', 'CNES')


def load_dw_cnes_leitos() -> pd.DataFrame:
    return _load_dw_query('dw_cnes_leitos.sql', 'CNES')


def load_dw_sinan_agravos() -> pd.DataFrame:
    return _load_dw_query('dw_sinan_agravos_calor.sql', 'SINAN')


def load_dw_sim_obitos() -> pd.DataFrame:
    return _load_dw_query('dw_sim_obitos_calor.sql', 'SIM')


def load_dw_gal_lacen() -> pd.DataFrame:
    return _load_dw_query('dw_gal_lacen_resultados.sql', 'GAL')
