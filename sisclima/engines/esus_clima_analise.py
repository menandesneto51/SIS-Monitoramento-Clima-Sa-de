"""Análise agregada e-SUS APS × clima / ARARAS (sem PII).

Correlações ecológicas municipais — não afirmam causalidade individual.
"""
from __future__ import annotations

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
        return {"n": n, "rho": None, "p": None}
    try:
        from scipy import stats

        rho, p = stats.spearmanr(a[m], b[m])
        if not np.isfinite(rho):
            return {"n": n, "rho": None, "p": None}
        return {"n": n, "rho": float(rho), "p": float(p) if np.isfinite(p) else None}
    except Exception as exc:  # noqa: BLE001
        log.debug("spearman falhou: %s", exc)
        return {"n": n, "rho": None, "p": None}


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

    corrs = {
        "atend_28d_x_tmax": _spearman(base.get("atendimentos_28d", pd.Series(dtype=float)), base.get("tmax", pd.Series(dtype=float))),
        "atend_28d_x_pm25": _spearman(base.get("atendimentos_28d", pd.Series(dtype=float)), base.get("pm25_ugm3", pd.Series(dtype=float))),
        "resp_cid_28d_x_pm25": _spearman(base.get("resp_cid_28d", pd.Series(dtype=float)), base.get("pm25_ugm3", pd.Series(dtype=float))),
        "asma_x_pm25": _spearman(base.get("asma", pd.Series(dtype=float)), base.get("pm25_ugm3", pd.Series(dtype=float))),
        "idoso_x_tmax": _spearman(base.get("idoso_60mais", pd.Series(dtype=float)), base.get("tmax", pd.Series(dtype=float))),
    }

    top_resp = []
    if "resp_cid_28d" in base.columns:
        tmp = base.nlargest(8, "resp_cid_28d", keep="all") if _num(base["resp_cid_28d"]).fillna(0).sum() > 0 else base.head(0)
        for _, r in tmp.iterrows():
            top_resp.append(
                {
                    "municipio": r.get("municipio") or r.get("municipio_araras"),
                    "classe": r.get("classe_araras") or r.get("nivel"),
                    "resp_cid_28d": r.get("resp_cid_28d"),
                    "pm25": r.get("pm25_ugm3"),
                    "tmax": r.get("tmax"),
                    "atendimentos_28d": r.get("atendimentos_28d"),
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
        }
    )
    return out


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

    def _corr_txt(key: str, label: str) -> str:
        c = (a.get("correlacoes") or {}).get(key) or {}
        rho, p, n = c.get("rho"), c.get("p"), c.get("n")
        if rho is None:
            return f"- **{label}:** insuficiente (n={fmt_int(n)})."
        sig = ""
        if p is not None and p < 0.05:
            sig = " (p<0,05)"
        elif p is not None:
            sig = f" (p={fmt_num(p, 3)})"
        return f"- **{label}:** ρ de Spearman = **{fmt_num(rho, 2)}** · n={fmt_int(n)}{sig}."

    lines = [
        "",
        "### Análise e-SUS APS × clima e classes ARARAS",
        "",
        "Cruzamento ecológico municipal (cadastro/atendimentos da APS com Tmáx, PM2,5 e classe). "
        "**Não implica causalidade individual.**",
        "",
        f"- **Universo:** {fmt_int(a.get('n'))} municípios · "
        f"**{fmt_int(a.get('n_criticos'))}** em vermelho/roxo.",
        f"- **Cadastro:** asma **{fmt_int(a.get('asma'))}** · DPOC **{fmt_int(a.get('dpoc'))}** · "
        f"idosos 60+ **{fmt_int(a.get('idoso_60mais'))}** · gestantes **{fmt_int(a.get('gestante'))}** · "
        f"acamados **{fmt_int(a.get('acamado'))}**.",
        f"- **Atendimentos:** 7d **{fmt_int(a.get('atendimentos_7d'))}** · 28d **{fmt_int(a.get('atendimentos_28d'))}** · "
        f"CID respiratório 28d **{fmt_int(a.get('resp_cid_28d'))}**.",
        f"- **Críticos vs demais (médias):** idosos {fmt_num(a.get('media_idoso_criticos'), 0)} vs "
        f"{fmt_num(a.get('media_idoso_outros'), 0)} · atend. 28d {fmt_num(a.get('media_atend28_criticos'), 0)} vs "
        f"{fmt_num(a.get('media_atend28_outros'), 0)} · Tmáx **{fmt_num(a.get('media_tmax_criticos'), 1, ' °C')}** · "
        f"PM2,5 **{fmt_num(a.get('media_pm25_criticos'), 1, ' µg/m³')}**.",
        "",
        "**Correlações (Spearman):**",
        _corr_txt("atend_28d_x_tmax", "Atend. 28d × Tmáx"),
        _corr_txt("resp_cid_28d_x_pm25", "CID respiratório 28d × PM2,5"),
        _corr_txt("idoso_x_tmax", "Idosos 60+ × Tmáx"),
    ]
    if not compact:
        rows = []
        for r in (a.get("top_resp_cid") or [])[:5]:
            rows.append(
                [
                    str(r.get("municipio") or "—"),
                    str(r.get("classe") or "—"),
                    fmt_int(r.get("resp_cid_28d")),
                    fmt_num(r.get("pm25"), 1),
                    fmt_num(r.get("tmax"), 1),
                ]
            )
        if rows:
            lines.extend(
                [
                    "",
                    "**Top 5 – CID respiratório (28d) na APS**",
                    "",
                    md_table(
                        ["Município", "Classe", "CID resp. 28d", "PM2,5", "Tmáx (°C)"],
                        rows,
                    ),
                ]
            )
    lines.extend(
        [
            "",
            "Fonte: Centralizador PEC/eSUS (agregado municipal) × ARARAS. "
            "Ausência de atendimento não é zero clínico. Detalhamento no painel operacional.",
        ]
    )
    return "\n".join(lines)
