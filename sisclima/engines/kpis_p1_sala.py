# -*- coding: utf-8 -*-
"""KPIs Prioridade 1 — SPI proxy, heat-days, Farrington epi, score fumaça.

Série operacional ARARAS (~5 anos em hist_clima). SPI aqui é proxy por z-score
do acumulado 30/90d vs mesmos períodos calendário — não substitui Monitor de Secas
oficial (ANA/INMET). Agregados apenas (LGPD).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table, table_exists
from sisclima.core.logging_utils import get_logger

log = get_logger(__name__)

_TMAX_LIMIAR = 37.0
_UTCI_LIMIAR = 38.0
_SPI_SECA = -1.0
_SPI_SECA_FORTE = -1.5
_MIN_ANOS = 2


def _norm_ibge(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.replace(r"\D", "", regex=True)
        .str.extract(r"(\d{6,7})", expand=False)
        .fillna("")
        .str.zfill(7)
    )


def _load_hist_clima() -> pd.DataFrame:
    if not table_exists("hist_clima_municipal_diario"):
        return pd.DataFrame()
    df = read_table("hist_clima_municipal_diario")
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    out["cod_ibge"] = _norm_ibge(out["cod_ibge"]) if "cod_ibge" in out.columns else ""
    out["data"] = pd.to_datetime(out["data"], errors="coerce").dt.normalize()
    out = out.dropna(subset=["cod_ibge", "data"])
    out = out[out["cod_ibge"].str.len() == 7]
    for c in ("tmax", "tmin", "utci_proxy", "precipitacao_mm", "pm25_ugm3"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    corte = pd.Timestamp(date.today() - timedelta(days=1))
    return out[out["data"] <= corte].sort_values(["cod_ibge", "data"])


# ---------------------------------------------------------------------------
# 1. SPI proxy (30d / 90d)
# ---------------------------------------------------------------------------


def _acum_rolling(hist: pd.DataFrame, dias: int) -> pd.DataFrame:
    if hist.empty or "precipitacao_mm" not in hist.columns:
        return pd.DataFrame()
    h = hist.copy()
    h["precipitacao_mm"] = pd.to_numeric(h["precipitacao_mm"], errors="coerce").fillna(0.0)
    h = h.sort_values(["cod_ibge", "data"])
    h["acum"] = (
        h.groupby("cod_ibge", group_keys=False)["precipitacao_mm"]
        .transform(lambda s: s.rolling(dias, min_periods=max(7, dias // 3)).sum())
    )
    h["_md"] = h["data"].dt.strftime("%m-%d")
    h["_ano"] = h["data"].dt.year
    return h


def compute_spi_proxy(*, dias: int = 30) -> dict[str, Any]:
    """SPI proxy municipal: z do acumulado N dias vs mesmos MM-DD em anos anteriores."""
    hist = _load_hist_clima()
    empty = {"ok": False, "dias": dias, "municipios": pd.DataFrame(), "kpi": {}}
    if hist.empty:
        return empty
    roll = _acum_rolling(hist, dias)
    if roll.empty or roll["acum"].notna().sum() < 100:
        return empty
    fim = roll["data"].max()
    md = fim.strftime("%m-%d")
    ano = int(fim.year)
    atual = roll[(roll["data"] == fim) & (roll["acum"].notna())].copy()
    if atual.empty:
        # último dia disponível por município
        idx = roll.dropna(subset=["acum"]).groupby("cod_ibge")["data"].idxmax()
        atual = roll.loc[idx].copy()
        fim = atual["data"].max()
        md = fim.strftime("%m-%d")
        ano = int(fim.year)

    hist_md = roll[(roll["_md"] == md) & (roll["_ano"] != ano) & roll["acum"].notna()]
    if hist_md.empty:
        return empty

    ref = hist_md.groupby("cod_ibge")["acum"].agg(["mean", "std", "count"]).reset_index()
    ref.columns = ["cod_ibge", "media_hist", "sd_hist", "n_anos"]
    m = atual.merge(ref, on="cod_ibge", how="left")
    m["sd_hist"] = m["sd_hist"].replace(0, np.nan)
    m["spi_proxy"] = (m["acum"] - m["media_hist"]) / m["sd_hist"]
    # sem sd: usar desvio relativo
    mask = m["spi_proxy"].isna() & m["media_hist"].notna() & (m["media_hist"].abs() > 1e-6)
    m.loc[mask, "spi_proxy"] = (m.loc[mask, "acum"] - m.loc[mask, "media_hist"]) / m.loc[mask, "media_hist"]
    m["classe_seca"] = np.where(
        m["spi_proxy"] <= _SPI_SECA_FORTE,
        "seca_forte",
        np.where(m["spi_proxy"] <= _SPI_SECA, "seca", "normal_ou_umido"),
    )
    n = max(int(m["spi_proxy"].notna().sum()), 1)
    n_seca = int((m["spi_proxy"] <= _SPI_SECA).sum())
    n_forte = int((m["spi_proxy"] <= _SPI_SECA_FORTE).sum())
    return {
        "ok": True,
        "dias": dias,
        "data_ref": str(pd.Timestamp(fim).date()),
        "md": md,
        "municipios": m[
            ["cod_ibge", "acum", "media_hist", "spi_proxy", "classe_seca", "n_anos"]
        ].copy(),
        "kpi": {
            "n_municipios": n,
            "pct_spi_le_menos1": round(100.0 * n_seca / n, 1),
            "pct_spi_le_menos15": round(100.0 * n_forte / n, 1),
            "n_seca": n_seca,
            "n_seca_forte": n_forte,
            "spi_mediana": float(m["spi_proxy"].median()) if m["spi_proxy"].notna().any() else None,
        },
    }


# ---------------------------------------------------------------------------
# 2. Heat-days YTD
# ---------------------------------------------------------------------------


def compute_heat_days_ytd(
    *,
    tmax_limiar: float = _TMAX_LIMIAR,
    utci_limiar: float = _UTCI_LIMIAR,
) -> dict[str, Any]:
    hist = _load_hist_clima()
    empty = {"ok": False, "municipios": pd.DataFrame(), "kpi": {}}
    if hist.empty or "tmax" not in hist.columns:
        return empty
    fim = hist["data"].max()
    ano = int(fim.year)
    ini_ytd = pd.Timestamp(year=ano, month=1, day=1)

    def _flag(df: pd.DataFrame) -> pd.Series:
        tmax = pd.to_numeric(df.get("tmax"), errors="coerce")
        utci = pd.to_numeric(df.get("utci_proxy"), errors="coerce") if "utci_proxy" in df.columns else pd.Series(np.nan, index=df.index)
        return (tmax >= tmax_limiar) | (utci >= utci_limiar)

    atual = hist[(hist["data"] >= ini_ytd) & (hist["data"] <= fim)].copy()
    atual["heat_day"] = _flag(atual)
    mun_atual = atual.groupby("cod_ibge", as_index=False)["heat_day"].sum().rename(columns={"heat_day": "dias_calor_ytd"})

    # histórico: mesmo YTD (1 jan → MM-DD) em anos anteriores
    rows = []
    for a in sorted(hist["data"].dt.year.dropna().unique()):
        a = int(a)
        if a >= ano:
            continue
        try:
            fim_a = pd.Timestamp(year=a, month=fim.month, day=fim.day)
        except ValueError:
            fim_a = pd.Timestamp(year=a, month=fim.month, day=28)
        chunk = hist[(hist["data"] >= pd.Timestamp(year=a, month=1, day=1)) & (hist["data"] <= fim_a)].copy()
        if chunk.empty:
            continue
        chunk["heat_day"] = _flag(chunk)
        g = chunk.groupby("cod_ibge")["heat_day"].sum()
        for cod, v in g.items():
            rows.append({"cod_ibge": cod, "ano": a, "dias": float(v)})
    hist_y = pd.DataFrame(rows)
    if not hist_y.empty:
        ref = hist_y.groupby("cod_ibge")["dias"].mean().rename("dias_hist_medio").reset_index()
        mun_atual = mun_atual.merge(ref, on="cod_ibge", how="left")
        mun_atual["delta"] = mun_atual["dias_calor_ytd"] - mun_atual["dias_hist_medio"]
    else:
        mun_atual["dias_hist_medio"] = np.nan
        mun_atual["delta"] = np.nan

    n = max(len(mun_atual), 1)
    media_atual = float(mun_atual["dias_calor_ytd"].mean())
    media_hist = float(mun_atual["dias_hist_medio"].mean()) if mun_atual["dias_hist_medio"].notna().any() else None
    n_acima = int((mun_atual["delta"] > 0).sum()) if "delta" in mun_atual.columns else 0
    # % mun com ≥15 dias de calor extremo no YTD
    n15 = int((mun_atual["dias_calor_ytd"] >= 15).sum())
    return {
        "ok": True,
        "data_ref": str(fim.date()),
        "ini_ytd": str(ini_ytd.date()),
        "tmax_limiar": tmax_limiar,
        "utci_limiar": utci_limiar,
        "municipios": mun_atual,
        "kpi": {
            "media_dias_calor_ytd": round(media_atual, 1),
            "media_dias_hist_ytd": None if media_hist is None else round(media_hist, 1),
            "delta_media": None if media_hist is None else round(media_atual - media_hist, 1),
            "pct_mun_acima_hist": round(100.0 * n_acima / n, 1),
            "pct_mun_ge_15d": round(100.0 * n15 / n, 1),
            "n_municipios": n,
        },
    }


# ---------------------------------------------------------------------------
# 3. Farrington-like excess (SRAG / dengue)
# ---------------------------------------------------------------------------


def _weekly_counts_from_table(table: str, date_col: str, value_col: str | None = None) -> pd.DataFrame:
    if not table_exists(table):
        return pd.DataFrame()
    df = read_table(table)
    if df is None or df.empty or date_col not in df.columns:
        return pd.DataFrame()
    out = df.copy()
    if "cod_ibge" in out.columns:
        out["cod_ibge"] = _norm_ibge(out["cod_ibge"])
    else:
        return pd.DataFrame()
    out["data"] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=["data", "cod_ibge"])
    out = out[out["cod_ibge"].str.len() == 7]
    iso = out["data"].dt.isocalendar()
    out["ano_epi"] = iso.year.astype(int)
    out["semana_epi"] = iso.week.astype(int)
    if value_col and value_col in out.columns:
        out["_v"] = pd.to_numeric(out[value_col], errors="coerce").fillna(1.0)
        g = out.groupby(["cod_ibge", "ano_epi", "semana_epi"], as_index=False)["_v"].sum()
        g = g.rename(columns={"_v": "casos"})
    else:
        g = out.groupby(["cod_ibge", "ano_epi", "semana_epi"], as_index=False).size()
        g = g.rename(columns={"size": "casos"})
    return g


def compute_farrington_excess(*, agravo: str = "srag") -> dict[str, Any]:
    """Excesso epidemiológico simplificado (média±2dp da mesma SE em anos anteriores)."""
    empty = {"ok": False, "agravo": agravo, "municipios": pd.DataFrame(), "kpi": {}}
    weekly = pd.DataFrame()
    if agravo == "srag":
        if table_exists("hist_saude_municipal_diario"):
            weekly = _weekly_counts_from_table("hist_saude_municipal_diario", "data", "casos_srag")
        if weekly.empty and table_exists("epi_sivep_srag"):
            weekly = _weekly_counts_from_table("epi_sivep_srag", "data", "casos_srag")
    else:
        if table_exists("hist_saude_municipal_diario"):
            weekly = _weekly_counts_from_table("hist_saude_municipal_diario", "data", "casos_dengue")
        if weekly.empty:
            for t in ("epi_sinan_dengue", "sinan_dengue", "epi_arbovirus"):
                if not table_exists(t):
                    continue
                raw = read_table(t)
                if raw is None or raw.empty:
                    continue
                for dc in ("data", "DT_NOTIFIC", "data_noticias", "data_sintomas"):
                    if dc in raw.columns:
                        weekly = _weekly_counts_from_table(t, dc)
                        if not weekly.empty:
                            break
                if not weekly.empty:
                    break

    if weekly.empty:
        empty["motivo"] = "serie_semanal_vazia"
        return empty

    # semana de referência = última com dados
    weekly = weekly.sort_values(["ano_epi", "semana_epi"])
    last = weekly.iloc[-1]
    ano = int(last["ano_epi"])
    se = int(last["semana_epi"])
    atual = weekly[(weekly["ano_epi"] == ano) & (weekly["semana_epi"] == se)].copy()
    hist = weekly[(weekly["semana_epi"] == se) & (weekly["ano_epi"] != ano)]

    # Fallback série curta: baseline = mesmas SE±2 em anos disponíveis OU
    # média das 8 semanas anteriores no mesmo município (mesmo ano)
    modo = "mesma_se_anos"
    if hist.empty or hist["ano_epi"].nunique() < _MIN_ANOS:
        # janela SE-8 .. SE-1 no mesmo ano
        se_prev = list(range(max(1, se - 8), se))
        hist = weekly[(weekly["ano_epi"] == ano) & (weekly["semana_epi"].isin(se_prev))]
        modo = "baseline_8se_mesmo_ano"
    if hist.empty or atual.empty:
        # último recurso: z-score já persistido no snapshot SIVEP
        if agravo == "srag" and table_exists("epi_sivep_srag"):
            snap = read_table("epi_sivep_srag")
            if snap is not None and not snap.empty and "zscore_srag" in snap.columns:
                s = snap.copy()
                s["cod_ibge"] = _norm_ibge(s["cod_ibge"]) if "cod_ibge" in s.columns else ""
                s["z"] = pd.to_numeric(s["zscore_srag"], errors="coerce")
                s["casos"] = pd.to_numeric(s.get("casos_srag"), errors="coerce")
                s["excesso"] = s["z"] >= 1.96
                s["alerta_2se"] = False
                n = max(int(s["z"].notna().sum()), 1)
                n_alerta = int(s["excesso"].fillna(False).sum())
                return {
                    "ok": True,
                    "agravo": agravo,
                    "ano_epi": None,
                    "semana_epi": None,
                    "modo": "zscore_snapshot_sivep",
                    "municipios": s,
                    "kpi": {
                        "n_municipios_com_dado": n,
                        "n_acima_limiar_95": n_alerta,
                        "pct_acima_limiar_95": round(100.0 * n_alerta / n, 1),
                        "n_alerta_2_semanas": 0,
                        "casos_semana_total": int(pd.to_numeric(s["casos"], errors="coerce").fillna(0).sum()),
                    },
                }
        empty["motivo"] = "sem_historico_mesma_se"
        return empty

    ref = hist.groupby("cod_ibge")["casos"].agg(["mean", "std", "count"]).reset_index()
    ref.columns = ["cod_ibge", "esperado", "sd", "n_anos"]
    m = atual.merge(ref, on="cod_ibge", how="left")
    m["sd"] = m["sd"].fillna(0).replace(0, np.nan)
    # limiar superior ~ Farrington simplificado: média + 1.96*sd (mín. Poisson)
    m["limiar_sup"] = m["esperado"] + 1.96 * m["sd"].fillna(np.sqrt(m["esperado"].clip(lower=0.5)))
    m["excesso"] = m["casos"] > m["limiar_sup"]
    m["z"] = (m["casos"] - m["esperado"]) / m["sd"]
    m.loc[m["sd"].isna() | (m["sd"] < 1e-9), "z"] = np.nan

    n = max(len(m), 1)
    n_alerta = int(m["excesso"].fillna(False).sum())
    # semanas consecutivas: SE atual e SE-1 (apenas no modo multi-ano)
    m["alerta_2se"] = False
    if modo == "mesma_se_anos":
        se_ant = se - 1 if se > 1 else 52
        ano_ant = ano if se > 1 else ano - 1
        ant = weekly[(weekly["ano_epi"] == ano_ant) & (weekly["semana_epi"] == se_ant)]
        if not ant.empty:
            ref2 = weekly[(weekly["semana_epi"] == se_ant) & (weekly["ano_epi"] != ano_ant)]
            if not ref2.empty:
                r2 = ref2.groupby("cod_ibge")["casos"].agg(["mean", "std"]).reset_index()
                r2.columns = ["cod_ibge", "esperado2", "sd2"]
                ant2 = ant.merge(r2, on="cod_ibge", how="left")
                ant2["limiar2"] = ant2["esperado2"] + 1.96 * ant2["sd2"].fillna(
                    np.sqrt(ant2["esperado2"].clip(lower=0.5))
                )
                ant2["excesso2"] = ant2["casos"] > ant2["limiar2"]
                m = m.merge(ant2[["cod_ibge", "excesso2"]], on="cod_ibge", how="left")
                m["alerta_2se"] = m["excesso"].fillna(False) & m["excesso2"].fillna(False)

    n_2se = int(m["alerta_2se"].fillna(False).sum())
    return {
        "ok": True,
        "agravo": agravo,
        "ano_epi": ano,
        "semana_epi": se,
        "modo": modo,
        "municipios": m,
        "kpi": {
            "n_municipios_com_dado": n,
            "n_acima_limiar_95": n_alerta,
            "pct_acima_limiar_95": round(100.0 * n_alerta / n, 1),
            "n_alerta_2_semanas": n_2se,
            "casos_semana_total": int(m["casos"].sum()),
        },
    }


# ---------------------------------------------------------------------------
# 4. Score exposição fumaça
# ---------------------------------------------------------------------------


def enrich_exposicao_fumaca(resumo: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta exposicao_fumaca_0_100 e reutiliza gap_fumaca_nebulizacao."""
    if resumo is None or resumo.empty:
        return resumo
    out = resumo.copy()
    pm = pd.to_numeric(out["pm25_ugm3"], errors="coerce") if "pm25_ugm3" in out.columns else pd.Series(np.nan, index=out.index)
    # PM score: 0 em 0 µg/m³, 50 em 25, 100 em ≥75
    pm_score = ((pm.fillna(0) / 75.0) * 100.0).clip(0, 100)

    focos = pd.Series(0.0, index=out.index, dtype=float)
    for c in ("focos_queimadas_7d", "focos_7d", "focos_queimadas_24h", "focos_24h"):
        if c in out.columns:
            focos = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
            break
    # focos: 0→0, 5→50, ≥20→100
    focos_score = ((focos / 20.0) * 100.0).clip(0, 100)

    out["exposicao_fumaca_0_100"] = (0.65 * pm_score + 0.35 * focos_score).round(1)
    # gap: já pode existir; se não, recalcular leve
    if "gap_fumaca_nebulizacao" not in out.columns:
        if "equipamentos_nebulizacao" in out.columns:
            neb = pd.to_numeric(out["equipamentos_nebulizacao"], errors="coerce")
        else:
            neb = pd.Series(np.nan, index=out.index)
        sinal = (out["exposicao_fumaca_0_100"] >= 40) | (pm.fillna(0) >= 25) | (focos.fillna(0) > 0)
        out["gap_fumaca_nebulizacao"] = (sinal & neb.notna() & (neb <= 0)).astype(int)
    return out


def compute_fumaca_kpi(resumo: pd.DataFrame | None = None) -> dict[str, Any]:
    if resumo is None or (isinstance(resumo, pd.DataFrame) and resumo.empty):
        if table_exists("resumo_municipal_atual"):
            resumo = read_table("resumo_municipal_atual")
        else:
            resumo = pd.DataFrame()
    if resumo is None or resumo.empty:
        return {"ok": False, "kpi": {}}
    out = enrich_exposicao_fumaca(resumo)
    n = max(len(out), 1)
    exp = pd.to_numeric(out["exposicao_fumaca_0_100"], errors="coerce")
    n_alto = int((exp >= 50).sum())
    gap = pd.to_numeric(out.get("gap_fumaca_nebulizacao"), errors="coerce").fillna(0)
    n_gap = int(gap.sum())
    # prioritários = exposição alta
    pri = out[exp >= 50]
    n_pri = max(len(pri), 1)
    gap_pri = int(pd.to_numeric(pri.get("gap_fumaca_nebulizacao"), errors="coerce").fillna(0).sum()) if not pri.empty else 0
    return {
        "ok": True,
        "municipios": out[["cod_ibge", "exposicao_fumaca_0_100"]].copy()
        if "cod_ibge" in out.columns
        else out,
        "kpi": {
            "exposicao_mediana": float(exp.median()) if exp.notna().any() else None,
            "pct_mun_exposicao_ge_50": round(100.0 * n_alto / n, 1),
            "n_mun_exposicao_ge_50": n_alto,
            "n_gap_nebulizacao": n_gap,
            "pct_prioritarios_com_gap": round(100.0 * gap_pri / n_pri, 1) if n_alto else 0.0,
            "n_municipios": n,
        },
    }


# ---------------------------------------------------------------------------
# Pacote boletim
# ---------------------------------------------------------------------------


def resumo_kpis_p1_boletim(resumo: pd.DataFrame | None = None) -> dict[str, Any]:
    """Markdown + KPIs estaduais para o boletim / painel."""
    spi1 = compute_spi_proxy(dias=30)
    spi3 = compute_spi_proxy(dias=90)
    heat = compute_heat_days_ytd()
    srag = compute_farrington_excess(agravo="srag")
    dengue = compute_farrington_excess(agravo="dengue")
    fum = compute_fumaca_kpi(resumo)

    linhas: list[str] = [
        "**KPIs da sala (Prioridade 1) — estiagem, calor acumulado, excesso epi, fumaça**",
        "",
        "_SPI proxy = z-score do acumulado 30/90 dias vs mesmos dias do calendário na série operacional "
        "(~5 anos). Não substitui Monitor de Secas / INMET. Farrington simplificado = casos da SE "
        "acima de média+1,96·dp da mesma SE em anos anteriores._",
        "",
    ]

    if spi1.get("ok"):
        k = spi1["kpi"]
        med = k.get("spi_mediana")
        med_txt = f"; mediana SPI {med:.2f}" if med is not None else ""
        linhas.append(
            f"- **Estiagem (SPI proxy 30d, ref. {spi1.get('data_ref')}):** "
            f"{k.get('pct_spi_le_menos1')}% municípios com SPI≤−1,0 "
            f"({k.get('n_seca')} mun.); SPI≤−1,5: {k.get('pct_spi_le_menos15')}% "
            f"({k.get('n_seca_forte')} mun.){med_txt}."
        )
    else:
        linhas.append("- **Estiagem (SPI proxy 30d):** indisponível (série hist insuficiente).")

    if spi3.get("ok"):
        k = spi3["kpi"]
        linhas.append(
            f"- **Estiagem (SPI proxy 90d):** {k.get('pct_spi_le_menos1')}% com SPI≤−1,0 "
            f"({k.get('n_seca')} mun.); SPI≤−1,5: {k.get('pct_spi_le_menos15')}%."
        )

    if heat.get("ok"):
        k = heat["kpi"]
        hist_txt = (
            f" vs média histórica YTD {k.get('media_dias_hist_ytd')} dias (Δ {k.get('delta_media'):+.1f})"
            if k.get("media_dias_hist_ytd") is not None
            else ""
        )
        linhas.append(
            f"- **Dias de calor extremo YTD** (Tmáx≥{heat.get('tmax_limiar')} °C ou UTCI≥{heat.get('utci_limiar')}): "
            f"média municipal {k.get('media_dias_calor_ytd')} dias{hist_txt}; "
            f"{k.get('pct_mun_ge_15d')}% dos municípios com ≥15 dias; "
            f"{k.get('pct_mun_acima_hist')}% acima do próprio histórico YTD."
        )
    else:
        linhas.append("- **Dias de calor extremo YTD:** indisponível.")

    for pack, nome in ((srag, "SRAG"), (dengue, "Dengue")):
        if pack.get("ok"):
            k = pack["kpi"]
            se_txt = (
                f"SE {pack.get('semana_epi')}/{pack.get('ano_epi')}"
                if pack.get("semana_epi")
                else "snapshot"
            )
            modo = pack.get("modo") or ""
            modo_txt = f" [{modo}]" if modo else ""
            linhas.append(
                f"- **Excesso epidemiológico {nome}** ({se_txt}{modo_txt}): "
                f"{k.get('n_acima_limiar_95')} municípios acima do limiar 95% "
                f"({k.get('pct_acima_limiar_95')}%); "
                f"{k.get('n_alerta_2_semanas')} em alerta por 2 semanas; "
                f"casos: {k.get('casos_semana_total')}."
            )
        else:
            linhas.append(
                f"- **Excesso epidemiológico {nome}:** indisponível"
                + (f" ({pack.get('motivo')})" if pack.get("motivo") else "")
                + "."
            )

    if fum.get("ok"):
        k = fum["kpi"]
        med = k.get("exposicao_mediana")
        med_txt = f"{med:.1f}" if med is not None else "—"
        linhas.append(
            f"- **Exposição à fumaça (0–100):** mediana {med_txt}; "
            f"{k.get('pct_mun_exposicao_ge_50')}% municípios com score ≥50 "
            f"({k.get('n_mun_exposicao_ge_50')} mun.); "
            f"gap nebulização nos prioritários: {k.get('pct_prioritarios_com_gap')}%."
        )
    else:
        linhas.append("- **Exposição à fumaça:** indisponível (resumo municipal vazio).")

    ok = any(
        [
            spi1.get("ok"),
            spi3.get("ok"),
            heat.get("ok"),
            srag.get("ok"),
            dengue.get("ok"),
            fum.get("ok"),
        ]
    )
    return {
        "ok": ok,
        "spi_30d": spi1,
        "spi_90d": spi3,
        "heat_days": heat,
        "farrington_srag": srag,
        "farrington_dengue": dengue,
        "fumaca": fum,
        "markdown": "\n".join(linhas),
    }
