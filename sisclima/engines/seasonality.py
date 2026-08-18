# -*- coding: utf-8 -*-
"""Sazonalidade clima-saúde (agravos, ocupação e índices climáticos do ARARAS)."""
from __future__ import annotations

import numpy as np
import pandas as pd


MESES = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def _to_date(df: pd.DataFrame, col: str = "data") -> pd.DataFrame:
    out = df.copy()
    if col in out.columns:
        out[col] = pd.to_datetime(out[col], errors="coerce")
        out = out.dropna(subset=[col])
    return out


def _state_daily_from_inputs(
    met: pd.DataFrame,
    sivep: pd.DataFrame,
    arbo_mun: pd.DataFrame,
    pressao: pd.DataFrame,
    ocup_mun: pd.DataFrame,
) -> pd.DataFrame:
    # Base de datas pela meteorologia
    m = _to_date(met, "data")
    if m.empty:
        return pd.DataFrame()
    daily = m.groupby("data", as_index=False).agg(
        tmax=("tmax", "mean") if "tmax" in m.columns else ("data", "count"),
        utci_proxy=("utci_proxy", "mean") if "utci_proxy" in m.columns else ("data", "count"),
        risco_cumulativo_3d=("risco_cumulativo_3d", "mean") if "risco_cumulativo_3d" in m.columns else ("data", "count"),
        precipitacao_mm=("precipitacao_mm", "mean") if "precipitacao_mm" in m.columns else ("data", "count"),
        pm25_ugm3=("pm25_ugm3", "mean") if "pm25_ugm3" in m.columns else ("data", "count"),
    )
    for c in ["tmax", "utci_proxy", "risco_cumulativo_3d", "precipitacao_mm", "pm25_ugm3"]:
        if c in daily.columns:
            daily[c] = pd.to_numeric(daily[c], errors="coerce")

    sv = _to_date(sivep, "data")
    if not sv.empty:
        cols = [c for c in ["casos_srag", "obitos", "incidencia_srag_100k"] if c in sv.columns]
        if cols:
            for c in cols:
                sv[c] = pd.to_numeric(sv[c], errors="coerce")
            sv_state = sv.groupby("data", as_index=False)[cols].sum(min_count=1)
            daily = daily.merge(sv_state, on="data", how="left")

    ab = _to_date(arbo_mun, "data")
    if not ab.empty and "casos_arbovirus_7d" in ab.columns:
        ab["casos_arbovirus_7d"] = pd.to_numeric(ab["casos_arbovirus_7d"], errors="coerce")
        ab_state = ab.groupby("data", as_index=False)["casos_arbovirus_7d"].sum(min_count=1)
        daily = daily.merge(ab_state, on="data", how="left")

    pr = _to_date(pressao, "data")
    if not pr.empty and "pressao_calor_pct" in pr.columns:
        pr["pressao_calor_pct"] = pd.to_numeric(pr["pressao_calor_pct"], errors="coerce")
        pr_state = pr.groupby("data", as_index=False)["pressao_calor_pct"].mean()
        daily = daily.merge(pr_state, on="data", how="left")

    # Ocupação: usar série se houver data; senão snapshot vira constante no último dia
    oc = ocup_mun.copy() if ocup_mun is not None else pd.DataFrame()
    if not oc.empty and "ocupacao_pct" in oc.columns:
        oc = oc.rename(columns={"ocupacao_pct": "ocupacao_leitos_pct"})
    if not oc.empty and "ocupacao_leitos_pct" in oc.columns:
        if "data" in oc.columns:
            oc = _to_date(oc, "data")
            oc["ocupacao_leitos_pct"] = pd.to_numeric(oc["ocupacao_leitos_pct"], errors="coerce")
            oc_state = oc.groupby("data", as_index=False)["ocupacao_leitos_pct"].mean()
            daily = daily.merge(oc_state, on="data", how="left")
        elif "data_processamento" in oc.columns:
            tmp = oc.copy()
            tmp["data"] = pd.to_datetime(tmp["data_processamento"], errors="coerce").dt.normalize()
            tmp["ocupacao_leitos_pct"] = pd.to_numeric(tmp["ocupacao_leitos_pct"], errors="coerce")
            oc_state = tmp.groupby("data", as_index=False)["ocupacao_leitos_pct"].mean()
            daily = daily.merge(oc_state, on="data", how="left")

    daily = daily.sort_values("data").drop_duplicates("data")
    return daily


def _monthly_index(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    d = daily.copy()
    d["ano"] = d["data"].dt.year
    d["mes"] = d["data"].dt.month
    # principal: casos_srag; fallback pressão
    if "casos_srag" in d.columns and pd.to_numeric(d["casos_srag"], errors="coerce").notna().any():
        serie_col = "casos_srag"
    elif "casos_arbovirus_7d" in d.columns and pd.to_numeric(d["casos_arbovirus_7d"], errors="coerce").notna().any():
        serie_col = "casos_arbovirus_7d"
    else:
        serie_col = "pressao_calor_pct"
    d[serie_col] = pd.to_numeric(d[serie_col], errors="coerce")
    mensal = d.groupby(["ano", "mes"], as_index=False)[serie_col].mean()
    por_mes = mensal.groupby("mes", as_index=False).agg(media_valor=(serie_col, "mean"), mediana_valor=(serie_col, "median"))
    media_geral = float(pd.to_numeric(por_mes["media_valor"], errors="coerce").mean()) if not por_mes.empty else np.nan
    por_mes["indice_sazonal"] = por_mes["media_valor"] / media_geral if media_geral and not pd.isna(media_geral) else np.nan
    por_mes["acima_media"] = por_mes["indice_sazonal"] > 1.0
    por_mes["mes_rotulo"] = por_mes["mes"].map(MESES)
    por_mes["desfecho_base"] = serie_col
    return por_mes.sort_values("mes")


def _heatmap_week_year(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    d = daily.copy()
    iso = d["data"].dt.isocalendar()
    d["ano_epi"] = iso.year.astype(int)
    d["semana_epi"] = iso.week.astype(int)
    if "casos_srag" in d.columns and pd.to_numeric(d["casos_srag"], errors="coerce").notna().any():
        val = "casos_srag"
    elif "casos_arbovirus_7d" in d.columns and pd.to_numeric(d["casos_arbovirus_7d"], errors="coerce").notna().any():
        val = "casos_arbovirus_7d"
    else:
        val = "pressao_calor_pct"
    d[val] = pd.to_numeric(d[val], errors="coerce")
    return d.groupby(["ano_epi", "semana_epi"], as_index=False)[val].mean().rename(columns={val: "valor"})


def _week_profile(heat: pd.DataFrame) -> pd.DataFrame:
    if heat.empty:
        return pd.DataFrame()
    return heat.groupby("semana_epi", as_index=False).agg(
        media_valor=("valor", "mean"),
        mediana_valor=("valor", "median"),
        p75_valor=("valor", lambda s: float(np.nanpercentile(s, 75))),
        p95_valor=("valor", lambda s: float(np.nanpercentile(s, 95))),
    )


def _picos(mensal_idx: pd.DataFrame, heat: pd.DataFrame, perfil: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    if not mensal_idx.empty:
        top = mensal_idx.sort_values("indice_sazonal", ascending=False).head(3)
        low = mensal_idx.sort_values("indice_sazonal", ascending=True).head(3)
        for _, r in top.iterrows():
            rows.append({"tipo": "pico_mensal", "mes": int(r["mes"]), "mes_rotulo": r["mes_rotulo"], "indice": float(r["indice_sazonal"])})
        for _, r in low.iterrows():
            rows.append({"tipo": "baixa_mensal", "mes": int(r["mes"]), "mes_rotulo": r["mes_rotulo"], "indice": float(r["indice_sazonal"])})
    if not heat.empty and not perfil.empty:
        hoje = pd.Timestamp.today()
        se = int(hoje.isocalendar().week)
        ano = int(hoje.isocalendar().year)
        obs = heat[(heat["ano_epi"] == ano) & (heat["semana_epi"] == se)]["valor"]
        ref = perfil[perfil["semana_epi"] == se]["media_valor"]
        rows.append(
            {
                "tipo": "se_atual_vs_media",
                "semana_epi": se,
                "valor_atual": float(obs.iloc[0]) if not obs.empty else np.nan,
                "valor_medio_historico": float(ref.iloc[0]) if not ref.empty else np.nan,
            }
        )
    return pd.DataFrame(rows)


def _lag_correlations(daily: pd.DataFrame, max_lag: int = 14) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame()
    expos = [c for c in ["tmax", "utci_proxy", "risco_cumulativo_3d", "pm25_ugm3", "precipitacao_mm"] if c in daily.columns]
    desf = [c for c in ["casos_srag", "casos_arbovirus_7d", "ocupacao_leitos_pct", "pressao_calor_pct", "obitos"] if c in daily.columns]
    rows: list[dict] = []
    for exp in expos:
        for out in desf:
            for lag in range(0, max_lag + 1):
                tmp = daily[[exp, out]].copy()
                tmp[f"{exp}_lag"] = pd.to_numeric(tmp[exp], errors="coerce").shift(lag)
                tmp[out] = pd.to_numeric(tmp[out], errors="coerce")
                ok = tmp[f"{exp}_lag"].notna() & tmp[out].notna()
                n = int(ok.sum())
                if n < 30:
                    continue
                x = tmp.loc[ok, f"{exp}_lag"]
                y = tmp.loc[ok, out]
                pear = x.corr(y, method="pearson")
                # Spearman sem dependência de scipy: Pearson sobre ranks.
                xr = x.rank(method="average")
                yr = y.rank(method="average")
                spear = xr.corr(yr, method="pearson")
                rows.append(
                    {
                        "exposicao": exp,
                        "desfecho": out,
                        "lag_dias": lag,
                        "pearson": pear,
                        "spearman": spear,
                        "abs_spearman": abs(float(spear)) if pd.notna(spear) else np.nan,
                        "n_dias_validos": n,
                        "nota_tecnica": "Correlação ecológica temporal exploratória (não causal).",
                    }
                )
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values(["abs_spearman", "n_dias_validos"], ascending=[False, False])
    out["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    return out


def compute_seasonality_outputs(
    met_biometeo: pd.DataFrame,
    epi_sivep_srag: pd.DataFrame,
    epi_arboviroses_municipal: pd.DataFrame,
    epi_pressao_assistencial: pd.DataFrame,
    hospital_ocupacao_municipio: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    daily = _state_daily_from_inputs(
        met_biometeo,
        epi_sivep_srag,
        epi_arboviroses_municipal,
        epi_pressao_assistencial,
        hospital_ocupacao_municipio,
    )
    mensal_idx = _monthly_index(daily)
    heat = _heatmap_week_year(daily)
    perfil = _week_profile(heat)
    picos = _picos(mensal_idx, heat, perfil)
    lags = _lag_correlations(daily, max_lag=14)
    return {
        "sazonalidade_indice_mensal_v1": mensal_idx,
        "sazonalidade_heatmap_semana_ano_v1": heat,
        "sazonalidade_perfil_semana_epi_v1": perfil,
        "sazonalidade_picos_v1": picos,
        "clima_desfecho_lags_v1": lags,
    }

