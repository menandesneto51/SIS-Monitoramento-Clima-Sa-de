# -*- coding: utf-8 -*-
"""
Enriquecimento operacional do SIS Clima-Saúde MT.

Completa o resumo municipal e tabelas de inteligência quando fontes
assistenciais (IndicaSUS) ou scripts V6–V8 estão ausentes:

- população / incidência
- arboviroses (cod_ibge 7 dígitos)
- qualidade do ar (último PM2.5)
- ANA / nível chuva
- pressão assistencial PROXY (clima + saúde)
- correlações Spearman persistidas
- predição operacional 7 dias (a partir de met_biometeo)
- alerta inteligente municipal
- alertas estatísticos clima-saúde
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.config import SETTINGS
from sisclima.core.db import read_table, write_df
from sisclima.core.logging_utils import get_logger
from sisclima.engines.correlation_stats import compute_spearman_pairs
from sisclima.engines.cnes_ops import build_ops_cnes_municipio
from sisclima.engines.hidro_risco import compute_hidro_risco_from_ana
from sisclima.engines.alerta_integrado import build_alerta_integrado_municipal
from sisclima.engines.odds_ratio import compute_climate_health_ors
from sisclima.engines.resilience import resilience_index
from sisclima.engines.seasonality import compute_seasonality_outputs
from sisclima.engines.soil_saturation import enrich_soil_saturation, municipal_soil_snapshot
from sisclima.engines.stages import STAGE_ORDER, classify_stage

log = get_logger(__name__)

LEVEL_ORDER = ["cinza", "verde", "amarela", "laranja", "vermelha", "roxa"]


def _norm_ibge(s: pd.Series) -> pd.Series:
    return s.astype(str).str.extract(r"(\d{7})", expand=False)


def _pad_ibge6_to7(s: pd.Series) -> pd.Series:
    """Tenta normalizar códigos IBGE de 6 ou 7 dígitos para 7."""
    raw = s.astype(str).str.replace(r"\D", "", regex=True)
    out = raw.str.extract(r"(\d{7})", expand=False)
    # MT: muitos exports vêm com 6 dígitos (sem DV) — completa com lookup se possível
    six = raw.where(raw.str.len() == 6)
    return out.fillna(six)  # pode ficar 6; merge usará also fuzzy via left 6


def _ibge_keys(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "cod_ibge" not in out.columns:
        return out
    out["cod_ibge"] = out["cod_ibge"].astype(str).str.replace(r"\D", "", regex=True)
    out["cod_ibge7"] = out["cod_ibge"].str.extract(r"(\d{7})", expand=False)
    out["cod_ibge6"] = out["cod_ibge"].str.extract(r"(\d{6})", expand=False)
    # Prefer 7; se só 6, usa 6
    out["cod_ibge"] = out["cod_ibge7"].fillna(out["cod_ibge6"])
    return out


def _window_sum_by_ibge(df: pd.DataFrame, value_cols: list[str], days: int = 14) -> pd.DataFrame:
    """Agrega últimos N dias por município relativos à data máxima da série."""
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return pd.DataFrame()
    out = _ibge_keys(df)
    if "data" in out.columns:
        out["data"] = pd.to_datetime(out["data"], errors="coerce")
        max_dt = out["data"].max()
        if pd.notna(max_dt):
            cutoff = max_dt.normalize() - pd.Timedelta(days=days)
            out = out[out["data"] >= cutoff]
    for c in value_cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    present = [c for c in value_cols if c in out.columns]
    if not present:
        return pd.DataFrame()
    return out.groupby("cod_ibge", as_index=False)[present].sum(min_count=1)


def _latest_by_ibge(df: pd.DataFrame, value_cols: list[str]) -> pd.DataFrame:
    if df is None or df.empty or "cod_ibge" not in df.columns:
        return pd.DataFrame()
    out = _ibge_keys(df)
    if "data" in out.columns:
        out["data"] = pd.to_datetime(out["data"], errors="coerce")
        out = out.sort_values("data").groupby("cod_ibge", as_index=False).tail(1)
    else:
        out = out.drop_duplicates("cod_ibge", keep="last")
    keep = ["cod_ibge"] + [c for c in value_cols if c in out.columns]
    if "municipio" in out.columns:
        keep.append("municipio")
    return out[keep].copy()


def _clip01(x: pd.Series) -> pd.Series:
    return pd.to_numeric(x, errors="coerce").clip(lower=0, upper=1)


def compute_pressao_proxy(resumo: pd.DataFrame) -> pd.DataFrame:
    """
    Pressão assistencial proxy 0–15% a partir de calor + SRAG + arbovírus + ar.
    Alinhada aos limiares de settings (amarela 2 … roxa 10).
    """
    df = resumo.copy()
    clima = np.zeros(len(df))
    saude = np.zeros(len(df))

    if "risco_cumulativo_3d" in df.columns:
        clima = clima + _clip01(pd.to_numeric(df["risco_cumulativo_3d"], errors="coerce") / 12.0).fillna(0) * 0.45
    if "utci_proxy" in df.columns:
        clima = clima + _clip01((pd.to_numeric(df["utci_proxy"], errors="coerce") - 26) / 16.0).fillna(0) * 0.35
    if "tmax" in df.columns:
        clima = clima + _clip01((pd.to_numeric(df["tmax"], errors="coerce") - 32) / 12.0).fillna(0) * 0.20

    if "zscore_srag" in df.columns:
        saude = saude + _clip01(pd.to_numeric(df["zscore_srag"], errors="coerce") / 3.0).fillna(0) * 0.35
    if "incidencia_srag_100k" in df.columns:
        saude = saude + _clip01(pd.to_numeric(df["incidencia_srag_100k"], errors="coerce") / 40.0).fillna(0) * 0.25
    if "casos_arbovirus_7d" in df.columns:
        saude = saude + _clip01(pd.to_numeric(df["casos_arbovirus_7d"], errors="coerce") / 30.0).fillna(0) * 0.20
    if "zscore_arbovirus" in df.columns:
        saude = saude + _clip01(pd.to_numeric(df["zscore_arbovirus"], errors="coerce") / 3.0).fillna(0) * 0.10
    if "pm25_ugm3" in df.columns:
        saude = saude + _clip01(pd.to_numeric(df["pm25_ugm3"], errors="coerce") / 75.0).fillna(0) * 0.10

    # Escala operacional ~0–15 (limiar roxa = 10)
    pressao = (0.55 * clima + 0.45 * saude) * 15.0
    pressao = pd.Series(pressao, index=df.index).clip(0, 15).round(2)

    out = pd.DataFrame(
        {
            "cod_ibge": df["cod_ibge"] if "cod_ibge" in df.columns else None,
            "municipio": df["municipio"] if "municipio" in df.columns else None,
            "data": pd.Timestamp.today().date().isoformat(),
            "pressao_calor_pct": pressao,
            "fonte_pressao": "PROXY_CLIMA_SAUDE",
            "atendimentos_total": np.nan,
            "atendimentos_calor": np.nan,
            "zscore_pressao": 0.0,
            "ewma_pressao": pressao,
            "cusum_pressao": 0.0,
        }
    )
    return out


def enrich_resumo_columns(resumo: pd.DataFrame) -> pd.DataFrame:
    """Preenche gaps do resumo com tabelas satélite."""
    if resumo is None or resumo.empty:
        return resumo if resumo is not None else pd.DataFrame()

    out = _ibge_keys(resumo)
    out["cod_ibge"] = out["cod_ibge"].astype(str)

    # Restaura nome do município a partir de colunas satélite
    for cand in ["municipio", "municipio_met", "municipio_x", "municipio_shape", "municipio_base"]:
        if cand in out.columns:
            if "municipio" not in out.columns:
                out["municipio"] = out[cand]
            else:
                out["municipio"] = out["municipio"].fillna(out[cand])

    # População / regional / demografia IBGE a partir da vulnerabilidade
    vuln = read_table("geo_vulnerabilidade_municipal")
    if vuln.empty:
        try:
            from sisclima.ingestion.ibge_vulnerabilidade import load_vulnerabilidade_municipal
            from sisclima.engines.resilience import vulnerability_index

            demo = load_vulnerabilidade_municipal()
            if not demo.empty:
                vuln = vulnerability_index(demo)
                write_df(vuln, "geo_vulnerabilidade_municipal")
        except Exception:
            vuln = pd.DataFrame()
    if not vuln.empty:
        v = vuln.copy()
        v = _ibge_keys(v)
        if "populacao_x" in v.columns and "populacao" not in v.columns:
            v["populacao"] = pd.to_numeric(v["populacao_x"], errors="coerce")
        elif "populacao_y" in v.columns:
            v["populacao"] = pd.to_numeric(v.get("populacao", v["populacao_y"]), errors="coerce")
        if "populacao" not in v.columns and "populacao_censo_2022" in v.columns:
            v["populacao"] = pd.to_numeric(v["populacao_censo_2022"], errors="coerce")
        if "municipio_x" in v.columns:
            v["municipio_geo"] = v["municipio_x"]
        keep = [
            c for c in [
                "cod_ibge", "populacao", "indice_vulnerabilidade_calor", "cobertura_vulnerabilidade_pct",
                "regional_saude", "municipio_geo", "lat", "lon",
                "idosos_pct", "criancas_0_4_pct", "criancas_0_9_pct", "rural_pct", "densidade",
                "area_km2", "idosos_60mais", "criancas_0_4", "fonte_vulnerabilidade",
            ]
            if c in v.columns
        ]
        v = v[keep].drop_duplicates("cod_ibge")
        # Campos demográficos: sempre atualizam quando o índice legado está flat (=50)
        force_demo = [
            "idosos_pct", "criancas_0_4_pct", "criancas_0_9_pct", "rural_pct", "densidade",
            "area_km2", "idosos_60mais", "criancas_0_4", "fonte_vulnerabilidade",
            "cobertura_vulnerabilidade_pct",
        ]
        flat_vuln = (
            "indice_vulnerabilidade_calor" in out.columns
            and pd.to_numeric(out["indice_vulnerabilidade_calor"], errors="coerce").nunique(dropna=True) <= 1
        )
        if flat_vuln and "indice_vulnerabilidade_calor" in v.columns:
            force_demo.append("indice_vulnerabilidade_calor")
        overlap = [c for c in keep if c != "cod_ibge" and c in out.columns and c not in force_demo]
        v_merge = v.drop(columns=overlap, errors="ignore") if overlap else v
        for need in ["populacao", "regional_saude", "indice_vulnerabilidade_calor", "municipio_geo"] + force_demo:
            if need in v.columns and need not in v_merge.columns:
                if need not in out.columns or out[need].isna().all() or need in force_demo:
                    v_merge = v_merge.merge(v[["cod_ibge", need]].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        # drop force cols from out before merge to avoid _x/_y
        drop_force = [c for c in force_demo if c in out.columns and c in v_merge.columns]
        if drop_force:
            out = out.drop(columns=drop_force, errors="ignore")
        if "cod_ibge" in v_merge.columns and len(v_merge.columns) > 1:
            out = out.merge(v_merge.drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        if "municipio_geo" in out.columns:
            out["municipio"] = out.get("municipio", pd.Series(dtype=str))
            out["municipio"] = out["municipio"].fillna(out["municipio_geo"])
        if "populacao" in out.columns:
            out["populacao"] = pd.to_numeric(out["populacao"], errors="coerce")
        elif "populacao" in v.columns:
            out = out.merge(v[["cod_ibge", "populacao"]].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
        if "regional_saude" not in out.columns or out["regional_saude"].isna().all():
            if "regional_saude" in v.columns:
                rs = v[["cod_ibge", "regional_saude"]].drop_duplicates("cod_ibge")
                out = out.drop(columns=["regional_saude"], errors="ignore").merge(rs, on="cod_ibge", how="left")
        if "indice_vulnerabilidade_calor" not in out.columns or out["indice_vulnerabilidade_calor"].isna().all():
            if "indice_vulnerabilidade_calor" in v.columns:
                iv = v[["cod_ibge", "indice_vulnerabilidade_calor"]].drop_duplicates("cod_ibge")
                out = out.drop(columns=["indice_vulnerabilidade_calor"], errors="ignore").merge(iv, on="cod_ibge", how="left")

    # SIVEP — janela 14d + último zscore/vírus
    sivep = read_table("epi_sivep_srag")
    if not sivep.empty:
        s_sum = _window_sum_by_ibge(sivep, ["casos_srag", "uti", "obitos", "suporte_ventilatorio"], days=14)
        s_last = _latest_by_ibge(
            sivep,
            [
                "letalidade_pct", "prop_uti_pct", "incidencia_srag_100k", "zscore_srag",
                "virus_dominante", "populacao", "positividade_viral_pct", "cobertura_lab_pct",
            ],
        )
        s = s_sum
        if not s_last.empty:
            s = s.merge(s_last, on="cod_ibge", how="outer") if not s.empty else s_last
        if not s.empty:
            s = _ibge_keys(s)
            s["cod_ibge6"] = s["cod_ibge"].astype(str).str[:6]
            tmp = out[["cod_ibge"]].copy()
            tmp["cod_ibge6"] = tmp["cod_ibge"].astype(str).str[:6]
            sm = s.drop(columns=["cod_ibge"], errors="ignore")
            tmp = tmp.merge(sm, on="cod_ibge6", how="left")
            for col in [
                "casos_srag", "uti", "obitos", "letalidade_pct", "prop_uti_pct",
                "incidencia_srag_100k", "zscore_srag", "virus_dominante",
                "positividade_viral_pct", "cobertura_lab_pct",
            ]:
                if col not in tmp.columns:
                    continue
                if col == "virus_dominante":
                    if col not in out.columns:
                        out[col] = tmp[col]
                    else:
                        out[col] = tmp[col].combine_first(out[col])
                else:
                    new = pd.to_numeric(tmp[col], errors="coerce")
                    if col not in out.columns:
                        out[col] = new
                    else:
                        cur = pd.to_numeric(out[col], errors="coerce")
                        # prioriza valor enriquecido (não deixa 0 do pipeline bloquear fillna)
                        out[col] = new.combine_first(cur)
                        if col in ("casos_srag", "uti", "obitos"):
                            out.loc[new.notna(), col] = new[new.notna()]
            if "casos_srag" in out.columns:
                pop = pd.to_numeric(out.get("populacao"), errors="coerce")
                casos = pd.to_numeric(out["casos_srag"], errors="coerce")
                if "incidencia_srag_100k" not in out.columns:
                    out["incidencia_srag_100k"] = np.nan
                need = pop.notna() & (pop > 0) & casos.notna()
                out.loc[need, "incidencia_srag_100k"] = casos[need] / pop[need] * 100_000

    # Arboviroses — match por 7 ou 6 dígitos
    arbo = read_table("epi_arboviroses_municipal")
    if not arbo.empty:
        a = _ibge_keys(arbo)
        cols = [
            "casos_arbovirus_7d", "casos_dengue_7d", "casos_zika_7d", "casos_chikungunya_7d",
            "casos_outras_arbovirus_7d", "zscore_arbovirus", "incidencia_arbovirus_100k",
            "alerta_arbovirus", "agravo_dominante",
        ]
        a = a[["cod_ibge"] + [c for c in cols if c in a.columns]].drop_duplicates("cod_ibge")
        # Join direto
        out6 = out["cod_ibge"].astype(str).str[:6]
        a6 = a["cod_ibge"].astype(str).str[:6]
        a = a.copy()
        a["cod_ibge6"] = a6
        tmp = out[["cod_ibge"]].copy()
        tmp["cod_ibge6"] = out6
        tmp = tmp.merge(a.drop(columns=["cod_ibge"], errors="ignore"), on="cod_ibge6", how="left")
        for col in cols:
            if col not in a.columns:
                continue
            if col not in out.columns:
                out[col] = tmp[col]
            elif col == "agravo_dominante":
                out[col] = tmp[col].combine_first(out[col])
            else:
                new = pd.to_numeric(tmp[col], errors="coerce")
                cur = pd.to_numeric(out[col], errors="coerce")
                out[col] = new.combine_first(cur)
                if col.startswith("casos_"):
                    out.loc[new.notna(), col] = new[new.notna()]
        # incidência arbovírus com população
        if "casos_arbovirus_7d" in out.columns:
            pop = pd.to_numeric(out.get("populacao"), errors="coerce")
            casos = pd.to_numeric(out["casos_arbovirus_7d"], errors="coerce")
            if "incidencia_arbovirus_100k" not in out.columns:
                out["incidencia_arbovirus_100k"] = np.nan
            need = out["incidencia_arbovirus_100k"].isna() & pop.notna() & (pop > 0) & casos.notna()
            out.loc[need, "incidencia_arbovirus_100k"] = casos[need] / pop[need] * 100_000

    # Qualidade do ar latest
    aq = read_table("qualidade_ar_municipal")
    if not aq.empty:
        q = _latest_by_ibge(aq, ["pm25_ugm3", "pm10_ugm3", "o3_ugm3", "no2_ugm3", "iq_ar_score", "qualidade_ar_nivel", "poluente_dominante"])
        if not q.empty:
            for col in q.columns:
                if col == "cod_ibge":
                    continue
                if col not in out.columns:
                    out = out.merge(q[["cod_ibge", col]], on="cod_ibge", how="left")
                else:
                    m = out[["cod_ibge"]].merge(q[["cod_ibge", col]], on="cod_ibge", how="left")
                    if col in ("qualidade_ar_nivel", "poluente_dominante"):
                        out[col] = out[col].fillna(m[col])
                    else:
                        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(pd.to_numeric(m[col], errors="coerce"))

    # ANA risco
    ana = read_table("ana_risco_municipal")
    if not ana.empty:
        an = _latest_by_ibge(ana, ["chuva_mm", "cota_cm", "vazao_m3s", "nivel_chuva", "precipitacao_mm"])
        if not an.empty:
            an = an.rename(columns={"chuva_mm": "chuva_mm_ana", "precipitacao_mm": "precipitacao_mm_ana"})
            for col in an.columns:
                if col == "cod_ibge":
                    continue
                if col not in out.columns:
                    out = out.merge(an[["cod_ibge", col]], on="cod_ibge", how="left")
                else:
                    m = out[["cod_ibge"]].merge(an[["cod_ibge", col]], on="cod_ibge", how="left")
                    if col == "nivel_chuva":
                        out[col] = out[col].fillna(m[col])
                    else:
                        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(pd.to_numeric(m[col], errors="coerce"))

    # Ocupação (município ou estado)
    occ = read_table("hospital_ocupacao_municipio")
    if not occ.empty and "cod_ibge" in occ.columns:
        o = occ.copy()
        o = _ibge_keys(o)
        rename = {"ocupacao_pct": "ocupacao_leitos_pct", "leitos_existentes": "leitos_total", "fonte": "fonte_ocupacao"}
        o = o.rename(columns={k: v for k, v in rename.items() if k in o.columns})
        keep = [c for c in ["cod_ibge", "ocupacao_leitos_pct", "leitos_total", "leitos_ocupados", "leitos_livres", "fonte_ocupacao"] if c in o.columns]
        o = o[keep].drop_duplicates("cod_ibge")
        for col in keep:
            if col == "cod_ibge":
                continue
            if col not in out.columns:
                out = out.merge(o[["cod_ibge", col]], on="cod_ibge", how="left")
            else:
                m = out[["cod_ibge"]].merge(o[["cod_ibge", col]], on="cod_ibge", how="left")
                out[col] = pd.to_numeric(out[col], errors="coerce").fillna(pd.to_numeric(m[col], errors="coerce")) if col != "fonte_ocupacao" else out[col].fillna(m[col])

    estado = read_table("hospital_ocupacao_estado")
    if not estado.empty and "ocupacao_pct" in estado.columns:
        valor = pd.to_numeric(estado["ocupacao_pct"], errors="coerce").dropna()
        if not valor.empty:
            if "ocupacao_leitos_pct" not in out.columns:
                out["ocupacao_leitos_pct"] = np.nan
            out["ocupacao_leitos_pct"] = pd.to_numeric(out["ocupacao_leitos_pct"], errors="coerce").fillna(float(valor.iloc[0]))
            if "fonte_ocupacao" not in out.columns:
                out["fonte_ocupacao"] = pd.NA
            out["fonte_ocupacao"] = out["fonte_ocupacao"].fillna("INDICASUS_ESTADUAL_FALLBACK")

    # Pressão proxy se ausente
    needs_press = "pressao_calor_pct" not in out.columns or pd.to_numeric(out["pressao_calor_pct"], errors="coerce").isna().all()
    if needs_press:
        press = compute_pressao_proxy(out)
        write_df(press, "epi_pressao_assistencial")
        out["pressao_calor_pct"] = press["pressao_calor_pct"].values
        out["fonte_pressao"] = "PROXY_CLIMA_SAUDE"
    elif "fonte_pressao" not in out.columns:
        out["fonte_pressao"] = "pipeline"

    # Limpeza auxiliar + nome municipal definitivo
    for cand in ["municipio_met", "municipio_geo", "municipio_shape", "municipio_base", "municipio_arbo"]:
        if cand in out.columns:
            if "municipio" not in out.columns:
                out["municipio"] = out[cand]
            else:
                out["municipio"] = out["municipio"].fillna(out[cand])
    drop_aux = [c for c in out.columns if c.endswith("_vuln") or c in ("cod_ibge7", "cod_ibge6", "municipio_geo")]
    out = out.drop(columns=drop_aux, errors="ignore")
    return out


def reclassify_resumo(resumo: pd.DataFrame) -> pd.DataFrame:
    """Reaplica classify_stage linha a linha com SETTINGS atuais."""
    if resumo is None or resumo.empty:
        return resumo
    out = resumo.copy()
    niveis, scores, motivos, flags_roxo = [], [], [], []
    for _, row in out.iterrows():
        try:
            result = classify_stage(row.to_dict(), SETTINGS)
            niveis.append(result.nivel)
            scores.append(int(result.score))
            motivos.append("; ".join(result.motivos[:8]) if result.motivos else str(row.get("motivo", "")))
            flags_roxo.append(int((result.indicadores or {}).get("flag_persistencia_roxa") or 0))
        except Exception as exc:
            log.debug("Falha classify_stage: %s", exc)
            niveis.append(str(row.get("nivel", "cinza")))
            scores.append(int(STAGE_ORDER.get(str(row.get("nivel", "cinza")), 0)))
            motivos.append(str(row.get("motivo", "")))
            flags_roxo.append(int(row.get("flag_persistencia_roxa") or 0))
    out["nivel"] = niveis
    out["score"] = scores
    out["motivo"] = motivos
    out["flag_persistencia_roxa"] = flags_roxo
    out["data_referencia"] = pd.Timestamp.today().date().isoformat()
    return out


def build_predicao_7d(met: pd.DataFrame, resumo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Predição operacional 7d a partir da série met (inclui forecast Open-Meteo se houver)."""
    if met is None or met.empty:
        return pd.DataFrame(), pd.DataFrame()
    m = _ibge_keys(met)
    m["data"] = pd.to_datetime(m["data"], errors="coerce")
    today = pd.Timestamp.today().normalize()
    fut = m[m["data"] >= today].copy()
    if fut.empty:
        fut = m[m["data"] >= (today - pd.Timedelta(days=7))].copy()
        fonte = "persistencia_7d_observado"
    else:
        fut = fut[fut["data"] <= today + pd.Timedelta(days=7)].copy()
        fonte = (
            "openmeteo_forecast_7d"
            if ("fonte" in m.columns and m["fonte"].astype(str).str.contains("openmeteo", case=False, na=False).any())
            else "met_forward_7d"
        )

    if fut.empty or "cod_ibge" not in fut.columns:
        return pd.DataFrame(), pd.DataFrame()

    for c in ["tmax", "utci_proxy", "risco_cumulativo_3d", "onda_calor_p95_2d"]:
        if c in fut.columns:
            fut[c] = pd.to_numeric(fut[c], errors="coerce")

    rows = []
    for cod, grp in fut.groupby("cod_ibge"):
        rows.append(
            {
                "cod_ibge": str(cod),
                "tmax_max_7d": pd.to_numeric(grp["tmax"], errors="coerce").max() if "tmax" in grp else np.nan,
                "utci_proxy_max_7d": pd.to_numeric(grp["utci_proxy"], errors="coerce").max() if "utci_proxy" in grp else np.nan,
                "risco_cumulativo_3d_max_7d": pd.to_numeric(grp["risco_cumulativo_3d"], errors="coerce").max() if "risco_cumulativo_3d" in grp else np.nan,
                "dias_onda_calor_prevista_7d": float(pd.to_numeric(grp["onda_calor_p95_2d"], errors="coerce").fillna(0).sum()) if "onda_calor_p95_2d" in grp else 0.0,
            }
        )
    agg = pd.DataFrame(rows)

    def _nivel_pred(row) -> str:
        score = 0
        if pd.notna(row.get("risco_cumulativo_3d_max_7d")):
            r = float(row["risco_cumulativo_3d_max_7d"])
            if r >= 18:
                score = max(score, 4)
            elif r >= 12:
                score = max(score, 3)
            elif r >= 7:
                score = max(score, 2)
            elif r >= 3:
                score = max(score, 1)
        if pd.notna(row.get("utci_proxy_max_7d")):
            u = float(row["utci_proxy_max_7d"])
            if u >= 44:
                score = max(score, 4)
            elif u >= 40:
                score = max(score, 3)
            elif u >= 36:
                score = max(score, 2)
            elif u >= 32:
                score = max(score, 1)
        if pd.notna(row.get("tmax_max_7d")):
            t = float(row["tmax_max_7d"])
            if t >= 40:
                score = max(score, 3)
            elif t >= 37:
                score = max(score, 2)
            elif t >= 34:
                score = max(score, 1)
        return LEVEL_ORDER[min(score + 1, 5)]

    agg["nivel_predicao_7d"] = agg.apply(_nivel_pred, axis=1)
    agg["risco_preditivo_score"] = agg["nivel_predicao_7d"].map(STAGE_ORDER).fillna(0).astype(int)
    agg["fonte_predicao"] = fonte

    if not resumo.empty and "municipio" in resumo.columns:
        mun_cols = ["cod_ibge", "municipio"] + (["regional_saude"] if "regional_saude" in resumo.columns else [])
        mun = resumo[mun_cols].drop_duplicates("cod_ibge")
        mun["cod_ibge"] = mun["cod_ibge"].astype(str)
        agg["cod_ibge"] = agg["cod_ibge"].astype(str)
        agg = agg.merge(mun, on="cod_ibge", how="left")

    if "regional_saude" in agg.columns:
        reg = (
            agg.groupby("regional_saude", as_index=False)
            .agg(
                municipios=("cod_ibge", "nunique"),
                risco_preditivo_score=("risco_preditivo_score", "max"),
            )
        )
        reg["nivel_predicao_7d"] = reg["risco_preditivo_score"].map(
            lambda s: LEVEL_ORDER[min(int(s) + 1, 5)] if pd.notna(s) else "verde"
        )
    else:
        reg = pd.DataFrame()
    return agg, reg


def build_alerta_inteligente(resumo: pd.DataFrame, pred: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if resumo is None or resumo.empty:
        return pd.DataFrame(), pd.DataFrame()
    am = resumo.copy()
    am["cod_ibge"] = am["cod_ibge"].astype(str)
    if not pred.empty:
        p = pred[["cod_ibge", "nivel_predicao_7d", "risco_preditivo_score"]].drop_duplicates("cod_ibge")
        p["cod_ibge"] = p["cod_ibge"].astype(str)
        am = am.merge(p, on="cod_ibge", how="left", suffixes=("", "_pred"))

    def _score_row(row) -> tuple[int, str]:
        score = int(STAGE_ORDER.get(str(row.get("nivel", "verde")).lower(), 0))
        extras = 0
        for col, thr in [("zscore_srag", 2.0), ("zscore_arbovirus", 2.0), ("pressao_calor_pct", 4.0), ("pm25_ugm3", 35.0), ("indice_saturacao_solo", 70.0)]:
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v) and float(v) >= thr:
                extras += 1
        for key in ("nivel_inmet", "nivel_cemaden", "nivel_alerta_hidro", "nivel_alerta_integrado"):
            niv = row.get(key)
            if isinstance(niv, str) and niv.lower() in ("laranja", "vermelha", "roxa"):
                extras += 1
                break
        pred_raw = pd.to_numeric(row.get("risco_preditivo_score"), errors="coerce")
        pred_s = int(pred_raw) if pd.notna(pred_raw) else 0
        score = max(score, pred_s)
        score = min(score + (1 if extras >= 2 else 0), 4)
        return score, LEVEL_ORDER[min(score + 1, 5)]

    scores, niveis = [], []
    for _, row in am.iterrows():
        s, n = _score_row(row)
        scores.append(s)
        niveis.append(n)
    am["alerta_inteligente_score"] = scores
    am["alerta_inteligente_nivel"] = niveis
    am["recomendacao_operacional"] = am["alerta_inteligente_nivel"].map(
        {
            "verde": "Monitoramento de rotina",
            "amarela": "Atenção — reforçar vigilância climática e SRAG",
            "laranja": "Alerta — articular regional e assistência",
            "vermelha": "Resposta intensificada — sala de situação",
            "roxa": "Situação excepcional — mobilização plena CIEVS",
            "cinza": "Dados insuficientes — priorizar coleta",
        }
    )
    keep = [
        c for c in [
            "cod_ibge", "municipio", "regional_saude", "nivel", "score",
            "alerta_inteligente_nivel", "alerta_inteligente_score",
            "risco_cumulativo_3d", "utci_proxy", "tmax", "pressao_calor_pct",
            "ocupacao_leitos_pct", "pm25_ugm3", "casos_srag", "casos_arbovirus_7d",
            "recomendacao_operacional", "nivel_predicao_7d", "risco_preditivo_score",
        ]
        if c in am.columns
    ]
    am = am[keep]
    if "regional_saude" in am.columns:
        reg = (
            am.groupby("regional_saude", as_index=False)
            .agg(
                municipios=("cod_ibge", "nunique"),
                alerta_inteligente_score=("alerta_inteligente_score", "max"),
            )
        )
        reg["alerta_inteligente_nivel"] = reg["alerta_inteligente_score"].map(
            lambda s: LEVEL_ORDER[min(int(s) + 1, 5)] if pd.notna(s) else "verde"
        )
    else:
        reg = pd.DataFrame()
    return am, reg


def build_alertas_estatisticos(resumo: pd.DataFrame, corr: pd.DataFrame) -> pd.DataFrame:
    if resumo is None or resumo.empty:
        return pd.DataFrame()
    top_pairs = corr.head(8) if corr is not None and not corr.empty else pd.DataFrame()
    rows = []
    for _, row in resumo.iterrows():
        score = 0
        motivos = []
        for col, thr, w in [
            ("risco_cumulativo_3d", 7, 2),
            ("utci_proxy", 36, 1),
            ("zscore_srag", 2, 2),
            ("casos_arbovirus_7d", 10, 1),
            ("pressao_calor_pct", 4, 1),
            ("pm25_ugm3", 35, 1),
            ("indice_saturacao_solo", 70, 1),
        ]:
            v = pd.to_numeric(row.get(col), errors="coerce")
            if pd.notna(v) and float(v) >= thr:
                score += w
                motivos.append(f"{col}>={thr}")
        if not top_pairs.empty:
            for _, p in top_pairs.iterrows():
                exp, des = p.get("exposicao"), p.get("desfecho")
                if exp in resumo.columns and des in row.index:
                    ev = pd.to_numeric(row.get(exp), errors="coerce")
                    dv = pd.to_numeric(row.get(des), errors="coerce")
                    if pd.notna(ev) and pd.notna(dv) and float(p.get("abs_rho", 0) or 0) >= 0.35:
                        # ambos acima do percentil 75 aproximado via valor relativo simples
                        if float(ev) > 0 and float(dv) > 0:
                            score += 1
                            motivos.append(f"par {exp}->{des}")
                            break
        nivel = LEVEL_ORDER[min(score + 1, 5)] if score > 0 else "verde"
        if score >= 6:
            nivel = "roxa"
        elif score >= 4:
            nivel = "vermelha"
        elif score >= 3:
            nivel = "laranja"
        elif score >= 2:
            nivel = "amarela"
        rows.append(
            {
                "cod_ibge": row.get("cod_ibge"),
                "municipio": row.get("municipio"),
                "regional_saude": row.get("regional_saude"),
                "nivel": row.get("nivel"),
                "score_alerta_estatistico": score,
                "nivel_alerta_estatistico": nivel,
                "motivo_estatistico": "; ".join(motivos[:6]),
                "risco_cumulativo_3d": row.get("risco_cumulativo_3d"),
                "utci_proxy": row.get("utci_proxy"),
                "tmax": row.get("tmax"),
                "pm25_ugm3": row.get("pm25_ugm3"),
                "ocupacao_leitos_pct": row.get("ocupacao_leitos_pct"),
                "pressao_calor_pct": row.get("pressao_calor_pct"),
            }
        )
    return pd.DataFrame(rows)


def run_operational_enrichment(reclassify: bool = True) -> dict[str, Any]:
    """Executa enriquecimento completo e persiste tabelas."""
    resumo = read_table("resumo_municipal_atual")
    if resumo.empty:
        raise RuntimeError("resumo_municipal_atual vazio — rode o pipeline antes.")

    log.info("Enriquecendo resumo municipal (%s linhas)...", len(resumo))
    resumo = enrich_resumo_columns(resumo)
    if reclassify:
        resumo = reclassify_resumo(resumo)

    write_df(resumo, "resumo_municipal_atual")

    # Base analítica preliminar (sem índices compostos ainda)
    base_cols = [
        c for c in [
            "cod_ibge", "municipio", "regional_saude", "populacao", "nivel", "score",
            "tmax", "tmedia", "utci_proxy", "heat_index", "risco_cumulativo_3d",
            "pm25_ugm3", "iq_ar_score", "precipitacao_mm", "nivel_chuva",
            "casos_srag", "incidencia_srag_100k", "zscore_srag",
            "casos_arbovirus_7d", "incidencia_arbovirus_100k", "zscore_arbovirus",
            "ocupacao_leitos_pct", "pressao_calor_pct", "indice_vulnerabilidade_calor",
        ]
        if c in resumo.columns
    ]
    write_df(resumo[base_cols], "analise_clima_saude_base_municipal_v8")

    # CNES / resiliência operacional
    ops_cnes_mun, ops_cnes_resumo = build_ops_cnes_municipio(resumo)
    if not ops_cnes_mun.empty:
        write_df(ops_cnes_mun, "ops_cnes_municipio")
    if not ops_cnes_resumo.empty:
        write_df(ops_cnes_resumo, "ops_resumo_operacional_cnes")
        inj = ops_cnes_resumo[
            [c for c in ["cod_ibge", "indice_capacidade_cnes", "cnes_leitos_total", "cnes_leitos_per_10k", "cnes_estabelecimentos_total"] if c in ops_cnes_resumo.columns]
        ].drop_duplicates("cod_ibge")
        inj["cod_ibge"] = inj["cod_ibge"].astype(str)
        resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
        for col in inj.columns:
            if col == "cod_ibge":
                continue
            if col in resumo.columns:
                resumo = resumo.drop(columns=[col])
        resumo = resumo.merge(inj, on="cod_ibge", how="left")
        pesos = SETTINGS.get("pesos_resiliencia", {}) if isinstance(SETTINGS, dict) else {}
        default_pesos = {
            "capacidade_leitos": 0.25, "estoque": 0.20, "infraestrutura": 0.20,
            "busca_ativa": 0.20, "comunicacao": 0.15,
        }
        new_resil = []
        for _, row in resumo.iterrows():
            try:
                new_resil.append(resilience_index(row.to_dict(), pesos or default_pesos))
            except Exception:
                new_resil.append({})
        if new_resil:
            rdf = pd.DataFrame(new_resil)
            for col in rdf.columns:
                resumo[col] = rdf[col].values
        write_df(resumo, "resumo_municipal_atual")

    corr = compute_spearman_pairs(resumo, min_n=12)
    write_df(corr, "analise_clima_saude_correlacoes_v8")
    odds = compute_climate_health_ors(resumo)
    write_df(odds, "analise_clima_saude_odds_ratio_v1")

    alertas_estat = build_alertas_estatisticos(resumo, corr)
    write_df(alertas_estat, "analise_clima_saude_alertas_estatisticos_v8")

    met = read_table("met_biometeo")
    # Solo: se met não tem umidade, tenta Open-Meteo (API oficial)
    if met.empty or "umidade_solo_0_1cm" not in met.columns:
        try:
            from sisclima.core.config import as_bool, env
            from sisclima.ingestion.openmeteo import fetch_openmeteo_for_municipios
            if as_bool(env("USE_OPENMETEO", "true"), True):
                mun_geo = resumo.copy()
                if "lat" not in mun_geo.columns or mun_geo["lat"].isna().all():
                    geo = read_table("geo_vulnerabilidade_municipal")
                    if not geo.empty and "cod_ibge" in geo.columns:
                        gkeep = [c for c in ["cod_ibge", "lat", "lon", "municipio"] if c in geo.columns]
                        mun_geo = mun_geo.drop(columns=[c for c in ["lat", "lon"] if c in mun_geo.columns], errors="ignore")
                        mun_geo = mun_geo.merge(geo[gkeep].drop_duplicates("cod_ibge"), on="cod_ibge", how="left")
                if {"lat", "lon"}.issubset(mun_geo.columns):
                    cols_geo = [c for c in ["cod_ibge", "municipio", "lat", "lon"] if c in mun_geo.columns]
                    om = fetch_openmeteo_for_municipios(mun_geo[cols_geo].dropna(subset=["lat", "lon"]))
                    if not om.empty:
                        om = enrich_soil_saturation(om)
                        if met.empty:
                            met = om
                        else:
                            soil_cols = [
                                c for c in om.columns
                                if str(c).startswith("umidade_solo") or c in ("indice_saturacao_solo", "classe_saturacao_solo", "fonte_solo")
                            ]
                            keys = [c for c in ["cod_ibge", "data"] if c in met.columns and c in om.columns]
                            if keys and soil_cols:
                                met = met.copy()
                                om = om.copy()
                                met["data"] = pd.to_datetime(met["data"], errors="coerce").dt.strftime("%Y-%m-%d")
                                om["data"] = pd.to_datetime(om["data"], errors="coerce").dt.strftime("%Y-%m-%d")
                                if "cod_ibge" in keys:
                                    met["cod_ibge"] = met["cod_ibge"].astype(str)
                                    om["cod_ibge"] = om["cod_ibge"].astype(str)
                                met = met.drop(columns=[c for c in soil_cols if c in met.columns], errors="ignore")
                                met = met.merge(om[keys + soil_cols].drop_duplicates(keys), on=keys, how="left")
                                # Se o merge não casou (datas históricas vs forecast), anexa snapshot solo do OM
                                if "indice_saturacao_solo" not in met.columns or pd.to_numeric(met["indice_saturacao_solo"], errors="coerce").isna().all():
                                    log.info("Merge solo por data sem match — usando série Open-Meteo com solo como met_biometeo complementar")
                                    met = pd.concat([met.drop(columns=soil_cols, errors="ignore"), om], ignore_index=True, sort=False)
                            else:
                                met = pd.concat([met, om], ignore_index=True, sort=False)
                        log.info("Solo Open-Meteo: %s linhas com índice", int(pd.to_numeric(met.get("indice_saturacao_solo"), errors="coerce").notna().sum()) if "indice_saturacao_solo" in met.columns else 0)
        except Exception as exc:
            log.warning("Open-Meteo solo não atualizado no enrichment: %s", exc)
    else:
        met = enrich_soil_saturation(met)

    if not met.empty and "indice_saturacao_solo" in met.columns:
        write_df(met, "met_biometeo")
        solo_snap = municipal_soil_snapshot(met, resumo)
        write_df(solo_snap, "solo_saturacao_municipal")
        if not solo_snap.empty and "cod_ibge" in solo_snap.columns:
            skeep = [c for c in ["cod_ibge", "indice_saturacao_solo", "classe_saturacao_solo", "umidade_solo_media"] if c in solo_snap.columns]
            sm = solo_snap[skeep].drop_duplicates("cod_ibge")
            sm["cod_ibge"] = sm["cod_ibge"].astype(str)
            resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
            for col in skeep:
                if col == "cod_ibge":
                    continue
                if col in resumo.columns:
                    resumo = resumo.drop(columns=[col])
            resumo = resumo.merge(sm, on="cod_ibge", how="left")
            write_df(resumo, "resumo_municipal_atual")

    ana_tel = read_table("ana_telemetria")
    hidro = compute_hidro_risco_from_ana(ana_tel)
    if hidro is None or hidro.empty:
        # Fallback leve a partir de ana_risco_municipal (nível de chuva)
        ana_r = read_table("ana_risco_municipal")
        if not ana_r.empty:
            ar = ana_r.copy()
            if "data" in ar.columns:
                ar["data"] = pd.to_datetime(ar["data"], errors="coerce")
                ar = ar.sort_values("data").groupby("cod_ibge", as_index=False).tail(1) if "cod_ibge" in ar.columns else ar
            nivel_map = {"verde": 0, "amarela": 1, "laranja": 3, "vermelha": 5, "roxa": 5}
            if "nivel_chuva" in ar.columns:
                ar["score_hidro_max"] = ar["nivel_chuva"].astype(str).str.lower().map(nivel_map).fillna(0).astype(int)
                ar["nivel_alerta_hidro"] = ar["nivel_chuva"]
                ar["risco_predominante"] = np.where(ar["score_hidro_max"] >= 1, "chuva_ana", "sem_gatilho")
                ar["fonte"] = "ANA_risco_municipal_fallback"
                ar["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                hidro = ar
    write_df(hidro if hidro is not None else pd.DataFrame(), "hidro_risco_municipal")
    if not hidro.empty and "cod_ibge" in hidro.columns:
        hkeep = [c for c in ["cod_ibge", "nivel_alerta_hidro", "score_hidro_max", "risco_predominante"] if c in hidro.columns]
        hm = hidro[hkeep].drop_duplicates("cod_ibge")
        hm["cod_ibge"] = hm["cod_ibge"].astype(str)
        resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
        for col in hkeep:
            if col == "cod_ibge":
                continue
            if col in resumo.columns:
                resumo = resumo.drop(columns=[col])
        resumo = resumo.merge(hm, on="cod_ibge", how="left")
        write_df(resumo, "resumo_municipal_atual")

    sivep_series = read_table("epi_sivep_srag")
    arbo_mun = read_table("epi_arboviroses_municipal")
    press_series = read_table("epi_pressao_assistencial")
    occ_mun = read_table("hospital_ocupacao_municipio")
    saz = compute_seasonality_outputs(met, sivep_series, arbo_mun, press_series, occ_mun)
    for tname, frame in saz.items():
        write_df(frame if frame is not None else pd.DataFrame(), tname)
    pred, pred_reg = build_predicao_7d(met, resumo)
    write_df(pred, "predicao_calor_7d_municipal_v6")
    write_df(pred_reg, "predicao_calor_7d_regional_v6")

    # Indicadores compostos do painel (tensão climática, vigilância, tendência 7d…)
    from sisclima.engines.panel_indicators import (
        enrich_panel_indicators,
        panel_indicators_snapshot,
        state_indicator_summary,
    )

    resumo = enrich_panel_indicators(resumo, pred)

    # WASH IBGE (antes do AdaptaSUS, para alimentar risco_wash)
    try:
        from sisclima.ingestion.ibge_wash import load_wash_municipal
        from sisclima.core.config import as_bool, env

        if as_bool(env("USE_IBGE_WASH", "true"), True):
            wash = load_wash_municipal()
            write_df(wash if wash is not None else pd.DataFrame(), "wash_municipal")
            if wash is not None and not wash.empty and "cod_ibge" in wash.columns:
                wcols = [
                    c
                    for c in (
                        "cod_ibge",
                        "cobertura_rede_agua_pct",
                        "deficit_rede_agua_pct",
                        "cobertura_agua_canalizada_pct",
                        "deficit_agua_canalizada_pct",
                        "cobertura_esgoto_rede_pct",
                        "deficit_esgoto_inadequado_pct",
                        "indice_deficit_wash",
                        "fonte_wash",
                    )
                    if c in wash.columns
                ]
                wm = wash[wcols].drop_duplicates("cod_ibge")
                wm["cod_ibge"] = wm["cod_ibge"].astype(str)
                resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
                for col in wcols:
                    if col != "cod_ibge" and col in resumo.columns:
                        resumo = resumo.drop(columns=[col])
                resumo = resumo.merge(wm, on="cod_ibge", how="left")
    except Exception as exc:  # noqa: BLE001
        log.warning("WASH IBGE não mesclado no enrichment: %s", exc)

    # Inteligência AdaptaSUS / Guia MS (scores por risco + derivados)
    from sisclima.engines.adaptasus_intelligence import enrich_adaptasus_intelligence

    resumo, adapt_mun, adapt_estado = enrich_adaptasus_intelligence(resumo)
    write_df(resumo, "resumo_municipal_atual")
    if not adapt_mun.empty:
        write_df(adapt_mun, "adaptasus_risco_municipal")
    if not adapt_estado.empty:
        write_df(adapt_estado, "adaptasus_risco_estado")

    snap = panel_indicators_snapshot(resumo)
    if not snap.empty:
        write_df(snap, "indicadores_painel_municipal")

    # Regrava base analítica já com índices compostos
    base_cols = [c for c in base_cols if c in resumo.columns]
    extra = [
        c for c in [
            "indice_tensao_climatica", "indice_carga_saude", "indice_vigilancia_integrada",
            "indice_adaptacao_climatica", "tendencia_7d", "completude_dados_pct",
            "percentil_risco_estadual", "orientacao_leiga", "orientacao_adaptasus",
            "risco_adaptasus_dominante", "risco_calor_vulneravel", "risco_ar_queimadas",
            "risco_vetorial_climatico", "pressao_rede_climatica",
            "indice_deficit_wash", "risco_wash", "cobertura_rede_agua_pct",
            "deficit_esgoto_inadequado_pct",
            "pop_vulneravel_exposta", "indice_exposicao_vulneravel", "idosos_pct",

        ]
        if c in resumo.columns and c not in base_cols
    ]
    write_df(resumo[base_cols + extra], "analise_clima_saude_base_municipal_v8")

    # Queimadas INPE (refresh best-effort) + merge no resumo
    try:
        from sisclima.ingestion.inpe_queimadas import load_queimadas_municipais
        from sisclima.core.config import as_bool, env

        if as_bool(env("USE_INPE_QUEIMADAS", "true"), True):
            q = load_queimadas_municipais()
            write_df(q if q is not None else pd.DataFrame(), "queimadas_focos_municipal")
            if q is not None and not q.empty and "cod_ibge" in q.columns:
                qcols = [
                    c
                    for c in (
                        "cod_ibge",
                        "focos_queimadas_24h",
                        "focos_queimadas_7d",
                        "frp_queimadas_7d",
                        "nivel_queimadas",
                        "dias_sem_chuva_max",
                    )
                    if c in q.columns
                ]
                qm = q[qcols].drop_duplicates("cod_ibge")
                qm["cod_ibge"] = qm["cod_ibge"].astype(str)
                resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
                for col in qcols:
                    if col != "cod_ibge" and col in resumo.columns:
                        resumo = resumo.drop(columns=[col])
                resumo = resumo.merge(qm, on="cod_ibge", how="left")
                write_df(resumo, "resumo_municipal_atual")
    except Exception as exc:  # noqa: BLE001
        log.warning("Queimadas INPE não mescladas no enrichment: %s", exc)

    # Frio extremo a partir do último dia de met_biometeo
    try:
        met_frio = read_table("met_biometeo")
        if not met_frio.empty and "tmin" in met_frio.columns and "cod_ibge" in met_frio.columns:
            from sisclima.engines.biometeo import add_coldwave_indicators
            from sisclima.core.config import SETTINGS as _SETTINGS

            mf = add_coldwave_indicators(met_frio, _SETTINGS if isinstance(_SETTINGS, dict) else {})
            if "data" in mf.columns:
                mf["data"] = pd.to_datetime(mf["data"], errors="coerce")
                mf = mf.sort_values("data").groupby("cod_ibge", as_index=False).tail(1)
            fcols = [
                c
                for c in (
                    "cod_ibge",
                    "onda_fria_2d",
                    "duracao_onda_fria_dias",
                    "intensidade_onda_fria",
                    "severidade_onda_fria",
                    "excesso_frio_tmin",
                )
                if c in mf.columns
            ]
            if len(fcols) > 1:
                fm = mf[fcols].drop_duplicates("cod_ibge")
                fm["cod_ibge"] = fm["cod_ibge"].astype(str)
                resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
                for col in fcols:
                    if col != "cod_ibge" and col in resumo.columns:
                        resumo = resumo.drop(columns=[col])
                resumo = resumo.merge(fm, on="cod_ibge", how="left")
                write_df(resumo, "resumo_municipal_atual")
    except Exception as exc:  # noqa: BLE001
        log.warning("Indicadores de frio não mesclados: %s", exc)

    # Alerta integrado SIS + TITAN antes do alerta inteligente (para compor extras)
    inmet_tab = read_table("inmet_alertas")
    cemaden_tab = read_table("cemaden_alertas")
    alerta_int = build_alerta_integrado_municipal(resumo, inmet_tab, cemaden_tab, hidro)
    write_df(alerta_int, "alerta_integrado_sis_titan")
    if not alerta_int.empty:
        inj_ai = alerta_int[
            [c for c in ["cod_ibge", "nivel_alerta_integrado", "score_alerta_integrado", "componente_dominante", "motivo_integrado", "acao_recomendada"] if c in alerta_int.columns]
        ].drop_duplicates("cod_ibge")
        inj_ai["cod_ibge"] = inj_ai["cod_ibge"].astype(str)
        resumo["cod_ibge"] = resumo["cod_ibge"].astype(str)
        for col in inj_ai.columns:
            if col == "cod_ibge":
                continue
            if col in resumo.columns:
                resumo = resumo.drop(columns=[col])
        resumo = resumo.merge(inj_ai, on="cod_ibge", how="left")
        write_df(resumo, "resumo_municipal_atual")

    # Prioridade global (soma ponderada das camadas 0–100)
    try:
        from sisclima.engines.prioridade_global import enrich_prioridade_global

        resumo = enrich_prioridade_global(resumo)
        write_df(resumo, "resumo_municipal_atual")
    except Exception as exc:  # noqa: BLE001
        log.warning("Prioridade global não calculada: %s", exc)

    alerta, alerta_reg = build_alerta_inteligente(resumo, pred)
    write_df(alerta, "alerta_inteligente_municipal_v6")
    write_df(alerta_reg, "alerta_inteligente_regional_v6")

    # Situação estadual
    if not resumo.empty:
        estado = resumo.sort_values(["score", "risco_cumulativo_3d"] if "risco_cumulativo_3d" in resumo.columns else ["score"], ascending=False).head(1).copy()
        estado["municipios_monitorados"] = resumo["cod_ibge"].nunique() if "cod_ibge" in resumo.columns else len(resumo)
        estado["municipios_laranja_ou_mais"] = int((pd.to_numeric(resumo["score"], errors="coerce") >= 2).sum())
        write_df(estado, "resumo_situacao_atual")

    # Metadados de disponibilidade assistencial para transparência na UI.
    if "fonte_ocupacao" in resumo.columns:
        fonte = resumo["fonte_ocupacao"].fillna("").astype(str)
        real_mask = fonte.str.contains("INDICASUS_TEMPO_REAL", case=False, na=False) & ~fonte.str.contains("FALLBACK|CACHE", case=False, na=False)
        fallback_mask = fonte.str.contains("FALLBACK|CACHE", case=False, na=False)
        total = len(resumo)
        meta = pd.DataFrame(
            [
                {
                    "data_referencia": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "municipios_total": int(total),
                    "municipios_ocup_real": int(real_mask.sum()),
                    "municipios_ocup_fallback": int(fallback_mask.sum()),
                    "cobertura_ocup_real_pct": float((100.0 * real_mask.sum() / total) if total else 0.0),
                }
            ]
        )
        write_df(meta, "ops_disponibilidade_assistencia")

    # Monitoramento saúde-calor (dicionário, GAL, SIM, série consolidada + status GeoCalor)
    try:
        from sisclima.engines.saude_calor_consolida import run_saude_calor_consolidation

        saude_meta = run_saude_calor_consolidation(include_geocalor=True, try_dw=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("Consolidação saúde-calor falhou: %s", exc)
        saude_meta = {"ok": False, "erro": str(exc)}

    summary = {
        "municipios": len(resumo),
        "com_pressao": int(pd.to_numeric(resumo.get("pressao_calor_pct"), errors="coerce").notna().sum()) if "pressao_calor_pct" in resumo.columns else 0,
        "com_ocupacao": int(pd.to_numeric(resumo.get("ocupacao_leitos_pct"), errors="coerce").notna().sum()) if "ocupacao_leitos_pct" in resumo.columns else 0,
        "com_pm25": int(pd.to_numeric(resumo.get("pm25_ugm3"), errors="coerce").notna().sum()) if "pm25_ugm3" in resumo.columns else 0,
        "com_arbo": int(pd.to_numeric(resumo.get("casos_arbovirus_7d"), errors="coerce").fillna(0).gt(0).sum()) if "casos_arbovirus_7d" in resumo.columns else 0,
        "correlacoes": len(corr),
        "odds_ratios": len(odds),
        "sazonalidade_mensal": len(saz.get("sazonalidade_indice_mensal_v1", pd.DataFrame())),
        "solo_saturacao": int(pd.to_numeric(resumo.get("indice_saturacao_solo"), errors="coerce").notna().sum()) if "indice_saturacao_solo" in resumo.columns else 0,
        "ops_cnes": len(ops_cnes_resumo) if not ops_cnes_resumo.empty else 0,
        "hidro_risco": len(hidro) if hidro is not None else 0,
        "alerta_integrado": len(alerta_int) if alerta_int is not None else 0,
        "predicao_7d": len(pred),
        "alerta_inteligente": len(alerta),
        "indicadores_painel": len(snap) if not snap.empty else 0,
        "adaptasus_municipios": len(adapt_mun) if adapt_mun is not None else 0,
        "adaptacao_media": float(pd.to_numeric(resumo.get("indice_adaptacao_climatica"), errors="coerce").mean()) if "indice_adaptacao_climatica" in resumo.columns else None,
        "painel_kpis": state_indicator_summary(resumo),
        "nivel_dist": resumo["nivel"].value_counts().to_dict() if "nivel" in resumo.columns else {},
        "saude_calor": saude_meta,
    }
    log.info("Enriquecimento concluído: %s", summary)
    return summary
