# -*- coding: utf-8 -*-
"""Filtros e extração agregada e-SUS APS x clima (sem PII)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from sisclima.core.config import ROOT
from sisclima.core.db import write_df
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.esus_aps import (
    credentials_ready,
    esus_aps_config,
    read_esus_sql,
    use_esus_aps,
)

log = get_logger(__name__)

TABLE_ATEND = "ops_esus_aps_municipio"
TABLE_CAD = "ops_esus_aps_cadastro_municipio"
TABLE_PRIO = "ops_esus_aps_prioridade"
TABLE_FULL = "ops_esus_aps_municipal"
CSV_ATEND = ROOT / "data" / "esus_aps" / "ops_esus_aps_municipio.csv"
CSV_CAD = ROOT / "data" / "esus_aps" / "ops_esus_aps_cadastro_municipio.csv"
CSV_PRIO = ROOT / "data" / "esus_aps" / "ops_esus_aps_prioridade.csv"
CSV_FULL = ROOT / "data" / "esus_aps" / "ops_esus_aps_municipal.csv"
SQL_ATEND = ROOT / "sql" / "esus_aps_atendimentos_municipio.sql"
SQL_CAD = ROOT / "sql" / "esus_aps_cadastro_municipio.sql"

NIVEIS_CRITICOS = frozenset({"vermelha", "roxa"})

SIGTAP_NEBULIZACAO: tuple[str, ...] = ("0301100039", "0301100047")

# CID alinhado ao catálogo El Niño (IndicaSUS/SIVEP).
CID_RESP_RE = r"(^|[^A-Z0-9])J(21|3[0-9]|4[0-5])"
CID_CALOR_RE = r"(^|[^A-Z0-9])(E86|E87|T67|X30)"
CID_DDA_RE = r"(^|[^A-Z0-9])(A09|K52)"
CIAP_RESP_RE = r"(^|[^A-Z0-9])R(05|06|07|96|97|98)"

_IBGE_DIGITS = re.compile(r"\D+")
_SIGTAP_DIGITS = re.compile(r"\D+")


def normalize_sigtap(code: Any) -> str:
    return _SIGTAP_DIGITS.sub("", str(code or ""))


def is_nebulizacao_sigtap(code: Any) -> bool:
    return normalize_sigtap(code) in SIGTAP_NEBULIZACAO


def is_mt_ibge(code: Any) -> bool:
    digits = _IBGE_DIGITS.sub("", str(code or ""))
    return digits.startswith("51") and len(digits) >= 6


def normalize_ibge7(code: Any) -> str:
    digits = _IBGE_DIGITS.sub("", str(code or ""))
    if not digits:
        return ""
    if len(digits) >= 7:
        return digits[:7]
    return digits.ljust(7, "0") if digits.startswith("51") and len(digits) == 6 else digits


def match_cid_group(text: Any, pattern: str) -> bool:
    blob = str(text or "").upper().replace(" ", "")
    return bool(re.search(pattern, blob, flags=re.IGNORECASE))


def recorte_mt(df: pd.DataFrame, col: str = "cod_ibge") -> pd.DataFrame:
    if df is None or df.empty or col not in df.columns:
        return pd.DataFrame() if df is None else df.iloc[0:0].copy()
    out = df.copy()
    out[col] = out[col].map(normalize_ibge7)
    return out[out[col].map(is_mt_ibge)].copy()


def _as_utc_day(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)


def probe_max_atendimento_valido(*, reader=None) -> date | None:
    """Última data válida de atendimento no Centralizador (ignora datas futuras)."""
    sql = """
    SELECT MAX(dt_inicial_atendimento)::date AS max_dt
    FROM tb_fat_atendimento_individual
    WHERE dt_inicial_atendimento < (NOW() + INTERVAL '1 day')
      AND dt_inicial_atendimento >= (NOW() - INTERVAL '180 days')
    """
    fn = reader or _default_reader
    try:
        df = fn(sql)
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao sondar max(dt_inicial_atendimento): %s", exc)
        return None
    if df is None or df.empty or "max_dt" not in df.columns:
        return None
    val = df.iloc[0]["max_dt"]
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return pd.to_datetime(val).date()
    except Exception:  # noqa: BLE001
        return None


def _janelas(
    ref: date | None = None,
    *,
    ancora: date | None = None,
    max_lag_dias: int = 3,
) -> dict[str, Any]:
    """Janelas 7d/28d.

    Se o Centralizador estiver atrasado (âncora << ref), a janela operacional
    usa a última data válida — evita 7d=0 e cobertura municipal artificialmente baixa.
    """
    calendario = ref or date.today()
    fim = calendario
    ancorada = False
    atraso_dias = 0
    if ancora is not None:
        atraso_dias = max(0, (calendario - ancora).days)
        if atraso_dias > max_lag_dias:
            fim = ancora
            ancorada = True
    return {
        "data_referencia": calendario,
        "data_janela_fim": fim,
        "data_max_atendimento": ancora,
        "atraso_dias": atraso_dias,
        "janela_ancorada": ancorada,
        "dt_ini_7d": _as_utc_day(fim - timedelta(days=6)),
        "dt_ini_28d": _as_utc_day(fim - timedelta(days=27)),
        "dt_fim": _as_utc_day(fim + timedelta(days=1)),
    }


def _load_sql(path: Path) -> str:
    sql = path.read_text(encoding="utf-8")
    return (
        sql.replace("{{CID_RESP}}", CID_RESP_RE)
        .replace("{{CID_CALOR}}", CID_CALOR_RE)
        .replace("{{CID_DDA}}", CID_DDA_RE)
        .replace("{{CIAP_RESP}}", CIAP_RESP_RE)
        .replace("{{SIGTAP_A}}", SIGTAP_NEBULIZACAO[0])
        .replace("{{SIGTAP_B}}", SIGTAP_NEBULIZACAO[1])
    )


def _default_reader(sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    return read_esus_sql(sql, params, query_timeout_seconds=600)


def fetch_atendimentos_municipio(
    *,
    ref: date | None = None,
    reader=None,
    ancorar_atraso: bool = True,
    max_lag_dias: int = 3,
) -> pd.DataFrame:
    fn = reader or _default_reader
    ancora = probe_max_atendimento_valido(reader=fn) if ancorar_atraso else None
    jan = _janelas(ref, ancora=ancora, max_lag_dias=max_lag_dias)
    if jan["janela_ancorada"]:
        log.warning(
            "e-SUS APS com atraso de %s dia(s): última data válida %s. "
            "Janela 7d/28d ancorada nessa data (não usar como zero clínico).",
            jan["atraso_dias"],
            jan["data_janela_fim"],
        )
    sql = _load_sql(SQL_ATEND)
    df = fn(
        sql,
        {
            "dt_ini_7d": jan["dt_ini_7d"],
            "dt_ini_28d": jan["dt_ini_28d"],
            "dt_fim": jan["dt_fim"],
        },
    )
    if df is None or df.empty:
        return pd.DataFrame()
    out = recorte_mt(df, "cod_ibge")
    out["data_referencia"] = jan["data_referencia"].isoformat()
    out["data_janela_fim"] = jan["data_janela_fim"].isoformat()
    out["data_max_atendimento"] = (
        jan["data_max_atendimento"].isoformat() if jan["data_max_atendimento"] else ""
    )
    out["atraso_dias"] = int(jan["atraso_dias"])
    out["janela_ancorada"] = bool(jan["janela_ancorada"])
    out["fonte"] = "esus2_centralizador"
    out["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    return out


def fetch_cadastro_municipio(*, ref: date | None = None, reader=None) -> pd.DataFrame:
    jan = _janelas(ref)
    sql = _load_sql(SQL_CAD)
    fn = reader or _default_reader
    try:
        df = fn(sql)
    except Exception as exc:  # noqa: BLE001
        log.warning("Cadastro e-SUS com faixa etária indisponível (%s); tenta sem idosos.", exc)
        df = fn(_sql_cadastro_sem_faixa())
    if df is None or df.empty:
        return pd.DataFrame()
    out = recorte_mt(df, "cod_ibge")
    if "idoso_60mais" not in out.columns:
        out["idoso_60mais"] = 0
    out["data_referencia"] = jan["data_referencia"].isoformat()
    out["fonte"] = "esus2_centralizador"
    out["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    return out


def _sql_cadastro_sem_faixa() -> str:
    return """
    WITH mun AS (
        SELECT
            co_seq_dim_municipio,
            no_municipio,
            regexp_replace(COALESCE(co_ibge::text, ''), '[^0-9]', '', 'g') AS ibge
        FROM tb_dim_municipio
        WHERE regexp_replace(COALESCE(co_ibge::text, ''), '[^0-9]', '', 'g') LIKE '51%'
    )
    SELECT
        m.ibge AS cod_ibge,
        MAX(m.no_municipio) AS municipio,
        COUNT(DISTINCT c.co_fat_cidadao_pec) AS cadastros,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_gestante, 0) = 1 THEN c.co_fat_cidadao_pec END) AS gestante,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_doenca_respira_asma, 0) = 1 THEN c.co_fat_cidadao_pec END) AS asma,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_doenca_respira_dpoc_enfisem, 0) = 1 THEN c.co_fat_cidadao_pec END) AS dpoc,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_doenca_respiratoria, 0) = 1 THEN c.co_fat_cidadao_pec END) AS doenca_respiratoria,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_fumante, 0) = 1 THEN c.co_fat_cidadao_pec END) AS fumante,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_hipertensao_arterial, 0) = 1 THEN c.co_fat_cidadao_pec END) AS hipertensao,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_diabete, 0) = 1 THEN c.co_fat_cidadao_pec END) AS diabetes,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_acamado, 0) = 1 THEN c.co_fat_cidadao_pec END) AS acamado,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_domiciliado, 0) = 1 THEN c.co_fat_cidadao_pec END) AS domiciliado,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_comunidade_tradicional, 0) = 1 THEN c.co_fat_cidadao_pec END) AS comunidade_tradicional,
        COUNT(DISTINCT CASE WHEN COALESCE(c.st_deficiencia, 0) = 1 THEN c.co_fat_cidadao_pec END) AS deficiencia,
        0 AS idoso_60mais
    FROM tb_fat_cad_individual c
    INNER JOIN mun m ON m.co_seq_dim_municipio = c.co_dim_municipio
    GROUP BY m.ibge
    ORDER BY m.ibge
    """


def persist_ops(df: pd.DataFrame, table: str, csv_path: Path) -> int:
    if df is None:
        df = pd.DataFrame()
    write_df(df, table, if_exists="replace")
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return len(df)


def _ibge6(code: Any) -> str:
    digits = _IBGE_DIGITS.sub("", str(code or ""))
    return digits[:6] if len(digits) >= 6 else digits


def cruzar_esus_classe_araras(
    atend: pd.DataFrame | None = None,
    cad: pd.DataFrame | None = None,
    resumo: pd.DataFrame | None = None,
    *,
    so_criticos: bool = True,
) -> pd.DataFrame:
    """Cadastro + pressão APS por município, com classe ARARAS.

    so_criticos=True restringe a vermelho/roxo; False devolve o estado (142).
    """
    from sisclima.core.db import read_table

    if atend is None:
        atend = read_table(TABLE_ATEND)
    if cad is None:
        cad = read_table(TABLE_CAD)
    if resumo is None:
        resumo = read_table("resumo_municipal_atual")
    if resumo is None or resumo.empty or "nivel" not in resumo.columns:
        return pd.DataFrame()
    nivel_col = "cod_ibge" if "cod_ibge" in resumo.columns else None
    if nivel_col is None:
        for c in ("codigo_ibge", "ibge"):
            if c in resumo.columns:
                nivel_col = c
                break
    if not nivel_col:
        return pd.DataFrame()
    cls = resumo[[nivel_col, "nivel"]].copy()
    if "municipio" in resumo.columns:
        cls["municipio_araras"] = resumo["municipio"]
    cls["_k"] = cls[nivel_col].map(_ibge6)
    cls["classe_araras"] = cls["nivel"].astype(str).str.lower().str.strip()
    if so_criticos:
        cls = cls[cls["classe_araras"].isin(NIVEIS_CRITICOS)].drop_duplicates("_k")
    else:
        cls = cls.drop_duplicates("_k")

    left = cad.copy() if cad is not None and not cad.empty else pd.DataFrame()
    if left.empty and atend is not None and not atend.empty:
        left = atend[["cod_ibge", "municipio"]].copy()
    if left.empty:
        return pd.DataFrame()
    left["_k"] = left["cod_ibge"].map(_ibge6)
    if atend is not None and not atend.empty:
        a = atend.copy()
        a["_k"] = a["cod_ibge"].map(_ibge6)
        keep = [
            c
            for c in (
                "atendimentos_7d",
                "atendimentos_28d",
                "resp_cid_7d",
                "resp_cid_28d",
                "resp_ciap_7d",
                "calor_cid_7d",
                "calor_cid_28d",
                "dda_cid_7d",
                "dda_cid_28d",
                "nebulizacao_7d",
                "nebulizacao_28d",
                "encaminhamento_urgencia_7d",
                "encaminhamento_internacao_7d",
                "data_max_atendimento",
                "data_janela_fim",
                "atraso_dias",
                "janela_ancorada",
            )
            if c in a.columns
        ]
        left = left.merge(a[["_k"] + keep], on="_k", how="left")
        for c in keep:
            if c in {"data_max_atendimento", "data_janela_fim"}:
                left[c] = left[c].fillna("")
            elif c == "janela_ancorada":
                left[c] = left[c].fillna(False)
            elif c == "atraso_dias":
                left[c] = pd.to_numeric(left[c], errors="coerce").fillna(0)
            else:
                left[c] = pd.to_numeric(left[c], errors="coerce").fillna(0)
    if so_criticos:
        out = left.merge(cls[["_k", "classe_araras"]], on="_k", how="inner")
    else:
        out = left.merge(cls[["_k", "classe_araras"]], on="_k", how="left")
        out["classe_araras"] = out["classe_araras"].fillna("")
    out = out.drop(columns=["_k"], errors="ignore")
    if "municipio" not in out.columns and "municipio_araras" in out.columns:
        out["municipio"] = out["municipio_araras"]
    sort_cols = [c for c in ("classe_araras", "asma", "idoso_60mais", "atendimentos_7d") if c in out.columns]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return out.reset_index(drop=True)


def persist_prioridade(df: pd.DataFrame) -> int:
    return persist_ops(df, TABLE_PRIO, CSV_PRIO)


def persist_municipal(df: pd.DataFrame) -> int:
    return persist_ops(df, TABLE_FULL, CSV_FULL)


def resumo_esus_estadual(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Totais e ranking (sem PII) para boletim e Sala."""
    from sisclima.core.db import read_table

    if df is None:
        df = read_table(TABLE_FULL)
        if df is None or df.empty:
            df = read_table(TABLE_CAD)
    if df is None or df.empty:
        return {"status": "sem_carga", "municipios": 0}

    def _s(col: str) -> int:
        if col not in df.columns:
            return 0
        return int(round(float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())))

    crit = df.copy()
    if "classe_araras" in crit.columns:
        crit = crit[crit["classe_araras"].astype(str).str.lower().isin(NIVEIS_CRITICOS)]
    else:
        crit = crit.iloc[0:0]
    ranking_cols = [
        c
        for c in (
            "municipio",
            "cod_ibge",
            "classe_araras",
            "asma",
            "dpoc",
            "idoso_60mais",
            "gestante",
            "acamado",
            "atendimentos_28d",
            "nebulizacao_7d",
            "resp_cid_28d",
        )
        if c in crit.columns
    ]
    rank = crit
    if "asma" in rank.columns:
        rank = rank.sort_values("asma", ascending=False)
    ranking = rank[ranking_cols].head(12).to_dict(orient="records") if ranking_cols and not rank.empty else []

    ordem = ["roxa", "vermelha", "laranja", "amarela", "verde", ""]
    por_classe: list[dict[str, Any]] = []
    if "classe_araras" in df.columns:
        cls = df["classe_araras"].astype(str).str.lower().str.strip()
        for nivel in ordem:
            sub = df[cls == nivel]
            if sub.empty:
                continue
            por_classe.append(
                {
                    "classe": nivel or "sem classe",
                    "municipios": int(len(sub)),
                    "asma": int(round(float(pd.to_numeric(sub.get("asma"), errors="coerce").fillna(0).sum())))
                    if "asma" in sub.columns
                    else 0,
                    "idoso_60mais": int(
                        round(float(pd.to_numeric(sub.get("idoso_60mais"), errors="coerce").fillna(0).sum()))
                    )
                    if "idoso_60mais" in sub.columns
                    else 0,
                    "atendimentos_28d": int(
                        round(float(pd.to_numeric(sub.get("atendimentos_28d"), errors="coerce").fillna(0).sum()))
                    )
                    if "atendimentos_28d" in sub.columns
                    else 0,
                    "nebulizacao_28d": int(
                        round(float(pd.to_numeric(sub.get("nebulizacao_28d"), errors="coerce").fillna(0).sum()))
                    )
                    if "nebulizacao_28d" in sub.columns
                    else 0,
                }
            )

    mun_cols = [
        c
        for c in (
            "municipio",
            "cod_ibge",
            "classe_araras",
            "asma",
            "dpoc",
            "idoso_60mais",
            "gestante",
            "acamado",
            "atendimentos_28d",
            "resp_cid_28d",
            "nebulizacao_28d",
            "nebulizacao_7d",
        )
        if c in df.columns
    ]
    mun_sort = df.copy()
    if "classe_araras" in mun_sort.columns:
        mun_sort["_ord"] = mun_sort["classe_araras"].astype(str).str.lower().map(
            {k: i for i, k in enumerate(ordem)}
        ).fillna(len(ordem))
        by = ["_ord"]
        if "asma" in mun_sort.columns:
            by.append("asma")
        mun_sort = mun_sort.sort_values(by, ascending=[True, False][: len(by)])
        mun_sort = mun_sort.drop(columns=["_ord"])
    elif "asma" in mun_sort.columns:
        mun_sort = mun_sort.sort_values("asma", ascending=False)
    municipais = mun_sort[mun_cols].to_dict(orient="records") if mun_cols else []

    atraso = 0
    if "atraso_dias" in df.columns:
        atraso = int(pd.to_numeric(df["atraso_dias"], errors="coerce").fillna(0).max())
    data_max = ""
    if "data_max_atendimento" in df.columns:
        vals = df["data_max_atendimento"].dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        data_max = str(vals.iloc[0]) if not vals.empty else ""
    janela_fim = ""
    if "data_janela_fim" in df.columns:
        vals = df["data_janela_fim"].dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        janela_fim = str(vals.iloc[0]) if not vals.empty else ""
    ancorada = bool(
        "janela_ancorada" in df.columns
        and pd.Series(df["janela_ancorada"]).astype(str).str.lower().isin({"true", "1"}).any()
    )
    # Fallback: metadados ficam na tabela de atendimento quando o cruzamento antigo não os trouxe.
    if not data_max:
        atend_meta = read_table(TABLE_ATEND)
        if atend_meta is not None and not atend_meta.empty:
            if "data_max_atendimento" in atend_meta.columns:
                vals = atend_meta["data_max_atendimento"].dropna().astype(str).str.strip()
                vals = vals[vals != ""]
                if not vals.empty:
                    data_max = str(vals.iloc[0])
            if (not janela_fim) and "data_janela_fim" in atend_meta.columns:
                vals = atend_meta["data_janela_fim"].dropna().astype(str).str.strip()
                vals = vals[vals != ""]
                if not vals.empty:
                    janela_fim = str(vals.iloc[0])
            if "atraso_dias" in atend_meta.columns:
                atraso = int(pd.to_numeric(atend_meta["atraso_dias"], errors="coerce").fillna(0).max())
            if "janela_ancorada" in atend_meta.columns:
                ancorada = bool(
                    pd.Series(atend_meta["janela_ancorada"])
                    .astype(str)
                    .str.lower()
                    .isin({"true", "1"})
                    .any()
                )

    return {
        "status": "ativo",
        "fonte": "esus2_centralizador",
        "municipios": int(df["cod_ibge"].nunique()) if "cod_ibge" in df.columns else int(len(df)),
        "municipios_com_atendimento_28d": int(
            (pd.to_numeric(df["atendimentos_28d"], errors="coerce").fillna(0) > 0).sum()
        )
        if "atendimentos_28d" in df.columns
        else 0,
        "data_max_atendimento": data_max,
        "data_janela_fim": janela_fim,
        "atraso_dias": atraso,
        "janela_ancorada": ancorada,
        "municipios_vermelho_roxo": int(len(crit)),
        "cadastros": _s("cadastros"),
        "asma": _s("asma"),
        "dpoc": _s("dpoc"),
        "idoso_60mais": _s("idoso_60mais"),
        "gestante": _s("gestante"),
        "acamado": _s("acamado"),
        "hipertensao": _s("hipertensao"),
        "diabetes": _s("diabetes"),
        "atendimentos_7d": _s("atendimentos_7d"),
        "atendimentos_28d": _s("atendimentos_28d"),
        "resp_cid_7d": _s("resp_cid_7d"),
        "resp_cid_28d": _s("resp_cid_28d"),
        "calor_cid_7d": _s("calor_cid_7d"),
        "dda_cid_7d": _s("dda_cid_7d"),
        "nebulizacao_7d": _s("nebulizacao_7d"),
        "nebulizacao_28d": _s("nebulizacao_28d"),
        "encaminhamento_urgencia_7d": _s("encaminhamento_urgencia_7d"),
        "por_classe": por_classe,
        "ranking_criticos": ranking,
        "municipais": municipais,
    }


def atualizar_esus_aps(*, ref: date | None = None, cruzar_araras: bool = True) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "ok": False,
        "n_atend": 0,
        "n_cadastro": 0,
        "erro": None,
    }
    if not use_esus_aps():
        meta["erro"] = "USE_ESUS_APS=false"
        return meta
    try:
        cfg = esus_aps_config()
    except ValueError as exc:
        meta["erro"] = str(exc)
        return meta
    if not credentials_ready(cfg):
        meta["erro"] = "ESUS_APS_USER / ESUS_APS_PASSWORD incompletos"
        return meta
    try:
        atend = fetch_atendimentos_municipio(ref=ref)
        cad = fetch_cadastro_municipio(ref=ref)
        meta["n_atend"] = persist_ops(atend, TABLE_ATEND, CSV_ATEND)
        meta["n_cadastro"] = persist_ops(cad, TABLE_CAD, CSV_CAD)
        if cruzar_araras:
            full = cruzar_esus_classe_araras(atend=atend, cad=cad, so_criticos=False)
            meta["n_municipal"] = persist_municipal(full)
            prio = full[full["classe_araras"].isin(NIVEIS_CRITICOS)].copy() if "classe_araras" in full.columns else full
            meta["n_prioridade"] = persist_prioridade(prio)
        meta["ok"] = True
        meta["data_referencia"] = (ref or date.today()).isoformat()
        if atend is not None and not atend.empty:
            if "data_max_atendimento" in atend.columns:
                meta["data_max_atendimento"] = str(atend["data_max_atendimento"].iloc[0] or "")
            if "atraso_dias" in atend.columns:
                meta["atraso_dias"] = int(pd.to_numeric(atend["atraso_dias"], errors="coerce").fillna(0).iloc[0])
            if "janela_ancorada" in atend.columns:
                meta["janela_ancorada"] = bool(atend["janela_ancorada"].iloc[0])
            if "data_janela_fim" in atend.columns:
                meta["data_janela_fim"] = str(atend["data_janela_fim"].iloc[0] or "")
    except Exception as exc:  # noqa: BLE001
        log.warning("Carga e-SUS APS falhou: %s", exc)
        meta["erro"] = str(exc)
    return meta
