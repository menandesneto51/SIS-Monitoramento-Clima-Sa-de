# -*- coding: utf-8 -*-
"""Série histórica ambiental estadual (clima + ar) e comparação com a janela atual."""
from __future__ import annotations

from typing import Any

import pandas as pd

from sisclima.core.db import read_table, table_exists


def serie_clima_estado(met: pd.DataFrame | None = None) -> pd.DataFrame:
    """Agrega `met_biometeo` em média/máxima estadual diária."""
    if met is None:
        met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    if met is None or met.empty or "data" not in met.columns:
        return pd.DataFrame()
    m = met.copy()
    m["data"] = pd.to_datetime(m["data"], errors="coerce").dt.normalize()
    m = m.dropna(subset=["data"])
    agg: dict[str, tuple[str, str]] = {}
    for col, how in (
        ("tmax", "mean"),
        ("tmin", "mean"),
        ("utci_proxy", "mean"),
        ("umidade_media", "mean"),
        ("precipitacao_mm", "sum"),
        ("risco_cumulativo_3d", "mean"),
    ):
        if col in m.columns:
            agg[f"{col}_{'media' if how == 'mean' else 'soma'}"] = (col, how)
    if "tmax" in m.columns:
        agg["tmax_max"] = ("tmax", "max")
    if not agg:
        return pd.DataFrame()
    out = m.groupby("data", as_index=False).agg(**agg)
    out["data"] = pd.to_datetime(out["data"], errors="coerce")
    return out.sort_values("data")


def serie_ar_estado(aq: pd.DataFrame | None = None) -> pd.DataFrame:
    if aq is None:
        aq = (
            read_table("qualidade_ar_estado_serie_v6")
            if table_exists("qualidade_ar_estado_serie_v6")
            else pd.DataFrame()
        )
    if aq is None or aq.empty:
        return pd.DataFrame()
    out = aq.copy()
    if "data" in out.columns:
        out["data"] = pd.to_datetime(out["data"], errors="coerce")
        out = out.dropna(subset=["data"]).sort_values("data")
    return out


def comparar_janela_atual(
    clima: pd.DataFrame,
    *,
    dias_janela: int = 7,
) -> dict[str, Any]:
    """Compara últimos N dias com a média histórica disponível da série."""
    empty = {
        "ok": False,
        "dias_serie": 0,
        "dias_janela": dias_janela,
        "narrativa": "Série ambiental insuficiente para comparação com o histórico.",
        "indicadores": {},
    }
    if clima is None or clima.empty or "data" not in clima.columns:
        return empty
    df = clima.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"]).sort_values("data")
    hoje = pd.Timestamp.now().normalize()
    # Evita incluir dias de previsão futura na "janela atual".
    df_obs = df[df["data"] <= hoje]
    if len(df_obs) >= max(dias_janela + 3, 10):
        df = df_obs
    if len(df) < max(dias_janela + 3, 10):
        empty["dias_serie"] = int(len(df))
        return empty

    fim = df["data"].max()
    ini = fim - pd.Timedelta(days=dias_janela - 1)
    atual = df[df["data"] >= ini]
    hist = df[df["data"] < ini]
    if atual.empty or hist.empty:
        empty["dias_serie"] = int(len(df))
        return empty

    indicadores: dict[str, dict[str, float]] = {}
    for col, rotulo in (
        ("tmax_media", "Tmáx média (°C)"),
        ("tmax_max", "Tmáx máxima (°C)"),
        ("utci_proxy_media", "UTCI médio"),
        ("umidade_media_media", "Umidade média (%)"),
        ("risco_cumulativo_3d_media", "Risco cumulativo 3d"),
    ):
        if col not in df.columns:
            continue
        a = pd.to_numeric(atual[col], errors="coerce").mean()
        h = pd.to_numeric(hist[col], errors="coerce").mean()
        if pd.isna(a) or pd.isna(h):
            continue
        indicadores[rotulo] = {
            "atual": float(a),
            "historico": float(h),
            "delta": float(a - h),
        }

    # Mês corrente vs mesmo mês em outros anos da série (z-score)
    mes = int(fim.month)
    ano = int(fim.year)
    mes_cmp: dict[str, Any] = {"mes": mes, "ano": ano, "ok": False}
    if "tmax_media" in df.columns:
        df_m = df.copy()
        df_m["_mes"] = df_m["data"].dt.month
        df_m["_ano"] = df_m["data"].dt.year
        atual_mes = df_m[(df_m["_mes"] == mes) & (df_m["_ano"] == ano)]
        hist_mes = df_m[(df_m["_mes"] == mes) & (df_m["_ano"] != ano)]
        mes_cmp["n_dias_mes_atual"] = int(len(atual_mes))
        mes_cmp["n_dias_mesmo_mes_historico"] = int(len(hist_mes))
        mes_cmp["anos_historico"] = sorted({int(a) for a in hist_mes["_ano"].dropna().unique().tolist()})
        zscores: dict[str, dict[str, float]] = {}
        for col, rotulo in (
            ("tmax_media", "Tmáx média (°C)"),
            ("utci_proxy_media", "UTCI médio"),
            ("risco_cumulativo_3d_media", "Risco cumulativo 3d"),
        ):
            if col not in df_m.columns:
                continue
            a = pd.to_numeric(atual_mes[col], errors="coerce").mean()
            h_s = pd.to_numeric(hist_mes[col], errors="coerce").dropna()
            if pd.isna(a) or len(h_s) < 5:
                continue
            mu = float(h_s.mean())
            sd = float(h_s.std(ddof=0))
            z = float((a - mu) / sd) if sd > 1e-9 else 0.0
            zscores[rotulo] = {
                "atual": float(a),
                "media_historica_mesmo_mes": mu,
                "desvio_padrao": sd,
                "zscore": z,
                "delta": float(a - mu),
            }
        if zscores:
            mes_cmp["ok"] = True
            mes_cmp["indicadores"] = zscores
            bits_z = [
                f"{rot}: {v['atual']:.1f} vs média {v['media_historica_mesmo_mes']:.1f} "
                f"do mesmo mês em anos anteriores (z={v['zscore']:+.2f})"
                for rot, v in zscores.items()
            ]
            mes_nome = [
                "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
                "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
            ][mes]
            mes_cmp["narrativa"] = (
                f"Comparação sazonal de {mes_nome}/{ano} com o mesmo mês na série "
                f"({', '.join(str(a) for a in mes_cmp['anos_historico']) or 'sem anos anteriores'}): "
                + "; ".join(bits_z)
                + ". |z|≥1 sugere desvio relevante frente ao padrão do mês."
            )

    partes = [
        f"Janela atual ({ini.date()} a {fim.date()}, {dias_janela} dias) frente à média do restante da série "
        f"({hist['data'].min().date()} a {hist['data'].max().date()}, {len(hist)} dias): "
    ]
    bits = []
    for rot, vals in indicadores.items():
        bits.append(f"{rot} {vals['atual']:.1f} vs histórico {vals['historico']:.1f} (Δ {vals['delta']:+.1f})")
    if not bits:
        return empty
    partes.append("; ".join(bits) + ".")
    partes.append(
        " Interpretação: desvio positivo em temperatura/UTCI/risco indica condição mais crítica "
        "que a média da série disponível — não substitui climatologia oficial de longo prazo."
    )
    if mes_cmp.get("ok") and mes_cmp.get("narrativa"):
        partes.append(" " + str(mes_cmp["narrativa"]))
    return {
        "ok": True,
        "dias_serie": int(len(df)),
        "dias_janela": dias_janela,
        "inicio_janela": str(ini.date()),
        "fim_janela": str(fim.date()),
        "indicadores": indicadores,
        "mes_cmp": mes_cmp,
        "narrativa": "".join(partes),
    }


def resumo_serie_ambiente_boletim() -> dict[str, Any]:
    """Pacote pronto para painel e boletim."""
    clima = serie_clima_estado()
    ar = serie_ar_estado()
    cmp_ = comparar_janela_atual(clima)
    ar_txt = ""
    if ar is not None and not ar.empty and "pm25_ugm3" in ar.columns:
        pm = pd.to_numeric(ar["pm25_ugm3"], errors="coerce")
        if pm.notna().any():
            ar_txt = (
                f" Qualidade do ar (série estadual): PM2,5 média {float(pm.mean()):.1f} µg/m³ "
                f"(máx. {float(pm.max()):.1f}; {len(ar)} dias)."
            )
    md = cmp_.get("narrativa") or "Série ambiental operacional ainda curta para comparação robusta."
    if ar_txt:
        md = md + ar_txt
    return {
        "clima": clima,
        "ar": ar,
        "comparacao": cmp_,
        "markdown": md,
        "ok": bool(cmp_.get("ok") or (ar is not None and not ar.empty)),
    }
