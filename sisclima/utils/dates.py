from __future__ import annotations
from datetime import datetime
import pandas as pd


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def today_str() -> str:
    return datetime.now().date().isoformat()


def to_date_col(df: pd.DataFrame, col: str = 'data') -> pd.DataFrame:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date.astype(str)
    return df
