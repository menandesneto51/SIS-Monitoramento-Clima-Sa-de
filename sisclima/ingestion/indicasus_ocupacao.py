from __future__ import annotations

from datetime import datetime

import pandas as pd

from sisclima.core.config import ROOT, env, as_bool
from sisclima.core.db import write_df, sqlite_conn
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.sqlserver import build_sqlserver_conn, probe_sqlserver, read_sqlserver
from sisclima.utils.io import normalize_cols
from sisclima.utils.municipios import ensure_municipality

log = get_logger(__name__)


def _ensure_indicasus_server_alias() -> None:
    import os

    host = env("INDICASUS_HOST") or env("INDICASUS_SERVER")
    if host and not env("INDICASUS_SERVER"):
        os.environ["INDICASUS_SERVER"] = host


def descobrir_objetos_indicasus() -> pd.DataFrame:
    _ensure_indicasus_server_alias()
    return read_sqlserver(
        "INDICASUS",
        """
        SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE IN ('BASE TABLE', 'VIEW')
        ORDER BY TABLE_NAME
        """,
    )


def _pick_occupancy_relation(catalog: pd.DataFrame) -> str | None:
    if catalog is None or catalog.empty:
        return None
    names = catalog.assign(
        full=catalog["TABLE_SCHEMA"].astype(str) + "." + catalog["TABLE_NAME"].astype(str),
        upper=catalog["TABLE_NAME"].astype(str).str.upper(),
    )
    preferred = [
        "VW_OCUPACAO_LEITOS_MUNICIPIO",
        "VW_OCUPACAO_LEITOS",
        "VW_OCUPACAO",
        "OCUPACAO_LEITOS",
        "LEITOMOVIMENTO",
        "MOVIMENTOLEITO",
        "LEITOS",
    ]
    for pref in preferred:
        hit = names[names["upper"] == pref]
        if not hit.empty:
            return str(hit.iloc[0]["full"])
    hit = names[names["upper"].str.contains("OCUP|LEITO", regex=True, na=False)]
    if not hit.empty:
        return str(hit.iloc[0]["full"])
    return None


def _normalize_occupancy(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = normalize_cols(df.copy())
    out = ensure_municipality(out)

    rename_map = {}
    lower = {c.lower(): c for c in out.columns}

    def _find(*cands: str) -> str | None:
        for c in cands:
            if c.lower() in lower:
                return lower[c.lower()]
            for k, orig in lower.items():
                if c.lower() in k:
                    return orig
        return None

    pairs = {
        "cod_ibge": ["cod_ibge", "codigoibge", "codibge", "ibge", "codmunicipio"],
        "municipio": ["municipio", "municipio_indicasus", "nomemunicipio", "localidade"],
        "LocalidadeId": ["localidadeid", "idlocalidade"],
        "unidades": ["unidades", "qtdunidades"],
        "ultima_movimentacao": ["ultima_movimentacao", "dataatualizacao", "datamovimento"],
        "leitos_existentes": ["leitos_existentes", "leitosexistentes", "leitostotal", "capacidade"],
        "leitos_sus": ["leitos_sus", "leitossus"],
        "leitos_ocupados": ["leitos_ocupados", "leitosocupados", "ocupados"],
        "leitos_bloqueados_cadastro": ["leitos_bloqueados_cadastro", "bloqueadoscadastro"],
        "leitos_bloqueados_movimento": ["leitos_bloqueados_movimento", "bloqueadosmovimento"],
        "leitos_higienizacao": ["leitos_higienizacao", "higienizacao"],
        "leitos_reservados": ["leitos_reservados", "reservados"],
        "ocupacao_pct": ["ocupacao_pct", "taxaocupacao", "percentualocupacao", "ocupacao"],
    }
    for target, cands in pairs.items():
        src = _find(*cands)
        if src and src != target:
            rename_map[src] = target
    if rename_map:
        out = out.rename(columns=rename_map)

    if "cod_ibge" in out.columns:
        out["cod_ibge"] = (
            out["cod_ibge"]
            .astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.extract(r"(\d+)", expand=False)
            .fillna("")
            .str.zfill(7)
        )
        out["cod_ibge_6"] = out["cod_ibge"].str[:6]

    for c in [
        "leitos_existentes",
        "leitos_sus",
        "leitos_ocupados",
        "leitos_bloqueados_cadastro",
        "leitos_bloqueados_movimento",
        "leitos_higienizacao",
        "leitos_reservados",
        "ocupacao_pct",
        "unidades",
    ]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    if "ocupacao_pct" not in out.columns or out["ocupacao_pct"].isna().all():
        total = pd.to_numeric(out.get("leitos_existentes"), errors="coerce")
        ocup = pd.to_numeric(out.get("leitos_ocupados"), errors="coerce")
        out["ocupacao_pct"] = (ocup / total * 100).where(total > 0)

    if "municipio_base" not in out.columns and "municipio" in out.columns:
        out["municipio_base"] = out["municipio"]
    if "municipio_indicasus" not in out.columns and "municipio" in out.columns:
        out["municipio_indicasus"] = out["municipio"]

    out["fonte"] = "INDICASUS_TEMPO_REAL"
    out["data_processamento"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return out


def load_indicasus_ocupacao_raw() -> pd.DataFrame:
    """Lê ocupação do BdSES com usuário Roney."""
    if as_bool(env("INDICASUS_USE_DW_CREDENTIALS", "false"), False):
        log.warning("INDICASUS_USE_DW_CREDENTIALS=true — ocupação deveria usar Roney; seguindo mesmo assim")

    _ensure_indicasus_server_alias()
    probe = probe_sqlserver("INDICASUS")
    if not probe.get("ok"):
        log.warning("IndicaSUS ocupação: %s", probe.get("detail"))
        return pd.DataFrame()

    # 1) SQL dedicado, se existir e funcionar
    sql_path = ROOT / "sql" / "indicasus_ocupacao_municipio.sql"
    if sql_path.exists():
        sql = sql_path.read_text(encoding="utf-8")
        # ignora template se ainda aponta para view inexistente sem descoberta
        df = read_sqlserver("INDICASUS", sql)
        if df is not None and not df.empty:
            log.info("IndicaSUS ocupação via SQL dedicado: %s linhas", len(df))
            return _normalize_occupancy(df)

    # 2) Descoberta automática
    catalog = descobrir_objetos_indicasus()
    rel = _pick_occupancy_relation(catalog)
    if not rel:
        log.warning(
            "IndicaSUS: nenhuma view/tabela de ocupação encontrada. "
            "Rode atualizar_ocupacao_indicasus.py --descobrir e ajuste sql/indicasus_ocupacao_municipio.sql"
        )
        return pd.DataFrame()

    df = read_sqlserver("INDICASUS", f"SELECT TOP 50000 * FROM {rel}")
    if df is None or df.empty:
        log.warning("IndicaSUS %s sem linhas", rel)
        return pd.DataFrame()
    log.info("IndicaSUS ocupação via %s: %s linhas", rel, len(df))
    return _normalize_occupancy(df)


def persist_indicasus_ocupacao(df: pd.DataFrame) -> dict[str, int]:
    """Grava hospital_ocupacao_municipio / estado no SQLite do SIS."""
    if df is None or df.empty:
        return {"municipio": 0, "estado": 0}

    mun = df.copy()
    write_df(mun, "hospital_ocupacao_municipio")
    write_df(mun, "raw_indicasus_ocupacao_tempo_real")

    estado = pd.DataFrame()
    if "ocupacao_pct" in mun.columns:
        occ = pd.to_numeric(mun["ocupacao_pct"], errors="coerce")
        total = pd.to_numeric(mun.get("leitos_existentes"), errors="coerce")
        ocup = pd.to_numeric(mun.get("leitos_ocupados"), errors="coerce")
        if total.notna().any() and ocup.notna().any() and float(total.sum(min_count=1) or 0) > 0:
            pct = float(ocup.sum(min_count=1) / total.sum(min_count=1) * 100)
        else:
            pct = float(occ.mean()) if occ.notna().any() else None
        if pct is not None:
            estado = pd.DataFrame(
                [
                    {
                        "ocupacao_pct": pct,
                        "municipios": int(mun["cod_ibge"].nunique()) if "cod_ibge" in mun.columns else len(mun),
                        "fonte": "INDICASUS_TEMPO_REAL",
                        "data_processamento": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                ]
            )
            write_df(estado, "hospital_ocupacao_estado")

    return {"municipio": len(mun), "estado": len(estado)}


def atualizar_ocupacao_indicasus() -> dict:
    conn = build_sqlserver_conn("INDICASUS")
    if not conn:
        return {"ok": False, "detail": "conexão INDICASUS não montada (confira HOST/DB/USER/PASSWORD do Roney)"}
    raw = load_indicasus_ocupacao_raw()
    if raw.empty:
        return {
            "ok": False,
            "detail": "sem linhas de ocupação — rode com --descobrir e ajuste o SQL",
        }
    counts = persist_indicasus_ocupacao(raw)
    return {"ok": True, "detail": f"municipios={counts['municipio']} estado={counts['estado']}", **counts}
