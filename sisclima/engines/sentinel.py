from __future__ import annotations
import pandas as pd
from sisclima.utils.municipios import ensure_municipality, group_cols

KEYWORDS = {
    'calor': 2, 'insolação': 3, 'insolacao': 3, 'desidratação': 3, 'desidratacao': 3,
    'sem água': 3, 'sem agua': 3, 'falta de energia': 3, 'upa lotada': 4,
    'hospital lotado': 4, 'morte': 5, 'óbito': 5, 'obito': 5, 'idoso': 2, 'rua': 2,
    'queimada': 2, 'fumaça': 2, 'fumaca': 2, 'ar seco': 2, 'qualidade do ar': 2
}


def score_rumors(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=['data','cod_ibge','municipio','rumores_total','score_sentinela','rumores_criticos'])
    out = ensure_municipality(df)
    date_col = 'data_captura' if 'data_captura' in out.columns else 'data'
    out['data'] = pd.to_datetime(out[date_col], errors='coerce').dt.date.astype(str)
    text_col = 'texto' if 'texto' in out.columns else ('descricao' if 'descricao' in out.columns else None)
    if text_col:
        def score(txt):
            t = str(txt).lower()
            return sum(w for k,w in KEYWORDS.items() if k in t)
        out['score'] = out[text_col].apply(score)
    else:
        out['score'] = pd.to_numeric(out.get('score', 0), errors='coerce').fillna(0)
    out['critico'] = (out['score'] >= 5).astype(int)
    return out.groupby(group_cols(out), as_index=False).agg(rumores_total=('data','size'), score_sentinela=('score','sum'), rumores_criticos=('critico','sum'))
