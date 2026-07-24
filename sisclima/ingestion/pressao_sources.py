from __future__ import annotations

import pandas as pd

from sisclima.core.config import ROOT, env, as_bool
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.sqlserver import read_sqlserver, use_sqlserver, probe_sqlserver
from sisclima.utils.io import normalize_cols

log = get_logger(__name__)


def _load_sql_file(name: str) -> str | None:
    path = ROOT / "sql" / name
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def load_dw_sih_internacoes() -> pd.DataFrame:
    """Pressão assistencial via VW_INTERNACAO no DW (senha DW)."""
    if not use_sqlserver() or not as_bool(env("USE_DW_SIH", env("USE_DW_INTERNACAO", "true")), True):
        return pd.DataFrame()
    sql = _load_sql_file("dw_sih_internacoes_calor.sql")
    if not sql:
        return pd.DataFrame()
    df = normalize_cols(read_sqlserver("DW", sql))
    if df is None or df.empty:
        log.warning("DW SIH/VW_INTERNACAO: consulta sem linhas")
        return pd.DataFrame()
    log.info("DW SIH/VW_INTERNACAO: %s linhas", len(df))
    return df


def _discover_sisreg_relation() -> str | None:
    probe = probe_sqlserver("SISREG")
    if not probe.get("ok"):
        log.warning("SISREG indisponível: %s", probe.get("detail"))
        return None
    catalog = read_sqlserver(
        "SISREG",
        """
        SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        ORDER BY TABLE_NAME
        """,
    )
    if catalog is None or catalog.empty:
        return None
    names = catalog.assign(
        full=catalog["TABLE_SCHEMA"].astype(str) + "." + catalog["TABLE_NAME"].astype(str),
        upper=catalog["TABLE_NAME"].astype(str).str.upper(),
    )
    preferred = [
        "VW_SOLICITACOES",
        "VW_REGULACAO",
        "VW_INTERNACAO",
        "SOLICITACOES",
        "REGULACAO",
        "PEDIDOS",
    ]
    for pref in preferred:
        hit = names[names["upper"].str.contains(pref, na=False)]
        if not hit.empty:
            return str(hit.iloc[0]["full"])
    # qualquer view com SOLICIT/REGUL
    hit = names[names["upper"].str.contains("SOLICIT|REGUL|INTERN", regex=True, na=False)]
    if not hit.empty:
        return str(hit.iloc[0]["full"])
    return None


def load_sisreg_solicitacoes() -> pd.DataFrame:
    """Pressão assistencial via SISREG (senha SISREG), se habilitado."""
    if not as_bool(env("USE_SISREG", "true"), True):
        return pd.DataFrame()
    # Garante HOST -> SERVER
    if env("SISREG_HOST") and not env("SISREG_SERVER"):
        import os

        os.environ["SISREG_SERVER"] = env("SISREG_HOST") or ""
    rel = _discover_sisreg_relation()
    if not rel:
        return pd.DataFrame()
    sql = f"SELECT TOP 100000 * FROM {rel}"
    df = normalize_cols(read_sqlserver("SISREG", sql))
    if df is None or df.empty:
        log.warning("SISREG %s: sem linhas", rel)
        return pd.DataFrame()
    log.info("SISREG %s: %s linhas", rel, len(df))
    df["fonte_pressao"] = f"SISREG:{rel}"
    return df


def load_pressao_assistencial_raw() -> pd.DataFrame:
    """Ordem: SISREG (se ok) → VW_INTERNACAO no DW."""
    sisreg = load_sisreg_solicitacoes()
    if not sisreg.empty:
        return sisreg
    sih = load_dw_sih_internacoes()
    if not sih.empty:
        sih["fonte_pressao"] = "DW:VW_INTERNACAO"
    return sih
