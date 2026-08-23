from __future__ import annotations
import numpy as np
import pandas as pd
from sisclima.utils.municipios import ensure_municipality

LEVEL_SCORE = {'verde':0, 'amarela':1, 'laranja':2, 'vermelha':3, 'roxa':4}
SCORE_LEVEL = {v:k for k,v in LEVEL_SCORE.items()}

ALIASES = {
    'pm25': 'pm25_ugm3', 'pm2_5': 'pm25_ugm3', 'pm2.5': 'pm25_ugm3', 'particulate_matter_2_5um': 'pm25_ugm3',
    'pm10': 'pm10_ugm3', 'particulate_matter_10um': 'pm10_ugm3',
    'o3': 'o3_ugm3', 'ozone': 'o3_ugm3',
    'no2': 'no2_ugm3', 'nitrogen_dioxide': 'no2_ugm3',
    'co': 'co_mgm3', 'carbon_monoxide': 'co_mgm3',
    'so2': 'so2_ugm3', 'sulphur_dioxide': 'so2_ugm3', 'sulfur_dioxide': 'so2_ugm3'
}

POLLUTANT_LABELS = {
    'pm25_ugm3': 'PM2.5', 'pm10_ugm3': 'PM10', 'o3_ugm3': 'Ozônio',
    'no2_ugm3': 'NO2', 'co_mgm3': 'CO', 'so2_ugm3': 'SO2'
}


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def normalize_air_quality(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=['data','cod_ibge','municipio','pm25_ugm3','pm10_ugm3','o3_ugm3','no2_ugm3','co_mgm3','so2_ugm3','fonte'])
    out = ensure_municipality(df.copy())
    out.columns = [str(c).strip().lower().replace(' ', '_').replace('-', '_') for c in out.columns]
    rename = {c: ALIASES[c] for c in out.columns if c in ALIASES}
    out = out.rename(columns=rename)
    if 'data' not in out.columns:
        date_candidates = [c for c in ['time','valid_time','datetime','data_referencia'] if c in out.columns]
        if date_candidates:
            out['data'] = out[date_candidates[0]]
        else:
            out['data'] = pd.Timestamp.now().date().isoformat()
    out['data'] = pd.to_datetime(out['data'], errors='coerce').dt.date.astype(str)
    pollutants = list(POLLUTANT_LABELS.keys())
    for c in pollutants:
        if c not in out.columns:
            out[c] = np.nan
    out = _to_numeric(out, pollutants)
    # Conversões defensivas: CAMS pode vir em kg/m3 para PM. Se valor muito pequeno, converter para ug/m3.
    for c in ['pm25_ugm3','pm10_ugm3','o3_ugm3','no2_ugm3','so2_ugm3']:
        small = out[c].notna() & (out[c].abs() < 1e-3)
        out.loc[small, c] = out.loc[small, c] * 1e9
    # CO: se vier em kg/m3, aproxima para mg/m3; se já vier em mg/m3, permanece.
    if 'co_mgm3' in out.columns:
        small = out['co_mgm3'].notna() & (out['co_mgm3'].abs() < 1e-3)
        out.loc[small, 'co_mgm3'] = out.loc[small, 'co_mgm3'] * 1e6
    if 'fonte' not in out.columns:
        out['fonte'] = 'copernicus_cams/local'
    keep = ['data','cod_ibge','municipio'] + pollutants + ['fonte']
    extra = [c for c in ['lat','lon','valid_time','leadtime_hour'] if c in out.columns]
    return out[[c for c in keep + extra if c in out.columns]]


def pollutant_stage(value: float, thresholds: dict) -> tuple[int, str]:
    if value is None or pd.isna(value):
        return 0, 'indisponível'
    for lvl, score in [('roxa',4), ('vermelha',3), ('laranja',2), ('amarela',1)]:
        if lvl in thresholds and value >= thresholds[lvl]:
            return score, lvl
    return 0, 'verde'


def add_air_quality_indicators(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    out = normalize_air_quality(df)
    if out.empty:
        return out
    cfg = settings.get('qualidade_ar', {})
    pollutants = list(POLLUTANT_LABELS.keys())
    scores = []
    levels = []
    dominant = []
    motivos = []
    for _, r in out.iterrows():
        best_score = 0; best_level = 'verde'; best_poll = None; best_text = []
        for c in pollutants:
            th = cfg.get(c, {})
            s, lvl = pollutant_stage(r.get(c), th)
            if s > best_score:
                best_score = s; best_level = lvl; best_poll = c
            if s > 0:
                best_text.append(f'{POLLUTANT_LABELS[c]} {r.get(c):.1f} atingiu {lvl}')
        scores.append(best_score)
        levels.append(best_level)
        dominant.append(POLLUTANT_LABELS.get(best_poll, '—'))
        motivos.append('; '.join(best_text) if best_text else 'qualidade do ar em normalidade operacional')
    out['iq_ar_score'] = scores
    out['qualidade_ar_nivel'] = levels
    out['poluente_dominante'] = dominant
    out['motivo_qualidade_ar'] = motivos
    out['indice_qualidade_ar_operacional'] = (out['iq_ar_score'] / 4 * 100).round(1)
    return out
