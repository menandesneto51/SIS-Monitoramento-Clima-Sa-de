from __future__ import annotations
import pandas as pd
from sisclima.ingestion.dw_sources import load_dw_indicasus_leitos
from sisclima.ingestion.local_csv import load_csv
from sisclima.utils.io import normalize_cols


def load_indicasus_leitos() -> pd.DataFrame:
    # V4: IndicaSUS/leitos será lido pelo Data Warehouse SES/MT, prefixo DW_.
    df = load_dw_indicasus_leitos()
    if df is not None and not df.empty:
        return normalize_cols(df)
    return load_csv('indicasus_csv', ['data'])
