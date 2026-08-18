# -*- coding: utf-8 -*-
"""Risco hidrológico municipal a partir de séries ANA (padrão claro hidro_risco_v14).

Classifica estiagem (nível baixo) e cheia/inundação (nível alto) por percentis
e, opcionalmente, por cotas absolutas em config/ana_cotas_referencia_mt.csv.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from sisclima.core.config import ROOT, env
from sisclima.utils.io import read_table_safe


def _fill_cod_ibge_from_municipio(df: pd.DataFrame) -> pd.DataFrame:
    """Preenche cod_ibge ausente via nome do município (match ASCII como map_estacoes_to_ibge)."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    if "municipio" not in out.columns:
        if "cod_ibge" not in out.columns:
            out["cod_ibge"] = pd.NA
        return out
    if "cod_ibge" not in out.columns:
        out["cod_ibge"] = pd.NA
    missing = out["cod_ibge"].isna() | (
        out["cod_ibge"].astype(str).str.strip().isin(["", "nan", "None", "<NA>", "NaT"])
    )
    if not missing.any():
        return out
    try:
        from sisclima.ingestion.ana_hidroweb import map_estacoes_to_ibge
        from sisclima.ingestion.ibge_municipios import get_municipios_operacionais

        mun_ref = get_municipios_operacionais()
        if mun_ref is None or mun_ref.empty:
            return out
        mapped = map_estacoes_to_ibge(out, mun_ref)
        if "cod_ibge" in mapped.columns:
            return mapped
    except Exception:
        pass
    return out


def _nivel_alerta(score: float) -> str:
    if score >= 5:
        return "vermelha"
    if score >= 3:
        return "laranja"
    if score >= 1:
        return "amarela"
    return "verde"


def _tendencia(delta: float, limiar: float) -> str:
    if pd.isna(delta):
        return "indisponivel"
    if delta >= limiar:
        return "subindo"
    if delta <= -limiar:
        return "caindo"
    return "estavel"


def _situacao_hidro(risco_predominante: str, score_estiagem: float, score_cheia: float) -> str:
    rp = str(risco_predominante or "").lower()
    if rp == "estiagem_rio_baixo" or (score_estiagem >= 2 and score_estiagem > score_cheia):
        return "seca_baixa"
    if rp == "cheia_subida_rio" or (score_cheia >= 2 and score_cheia > score_estiagem):
        return "inundacao_alta"
    if rp == "chuva_ana" and score_cheia >= 1:
        return "inundacao_alta"
    return "normal"


def _cota_regua_plausivel(series: pd.Series, nomes: pd.Series | None = None) -> pd.Series:
    """Exclui cotas de barramento/elevação (tipicamente >5 m em escala de régua fluvial).

    Estações 'BARRAMENTO' reportam cota de reservatório (dezenas de milhares de cm)
    e distorcem o max municipal — não devem entrar no score de seca/cheia.
    """
    ok = pd.to_numeric(series, errors="coerce").notna()
    vals = pd.to_numeric(series, errors="coerce")
    ok &= vals >= 0
    ok &= vals < 5000  # régua fluvial operacional; acima costuma ser cota de barragem
    if nomes is not None:
        n = nomes.astype(str).str.upper()
        ok &= ~n.str.contains("BARRAMENTO", na=False)
    return ok


def load_cotas_referencia(path: str | Path | None = None) -> pd.DataFrame:
    """CSV opcional: codigo_estacao, cota_seca_cm, cota_alerta_cm, cota_emergencia_cm."""
    raw = path or env("ANA_COTAS_REFERENCIA_CSV", "config/ana_cotas_referencia_mt.csv")
    p = Path(raw) if Path(str(raw)).is_absolute() else ROOT / str(raw)
    if not p.exists():
        return pd.DataFrame()
    df = read_table_safe(p)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "codigo_estacao" not in df.columns:
        return pd.DataFrame()
    df["codigo_estacao"] = df["codigo_estacao"].astype(str).str.replace(r"\.0$", "", regex=True)
    for c in ("cota_seca_cm", "cota_alerta_cm", "cota_emergencia_cm"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    # ignora linhas de exemplo comentadas / vazias
    df = df[df["codigo_estacao"].str.len() > 0]
    df = df[~df["codigo_estacao"].astype(str).str.startswith("#")]
    return df.reset_index(drop=True)


def _score_series(valores: pd.Series, valor_ult: float, delta_7d: float, limiar_delta: float) -> tuple[int, int, list[str], str]:
    p10 = float(valores.quantile(0.10))
    p25 = float(valores.quantile(0.25))
    p75 = float(valores.quantile(0.75))
    p90 = float(valores.quantile(0.90))
    tend = _tendencia(delta_7d, limiar_delta)
    score_estiagem = 0
    score_cheia = 0
    motivo: list[str] = []
    if valor_ult <= p10:
        score_estiagem += 3
        motivo.append("valor <= P10")
    elif valor_ult <= p25:
        score_estiagem += 1
        motivo.append("valor <= P25")
    if valor_ult >= p90:
        score_cheia += 3
        motivo.append("valor >= P90")
    elif valor_ult >= p75:
        score_cheia += 1
        motivo.append("valor >= P75")
    if tend == "caindo":
        score_estiagem += 1
        motivo.append("tendencia queda 7d")
    if tend == "subindo":
        score_cheia += 1
        motivo.append("tendencia subida 7d")
    return score_estiagem, score_cheia, motivo, tend


def _score_cota_absoluta(valor_ult: float, ref: pd.Series | dict) -> tuple[int, int, list[str]]:
    """Aplica limiares absolutos de régua (cm) quando cadastrados."""
    se = sc = 0
    motivo: list[str] = []
    seca = pd.to_numeric(ref.get("cota_seca_cm") if hasattr(ref, "get") else None, errors="coerce")
    alerta = pd.to_numeric(ref.get("cota_alerta_cm") if hasattr(ref, "get") else None, errors="coerce")
    emerg = pd.to_numeric(ref.get("cota_emergencia_cm") if hasattr(ref, "get") else None, errors="coerce")
    if pd.notna(seca) and valor_ult <= float(seca):
        se = max(se, 3)
        motivo.append(f"cota <= seca ({float(seca):.0f} cm)")
    if pd.notna(emerg) and valor_ult >= float(emerg):
        sc = max(sc, 5)
        motivo.append(f"cota >= emergência ({float(emerg):.0f} cm)")
    elif pd.notna(alerta) and valor_ult >= float(alerta):
        sc = max(sc, 3)
        motivo.append(f"cota >= alerta ({float(alerta):.0f} cm)")
    return se, sc, motivo


def compute_hidro_risco_from_ana(telemetria: pd.DataFrame) -> pd.DataFrame:
    """Calcula risco hidro municipal a partir de ana_telemetria (cota/vazao/chuva)."""
    if telemetria is None or telemetria.empty:
        return pd.DataFrame()
    df = telemetria.copy()
    if "data" not in df.columns and "data_hora" in df.columns:
        df["data"] = pd.to_datetime(df["data_hora"], errors="coerce").dt.normalize()
    else:
        df["data"] = pd.to_datetime(df.get("data"), errors="coerce")
    df = df.dropna(subset=["data"])
    if df.empty:
        return pd.DataFrame()

    cotas_ref = load_cotas_referencia()
    ref_by_est: dict[str, pd.Series] = {}
    if not cotas_ref.empty:
        for _, r in cotas_ref.iterrows():
            ref_by_est[str(r["codigo_estacao"])] = r

    min_dias_pct = int(env("ANA_HIDRO_MIN_DIAS", "5") or 5)
    rows: list[dict] = []
    for var, label in [("cota_cm", "cota"), ("vazao_m3s", "vazao"), ("chuva_mm", "chuva")]:
        if var not in df.columns:
            continue
        work = df.copy()
        work[var] = pd.to_numeric(work[var], errors="coerce")
        work = work.dropna(subset=[var])
        if label == "cota":
            nomes = work["nome_estacao"] if "nome_estacao" in work.columns else None
            work = work.loc[_cota_regua_plausivel(work[var], nomes)].copy()
            if work.empty:
                continue
        keys = [c for c in ["cod_ibge", "municipio"] if c in work.columns]
        # pandas groupby dropna=True esconde grupos com cod_ibge nulo
        if "cod_ibge" in keys and work["cod_ibge"].isna().all():
            keys = [c for c in keys if c != "cod_ibge"]
        if not keys:
            continue
        for key_vals, g in work.groupby(keys, dropna=False):
            if not isinstance(key_vals, tuple):
                key_vals = (key_vals,)
            meta = dict(zip(keys, key_vals))
            g = g.sort_values("data")
            daily = g.groupby("data", as_index=False)[var].median()
            valores = daily[var].dropna()
            valor_ult = float(valores.iloc[-1]) if len(valores) else np.nan
            if pd.isna(valor_ult):
                continue

            # Cotas absolutas por estação (permite série curta)
            se_abs = sc_abs = 0
            motivo_abs: list[str] = []
            if label == "cota" and "codigo_estacao" in g.columns and ref_by_est:
                for cod in g["codigo_estacao"].astype(str).unique():
                    if cod in ref_by_est:
                        se_a, sc_a, mot = _score_cota_absoluta(valor_ult, ref_by_est[cod])
                        se_abs = max(se_abs, se_a)
                        sc_abs = max(sc_abs, sc_a)
                        motivo_abs.extend(mot)

            has_abs = se_abs > 0 or sc_abs > 0
            min_need = 3 if has_abs else min_dias_pct
            if len(daily) < min_need and not has_abs:
                continue
            if len(valores) < min_need and not has_abs:
                continue

            se = sc = 0
            motivo: list[str] = []
            tend = "indisponivel"
            delta_7d = np.nan
            if len(valores) >= min_dias_pct:
                ult7 = float(daily.tail(7)[var].mean()) if len(daily) >= 7 else float(valores.mean())
                ant7 = float(daily.iloc[-14:-7][var].mean()) if len(daily) >= 14 else np.nan
                delta_7d = float(ult7 - ant7) if not pd.isna(ult7) and not pd.isna(ant7) else np.nan
                iqr = float(valores.quantile(0.75) - valores.quantile(0.25)) if len(valores) >= 4 else 1.0
                limiar = max(abs(iqr) * 0.10, 1.0)
                se, sc, motivo, tend = _score_series(valores, valor_ult, delta_7d, limiar)

            se = max(se, se_abs)
            sc = max(sc, sc_abs)
            motivo = motivo + motivo_abs

            if label == "chuva":
                se = 0
                if len(valores) >= min_dias_pct and valor_ult >= float(valores.quantile(0.90)):
                    sc = max(sc, 2)
                    motivo = [m for m in motivo if "P10" not in m and "P25" not in m] or ["chuva alta (P90)"]
                elif not motivo:
                    continue

            score = max(se, sc)
            if score <= 0 and not has_abs:
                # ainda registra série neutra só para cota/vazão com histórico
                if label == "chuva":
                    continue
            rows.append(
                {
                    **meta,
                    "variavel": label,
                    "n_dias": int(len(daily)),
                    "data_ultima": pd.Timestamp(daily["data"].max()).strftime("%Y-%m-%d"),
                    "valor_ultimo": round(valor_ult, 3),
                    "delta_7d": round(delta_7d, 3) if not pd.isna(delta_7d) else np.nan,
                    "tendencia_7d": tend,
                    "score_estiagem": se,
                    "score_cheia": sc,
                    "score_hidro": score,
                    "nivel_alerta_hidro": _nivel_alerta(score),
                    "motivo_tecnico": "; ".join(motivo) if motivo else "sem gatilho",
                }
            )

    if not rows:
        return pd.DataFrame()
    est = pd.DataFrame(rows)
    group_keys = [c for c in ["cod_ibge", "municipio"] if c in est.columns]
    if "cod_ibge" in group_keys and est["cod_ibge"].isna().all():
        group_keys = [c for c in group_keys if c != "cod_ibge"]
    mun = (
        est.groupby(group_keys, as_index=False, dropna=False)
        .agg(
            n_series=("variavel", "nunique"),
            score_hidro_max=("score_hidro", "max"),
            score_estiagem_max=("score_estiagem", "max"),
            score_cheia_max=("score_cheia", "max"),
            data_mais_recente=("data_ultima", "max"),
            cota_cm_ultima=("valor_ultimo", "max"),
            motivo_resumo=("motivo_tecnico", lambda s: " | ".join(list(s)[:3])[:800]),
        )
    )
    # cota_cm_ultima: preferir valor da variável cota se existir
    cota_rows = est[est["variavel"] == "cota"] if "variavel" in est.columns else pd.DataFrame()
    if not cota_rows.empty and group_keys:
        cota_ult = cota_rows.sort_values("data_ultima").groupby(group_keys, as_index=False).tail(1)
        cota_ult = cota_ult[group_keys + ["valor_ultimo"]].rename(columns={"valor_ultimo": "cota_cm"})
        mun = mun.drop(columns=["cota_cm_ultima"], errors="ignore").merge(cota_ult, on=group_keys, how="left")
    else:
        mun = mun.rename(columns={"cota_cm_ultima": "cota_cm"})

    mun["nivel_alerta_hidro"] = mun["score_hidro_max"].map(_nivel_alerta)
    mun["risco_predominante"] = np.where(
        mun["score_estiagem_max"] > mun["score_cheia_max"],
        "estiagem_rio_baixo",
        np.where(mun["score_cheia_max"] > mun["score_estiagem_max"], "cheia_subida_rio", "misto_ou_neutro"),
    )
    mun["situacao_hidro"] = [
        _situacao_hidro(rp, se, sc)
        for rp, se, sc in zip(
            mun["risco_predominante"],
            mun["score_estiagem_max"],
            mun["score_cheia_max"],
        )
    ]
    mun["fonte"] = "ANA_telemetria_percentis"
    mun["data_processamento"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    mun["nota_tecnica"] = (
        "Risco hidrológico por percentis/tendência e cotas absolutas opcionais "
        "(seca_baixa / inundacao_alta)."
    )
    # groupby pode omitir cod_ibge quando a coluna era toda nula — recupera via município
    mun = _fill_cod_ibge_from_municipio(mun)
    return mun
