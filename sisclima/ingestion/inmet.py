from __future__ import annotations
import pandas as pd
import requests
from sisclima.core.config import env
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)


def fetch_inmet_alerts() -> pd.DataFrame:
    """Conector genérico para alertas INMET.

    Se INMET_ALERTS_URL estiver vazio, retorna DataFrame vazio e o pipeline usa CSV.
    """
    url = env('INMET_ALERTS_URL')
    if not url:
        return pd.DataFrame()
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        js = r.json()
        if isinstance(js, list):
            return pd.DataFrame(js)
        if isinstance(js, dict):
            for key in ['data','alertas','features','items']:
                if key in js and isinstance(js[key], list):
                    return pd.DataFrame(js[key])
            return pd.DataFrame([js])
    except Exception as e:
        log.warning('Falha ao consultar alertas INMET: %s', e)
    return pd.DataFrame()


def normalize_inmet_alerts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [str(c).lower().strip().replace(' ', '_') for c in df.columns]
    # Padronização mínima esperada pelo motor de estágio
    for col in ['nivel','severidade','risco']:
        if col in df.columns and 'nivel_alerta' not in df.columns:
            df = df.rename(columns={col:'nivel_alerta'})
            break
    return df
