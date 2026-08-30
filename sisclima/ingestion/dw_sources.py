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
    """
    Carrega SINAN do DW com camadas independentes (falha isolada por arquivo):
    1) agravos sensíveis ao calor (inclui dengue)
    2) ficha Chikungunya
    3) ficha Zika (quando existir)
    4) filtro de arboviroses na notificação individual
    """
    from sisclima.core.logging_utils import get_logger

    log = get_logger(__name__)
    parts: list[pd.DataFrame] = []
    for sql_name in (
        'dw_sinan_agravos_calor.sql',
        'dw_sinan_chikungunya.sql',
        'dw_sinan_zika.sql',
        'dw_sinan_arboviroses_notif.sql',
    ):
        try:
            chunk = _load_dw_query(sql_name, 'SINAN')
        except Exception as exc:
            # View ausente (ex.: VW_SINAN_ZIKA) não interrompe as demais camadas.
            log.warning("SINAN DW %s indisponível: %s", sql_name, exc)
            chunk = pd.DataFrame()
        if chunk is not None and not chunk.empty:
            parts.append(chunk)
        elif sql_name == 'dw_sinan_zika.sql':
            log.info("SINAN Zika: view/arquivo ausente no DW — camada ignorada.")

    if not parts:
        return pd.DataFrame()

    out = pd.concat(parts, ignore_index=True, sort=False)
    subset = [c for c in ['numero_notificacao', 'data', 'cod_ibge', 'agravo'] if c in out.columns]
    if subset:
        out = out.drop_duplicates(subset=subset, keep='first')
    return out.reset_index(drop=True)


def load_dw_sivep_srag() -> pd.DataFrame:
    """SIVEP/SRAG no DW (fallback quando pasta local está vazia). Flag: USE_DW_SIVEP."""
    try:
        return _load_dw_query('sivep_srag_residencia.sql', 'SIVEP')
    except Exception:
        return pd.DataFrame()


def load_dw_sim_obitos() -> pd.DataFrame:
    return _load_dw_query('dw_sim_obitos_calor.sql', 'SIM')


def load_dw_sinan_intoxicacao_detalhe() -> pd.DataFrame:
    """Ficha intoxicação exógena (detalhe para filtro fumaça/queimada)."""
    return _load_dw_query('dw_sinan_intoxicacao_detalhe.sql', 'SINAN')


def load_dw_indicasus_internacao() -> pd.DataFrame:
    """Internações IndicaSUS no DW SES (dbo.VW_INTERNACAO) por CID sensível ao clima."""
    return _load_dw_query('dw_internacao_cid_clima.sql', 'INDICASUS')


def load_dw_internacao_cid_clima() -> pd.DataFrame:
    """Alias legado — preferir load_dw_indicasus_internacao()."""
    return load_dw_indicasus_internacao()


def load_dw_sinan_agravos_extras_clima() -> pd.DataFrame:
    """SINAN extras: hantavirose, peçonhentos, SRAG, leishmaniose, febre maculosa."""
    return _load_dw_query('dw_sinan_agravos_extras_clima.sql', 'SINAN')


def load_dw_gal_lacen() -> pd.DataFrame:
    return _load_dw_query('dw_gal_lacen_resultados.sql', 'GAL')
