"""Análise agregada e-SUS APS × clima / ARARAS (sem PII).

Correlações ecológicas municipais — não afirmam causalidade individual.
"""
from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table
from sisclima.core.logging_utils import get_logger
from sisclima.ingestion.esus_aps_clima import CSV_FULL, NIVEIS_CRITICOS

log = get_logger(__name__)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _spearman(x: pd.Series, y: pd.Series) -> dict[str, Any]:
    a = _num(x)
    b = _num(y)
    m = a.notna() & b.notna()
    n = int(m.sum())
    if n < 8:
        return {"n": n, "rho": None, "p": None, "motivo": f"pares válidos insuficientes (n={n}; mínimo 8)"}
    try:
        from scipy import stats

        if float(a[m].std(ddof=0) or 0) == 0 or float(b[m].std(ddof=0) or 0) == 0:
            return {"n": n, "rho": None, "p": None, "motivo": "variância nula em uma das séries"}
        rho, p = stats.spearmanr(a[m], b[m])
        if not np.isfinite(rho):
            return {"n": n, "rho": None, "p": None, "motivo": "resultado numérico inválido"}
        return {"n": n, "rho": float(rho), "p": float(p) if np.isfinite(p) else None, "motivo": None}
    except Exception as exc:  # noqa: BLE001
        log.debug("spearman falhou: %s", exc)
        return {"n": n, "rho": None, "p": None, "motivo": f"erro numérico ({exc})"}


def _load_esus_municipal() -> pd.DataFrame:
    try:
        df = read_table("ops_esus_aps_municipal")
        if df is not None and not df.empty:
            return df
    except Exception:  # noqa: BLE001
        pass
    if CSV_FULL.exists():
        return pd.read_csv(CSV_FULL)
    return pd.DataFrame()


def cruzar_esus_clima(resumo: pd.DataFrame | None = None) -> pd.DataFrame:
    esus = _load_esus_municipal()
    if esus.empty:
        return pd.DataFrame()
    if resumo is None or resumo.empty:
        try:
            resumo = read_table("resumo_municipal_atual")
        except Exception:  # noqa: BLE001
            resumo = pd.DataFrame()
    if resumo is None or resumo.empty:
        return esus
    esus = esus.copy()
    resumo = resumo.copy()
    esus["cod_ibge"] = esus["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    resumo["cod_ibge"] = resumo["cod_ibge"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(7)
    cols = [
        c
        for c in (
            "cod_ibge",
            "municipio",
            "nivel",
            "tmax",
            "umidade_media",
            "pm25_ugm3",
            "focos_queimadas_7d",
            "utci",
            "onda_calor_p95_2d",
            "ocupacao_pct",
            "score",
        )
        if c in resumo.columns
    ]
    return esus.merge(resumo[cols], on="cod_ibge", how="left", suffixes=("", "_araras"))


def analisar_esus_clima(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Indicadores e correlações para boletim / PPTX."""
    base = df if df is not None else cruzar_esus_clima()
    out: dict[str, Any] = {"ok": False, "n": 0}
    if base is None or base.empty:
        out["erro"] = "sem_esus_municipal"
        return out

    n = len(base)
    classe = base.get("classe_araras")
    if classe is None and "nivel" in base.columns:
        classe = base["nivel"]
    crit = classe.astype(str).str.lower().isin(NIVEIS_CRITICOS) if classe is not None else pd.Series([False] * n)

    def _sum(col: str) -> int | None:
        if col not in base.columns:
            return None
        s = _num(base[col])
        return int(s.fillna(0).sum()) if s.notna().any() else None

    def _mean_group(col: str, mask: pd.Series) -> float | None:
        if col not in base.columns:
            return None
        s = _num(base.loc[mask, col])
        return float(s.mean()) if s.notna().any() else None

    atraso = 0
    data_max = ""
    if "atraso_dias" in base.columns:
        atraso = int(_num(base["atraso_dias"]).fillna(0).max())
    if "data_max_atendimento" in base.columns:
        vals = base["data_max_atendimento"].dropna().astype(str).str.strip()
        vals = vals[vals != ""]
        data_max = str(vals.iloc[0]) if not vals.empty else ""

    corrs = {
        "atend_28d_x_tmax": _spearman(base.get("atendimentos_28d", pd.Series(dtype=float)), base.get("tmax", pd.Series(dtype=float))),
        "atend_28d_x_pm25": _spearman(base.get("atendimentos_28d", pd.Series(dtype=float)), base.get("pm25_ugm3", pd.Series(dtype=float))),
        "resp_cid_28d_x_pm25": _spearman(base.get("resp_cid_28d", pd.Series(dtype=float)), base.get("pm25_ugm3", pd.Series(dtype=float))),
        "asma_x_pm25": _spearman(base.get("asma", pd.Series(dtype=float)), base.get("pm25_ugm3", pd.Series(dtype=float))),
        "idoso_x_tmax": _spearman(base.get("idoso_60mais", pd.Series(dtype=float)), base.get("tmax", pd.Series(dtype=float))),
    }

    top_resp = []
    if "resp_cid_28d" in base.columns:
        s_resp = _num(base["resp_cid_28d"])
        # Só ordenar por CID quando há observação válida (>0); zeros de atraso não entram no top
        mask_ok = s_resp.notna() & (s_resp > 0)
        tmp = base.loc[mask_ok].nlargest(8, "resp_cid_28d", keep="all") if mask_ok.any() else base.head(0)
        for _, r in tmp.iterrows():
            top_resp.append(
                {
                    "municipio": r.get("municipio") or r.get("municipio_araras"),
                    "classe": r.get("classe_araras") or r.get("nivel"),
                    "resp_cid_28d": r.get("resp_cid_28d"),
                    "pm25": r.get("pm25_ugm3"),
                    "tmax": r.get("tmax"),
                    "atendimentos_28d": r.get("atendimentos_28d"),
                    "atend_ausente": pd.isna(r.get("atendimentos_28d")),
                }
            )

    out.update(
        {
            "ok": True,
            "n": n,
            "n_criticos": int(crit.sum()),
            "cadastros": _sum("cadastros") or _sum("cadastro_total"),
            "asma": _sum("asma"),
            "dpoc": _sum("dpoc"),
            "idoso_60mais": _sum("idoso_60mais"),
            "gestante": _sum("gestante"),
            "acamado": _sum("acamado"),
            "atendimentos_7d": _sum("atendimentos_7d"),
            "atendimentos_28d": _sum("atendimentos_28d"),
            "resp_cid_28d": _sum("resp_cid_28d"),
            "nebulizacao_28d": _sum("nebulizacao_28d"),
            "media_asma_criticos": _mean_group("asma", crit),
            "media_asma_outros": _mean_group("asma", ~crit),
            "media_idoso_criticos": _mean_group("idoso_60mais", crit),
            "media_idoso_outros": _mean_group("idoso_60mais", ~crit),
            "media_atend28_criticos": _mean_group("atendimentos_28d", crit),
            "media_atend28_outros": _mean_group("atendimentos_28d", ~crit),
            "media_tmax_criticos": _mean_group("tmax", crit),
            "media_pm25_criticos": _mean_group("pm25_ugm3", crit),
            "correlacoes": corrs,
            "top_resp_cid": top_resp,
            "atraso_dias": atraso,
            "data_max_atendimento": data_max,
            "status_temporal": "DEFASADO" if atraso >= 7 else ("ATUAL" if data_max else "INDISPONÍVEL"),
        }
    )
    return out


def _fmt_data_pt(val: Any) -> str:
    s = str(val or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        y, m, d = s[:10].split("-")
        return f"{d}/{m}/{y}"
    return s or "—"


def markdown_esus_clima(
    analise: dict[str, Any] | None = None,
    *,
    compact: bool = False,
) -> str:
    from sisclima.engines.boletim_el_nino.formatters import fmt_int, fmt_num, md_table

    a = analise or analisar_esus_clima()
    if not a.get("ok"):
        return (
            "\n### Análise e-SUS APS × clima\n\n"
            "Dados agregados da atenção primária indisponíveis nesta rodada "
            f"({a.get('erro') or 'sem cruzamento'}).\n"
        )

    data_max = _fmt_data_pt(a.get("data_max_atendimento") or "—")
    atraso = int(a.get("atraso_dias") or 0)
    selo = (
        f"> **DADO ASSISTENCIAL DEFASADO**  \n"
        f"> Última atualização: **{data_max}**  \n"
        f"> Não representa a situação corrente da semana epidemiológica em curso "
        f"(defasagem de **{fmt_int(atraso)}** dia(s))."
    )

    if compact:
        return "\n".join(
            [
                "",
                "### Atenção primária (e-SUS APS) — contexto",
                "",
                selo,
                "",
                f"Centralizador e-SUS APS: última carga válida **{data_max}**, "
                f"defasagem **{fmt_int(atraso)}** dias. "
                "Dados utilizados apenas como contexto de vulnerabilidade/cobertura, "
                "**não** como pressão assistencial atual.",
                "",
                f"- Cadastro (contexto): asma **{fmt_int(a.get('asma'))}** · idosos 60+ "
                f"**{fmt_int(a.get('idoso_60mais'))}** · gestantes **{fmt_int(a.get('gestante'))}** · "
                f"**{fmt_int(a.get('n_criticos'))}** municípios vermelho/roxo com cadastro.",
                "",
                "Tabelas detalhadas, correlações e top municípios: **anexo técnico / painel**.",
                "Ausência de envio ≠ zero clínico (municípios sem carga na janela: **N/D**).",
            ]
        )

    def _corr_txt(key: str, label: str) -> str:
        c = (a.get("correlacoes") or {}).get(key) or {}
        rho, p, n = c.get("rho"), c.get("p"), c.get("n")
        if rho is None:
            motivo = c.get("motivo") or f"não calculável (n válido={fmt_int(n)})"
            return f"- **{label}:** não calculada — motivo: {motivo}."
        sig = ""
        if p is not None and p < 0.05:
            sig = " · p<0,05"
        elif p is not None:
            sig = f" · p={fmt_num(p, 3)}"
        return f"- **{label}:** ρ = **{fmt_num(rho, 2)}**; n válido = {fmt_int(n)}{sig}."

    def _fmt_atend(v: Any, ausente: bool = False) -> str:
        if ausente or v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/D"
        return fmt_int(v)

    lines = [
        "",
        "### Análise e-SUS APS × clima e classes ARARAS (anexo)",
        "",
        selo,
        "",
        "Cruzamento ecológico municipal (cadastro/atendimentos da APS com Tmáx, PM2,5 e classe). "
        "**Não implica causalidade individual.** Data de referência dos atendimentos: "
        f"**{data_max}**.",
        "",
        f"- **Universo:** {fmt_int(a.get('n'))} municípios · "
        f"**{fmt_int(a.get('n_criticos'))}** em vermelho/roxo.",
        f"- **Cadastro:** asma **{fmt_int(a.get('asma'))}** · DPOC **{fmt_int(a.get('dpoc'))}** · "
        f"idosos 60+ **{fmt_int(a.get('idoso_60mais'))}** · gestantes **{fmt_int(a.get('gestante'))}** · "
        f"acamados **{fmt_int(a.get('acamado'))}**.",
        "",
        "**Correlações (Spearman):**",
        _corr_txt("atend_28d_x_tmax", "Atend. 28d × Tmáx"),
        _corr_txt("resp_cid_28d_x_pm25", "CID respiratório 28d × PM2,5"),
        _corr_txt("idoso_x_tmax", "Idosos 60+ × Tmáx"),
    ]
    rows = []
    for r in (a.get("top_resp_cid") or [])[:5]:
        rows.append(
            [
                str(r.get("municipio") or "—"),
                str(r.get("classe") or "—"),
                fmt_int(r.get("resp_cid_28d")),
                fmt_num(r.get("pm25"), 1),
                fmt_num(r.get("tmax"), 1),
                _fmt_atend(r.get("atendimentos_28d"), bool(r.get("atend_ausente"))),
            ]
        )
    if rows:
        lines.extend(
            [
                "",
                "**Top 5 – CID respiratório (28d) na APS**",
                "",
                f"_Data de referência dos atendimentos: {data_max}_",
                "",
                md_table(
                    ["Município", "Classe", "CID resp. 28d", "PM2,5", "Tmáx (°C)", "Atend. 28d"],
                    rows,
                ),
            ]
        )
    lines.extend(
        [
            "",
            "Fonte: Centralizador PEC/eSUS (agregado municipal) × ARARAS. "
            "Ausência de atendimento = **N/D** (não zero clínico).",
        ]
    )
    return "\n".join(lines)
