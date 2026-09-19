# -*- coding: utf-8 -*-
"""Série histórica ambiental estadual (clima + ar) e comparação com a janela atual.

Regra de ouro: comparar **o mesmo período do calendário** (mesmos dias MM-DD /
mesmo mês) em anos anteriores — nunca misturar meses diferentes como se fosse
climatologia sazonal.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from sisclima.core.db import read_table, table_exists

# Mínimos para publicar comparação de mesmo período
_MIN_DIAS_HIST_MESMO_PERIODO = 10
_MIN_ANOS_HIST = 2
_MIN_DIAS_HIST_MES = 5


def serie_clima_estado(met: pd.DataFrame | None = None) -> pd.DataFrame:
    """Agrega clima em média/máxima estadual diária.

    Prefere ``hist_clima_municipal_diario``; cai em ``met_biometeo`` se hist vazio.
    Funde PM2.5 de ``qualidade_ar_municipal`` quando hist não cobre o dia.
    """
    if met is None:
        if table_exists("hist_clima_municipal_diario"):
            hist = read_table("hist_clima_municipal_diario")
            if hist is not None and not hist.empty:
                met = hist
        if met is None or (isinstance(met, pd.DataFrame) and met.empty):
            met = read_table("met_biometeo") if table_exists("met_biometeo") else pd.DataFrame()
    if met is None or met.empty or "data" not in met.columns:
        return pd.DataFrame()
    m = met.copy()
    m["data"] = pd.to_datetime(m["data"], errors="coerce").dt.normalize()
    m = m.dropna(subset=["data"])
    # OBSERVED only — nunca misturar previsão futura na série histórica
    from datetime import date, timedelta

    corte = pd.Timestamp(date.today() - timedelta(days=1))
    m = m[m["data"] <= corte]
    # Alias PM se vier só como pm25
    if "pm25_ugm3" not in m.columns and "pm25" in m.columns:
        m["pm25_ugm3"] = pd.to_numeric(m["pm25"], errors="coerce")
    # Amplitude municipal diária (tmax−tmin) antes da média estadual
    if {"tmax", "tmin"}.issubset(m.columns):
        m["amplitude"] = (
            pd.to_numeric(m["tmax"], errors="coerce") - pd.to_numeric(m["tmin"], errors="coerce")
        )
    agg: dict[str, tuple[str, str]] = {}
    for col, how in (
        ("tmax", "mean"),
        ("tmin", "mean"),
        ("amplitude", "mean"),
        ("utci_proxy", "mean"),
        ("umidade_media", "mean"),
        ("precipitacao_mm", "mean"),
        ("risco_cumulativo_3d", "mean"),
        ("pm25_ugm3", "mean"),
    ):
        if col in m.columns:
            agg[f"{col}_{'media' if how == 'mean' else 'soma'}"] = (col, how)
    if "tmax" in m.columns:
        agg["tmax_max"] = ("tmax", "max")
    if not agg:
        return pd.DataFrame()
    out = m.groupby("data", as_index=False).agg(**agg)
    out["data"] = pd.to_datetime(out["data"], errors="coerce")
    # Fallback se amplitude não veio do groupby
    if "amplitude_media" not in out.columns and {"tmax_media", "tmin_media"}.issubset(out.columns):
        out["amplitude_media"] = (
            pd.to_numeric(out["tmax_media"], errors="coerce")
            - pd.to_numeric(out["tmin_media"], errors="coerce")
        )

    # Completar PM estadual a partir da série AQ se hist estiver rarefeito
    if table_exists("qualidade_ar_estado_serie_v6"):
        aq = read_table("qualidade_ar_estado_serie_v6")
        if aq is not None and not aq.empty and "data" in aq.columns and "pm25_ugm3" in aq.columns:
            aq = aq.copy()
            aq["data"] = pd.to_datetime(aq["data"], errors="coerce").dt.normalize()
            aq["pm25_ugm3"] = pd.to_numeric(aq["pm25_ugm3"], errors="coerce")
            aq = aq.dropna(subset=["data", "pm25_ugm3"]).drop_duplicates("data", keep="last")
            if "pm25_ugm3_media" not in out.columns:
                out["pm25_ugm3_media"] = np.nan
            else:
                out["pm25_ugm3_media"] = pd.to_numeric(out["pm25_ugm3_media"], errors="coerce")
            merged = out.merge(
                aq[["data", "pm25_ugm3"]].rename(columns={"pm25_ugm3": "_pm_aq"}),
                on="data",
                how="left",
            )
            fill = merged["pm25_ugm3_media"].isna() & merged["_pm_aq"].notna()
            merged.loc[fill, "pm25_ugm3_media"] = merged.loc[fill, "_pm_aq"]
            # dias só em AQ (fora do hist) — acrescentar
            only_aq = aq[~aq["data"].isin(out["data"])].copy()
            if not only_aq.empty:
                extra = pd.DataFrame({"data": only_aq["data"], "pm25_ugm3_media": only_aq["pm25_ugm3"]})
                merged = pd.concat([merged.drop(columns=["_pm_aq"], errors="ignore"), extra], ignore_index=True)
            else:
                merged = merged.drop(columns=["_pm_aq"], errors="ignore")
            out = merged
    return out.sort_values("data").drop_duplicates("data", keep="last")


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


def _sentido_desvio_sazonal(rotulo: str, z: float) -> str:
    """Frase curta em linguagem leiga para o sentido do z-score sazonal."""
    nome = str(rotulo).lower()
    if "amplitude" in nome:
        return (
            "maior amplitude térmica (dia/noite) que o padrão do período"
            if z > 0
            else "menor amplitude térmica (dia/noite) que o padrão do período"
        )
    if "umidade" in nome:
        return "mais úmido que o esperado para o período" if z > 0 else "mais seco que o esperado para o período"
    if "risco" in nome:
        return "risco térmico acima do padrão do período" if z > 0 else "risco térmico abaixo do padrão do período"
    if "utci" in nome or "tmáx" in nome or "tmax" in nome or "tmin" in nome or "temperatura" in nome:
        return "mais quente que o padrão do período" if z > 0 else "mais ameno que o padrão do período"
    if "precip" in nome or "chuva" in nome or "acumulad" in nome:
        return "mais chuvoso que o padrão do período" if z > 0 else "mais seco (menos chuva) que o padrão do período"
    if "pm" in nome or "ar" in nome:
        return "pior qualidade do ar que o padrão do período" if z > 0 else "melhor qualidade do ar que o padrão do período"
    return "acima do padrão do período" if z > 0 else "abaixo do padrão do período"


def _metricas() -> tuple[tuple[str, str], ...]:
    return (
        ("tmax_media", "Tmáx média (°C)"),
        ("tmax_max", "Tmáx máxima (°C)"),
        ("tmin_media", "Tmín média (°C)"),
        ("amplitude_media", "Amplitude térmica média (°C)"),
        ("utci_proxy_media", "UTCI médio"),
        ("umidade_media_media", "Umidade média (%)"),
        ("precipitacao_mm_media", "Precipitação média (mm)"),
        ("precipitacao_mm_acumulada", "Precipitação acumulada (mm)"),
        ("risco_cumulativo_3d_media", "Risco cumulativo 3d"),
        ("pm25_ugm3_media", "PM2.5 médio (µg/m³)"),
    )


def _col_fonte(col: str) -> str:
    """Coluna diária usada para métricas derivadas (ex.: acumulado de chuva)."""
    if col == "precipitacao_mm_acumulada":
        return "precipitacao_mm_media"
    return col


def _hist_por_ano(hist: pd.DataFrame, fonte: str, *, como: str) -> pd.Series:
    """Uma observação por ano no recorte histórico (média, max ou soma)."""
    tmp = hist.copy()
    tmp["_ano"] = pd.to_datetime(tmp["data"]).dt.year
    tmp["_v"] = pd.to_numeric(tmp[fonte], errors="coerce")
    g = tmp.groupby("_ano")["_v"]
    if como == "sum":
        return g.sum().dropna()
    if como == "max":
        return g.max().dropna()
    return g.mean().dropna()


def _agg_atual_hist(
    atual: pd.DataFrame,
    hist: pd.DataFrame,
    col: str,
    *,
    hist_por_ano: bool = False,
) -> tuple[float, float] | None:
    fonte = _col_fonte(col)
    if fonte not in atual.columns or fonte not in hist.columns:
        return None
    serie_a = pd.to_numeric(atual[fonte], errors="coerce")
    serie_h = pd.to_numeric(hist[fonte], errors="coerce")
    if col == "precipitacao_mm_acumulada":
        a = float(serie_a.sum(skipna=True))
        # média dos acumulados anuais no mesmo recorte
        if "data" in hist.columns and hist["data"].notna().any():
            acum_anos = _hist_por_ano(hist, fonte, como="sum")
            if len(acum_anos) < 1:
                return None
            h = float(acum_anos.mean())
        else:
            h = float(serie_h.sum(skipna=True))
    elif col == "tmax_max":
        a = serie_a.max()
        h = serie_h.max()
        if "data" in hist.columns and hist["data"].notna().any():
            picos = _hist_por_ano(hist, fonte, como="max")
            if len(picos) >= 1:
                h = float(picos.mean())
    elif hist_por_ano and "data" in hist.columns and hist["data"].notna().any():
        # YTD / janelas multi-anuais: 1 valor por ano, depois média entre anos
        a = serie_a.mean()
        medias = _hist_por_ano(hist, fonte, como="mean")
        if len(medias) < 1:
            return None
        h = float(medias.mean())
    else:
        a = serie_a.mean()
        h = serie_h.mean()
    if pd.isna(a) or pd.isna(h):
        return None
    return float(a), float(h)


def _zscore_atual_hist(
    atual: pd.DataFrame,
    hist: pd.DataFrame,
    col: str,
    *,
    hist_por_ano: bool = False,
) -> dict[str, float] | None:
    fonte = _col_fonte(col)
    if fonte not in atual.columns or fonte not in hist.columns:
        return None
    if col == "precipitacao_mm_acumulada":
        a = float(pd.to_numeric(atual[fonte], errors="coerce").sum(skipna=True))
        if "data" not in hist.columns:
            return None
        acum_anos = _hist_por_ano(hist, fonte, como="sum")
        if pd.isna(a) or len(acum_anos) < _MIN_ANOS_HIST:
            return None
        mu = float(acum_anos.mean())
        sd = float(acum_anos.std(ddof=0))
        z = float((a - mu) / sd) if sd > 1e-9 else 0.0
        return {
            "atual": float(a),
            "media_historica_mesmo_periodo": mu,
            "desvio_padrao": sd,
            "zscore": z,
            "delta": float(a - mu),
        }
    if col == "tmax_max":
        a = float(pd.to_numeric(atual[fonte], errors="coerce").max())
        como = "max"
    else:
        a = float(pd.to_numeric(atual[fonte], errors="coerce").mean())
        como = "mean"
    if hist_por_ano and "data" in hist.columns and hist["data"].notna().any():
        anos = _hist_por_ano(hist, fonte, como=como)
        if pd.isna(a) or len(anos) < _MIN_ANOS_HIST:
            return None
        mu = float(anos.mean())
        sd = float(anos.std(ddof=0))
        z = float((a - mu) / sd) if sd > 1e-9 else 0.0
        return {
            "atual": float(a),
            "media_historica_mesmo_periodo": mu,
            "desvio_padrao": sd,
            "zscore": z,
            "delta": float(a - mu),
        }
    h_s = pd.to_numeric(hist[fonte], errors="coerce").dropna()
    if pd.isna(a) or len(h_s) < _MIN_DIAS_HIST_MES:
        return None
    mu = float(h_s.mean())
    sd = float(h_s.std(ddof=0))
    z = float((a - mu) / sd) if sd > 1e-9 else 0.0
    return {
        "atual": float(a),
        "media_historica_mesmo_periodo": mu,
        "desvio_padrao": sd,
        "zscore": z,
        "delta": float(a - mu),
    }


def _metrica_disponivel(df: pd.DataFrame, col: str) -> bool:
    return _col_fonte(col) in df.columns


def comparar_janela_atual(
    clima: pd.DataFrame,
    *,
    dias_janela: int = 7,
) -> dict[str, Any]:
    """Compara a janela atual com o **mesmo período calendário** em anos anteriores.

    1. Janela de N dias (MM-DD) × mesmos MM-DD nos anos anteriores.
    2. Mês corrente × o mesmo mês nos anos anteriores (z-score).

    Não publica mais a comparação “janela × restante da série” (meses misturados)
    como leitura sazonal.
    """
    empty = {
        "ok": False,
        "dias_serie": 0,
        "dias_janela": dias_janela,
        "narrativa": "Série ambiental insuficiente para comparação com o histórico.",
        "indicadores": {},
        "periodo_cmp": {"ok": False},
        "mes_cmp": {"ok": False},
    }
    if clima is None or clima.empty or "data" not in clima.columns:
        return empty
    df = clima.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"]).sort_values("data")
    hoje = pd.Timestamp.now().normalize()
    # OBSERVED_DATA_DATE <= REPORT_CUTOFF (hoje−1): não misturar previsão.
    corte = hoje - pd.Timedelta(days=1)
    df_obs = df[df["data"] <= corte]
    if len(df_obs) >= max(dias_janela + 3, 10):
        df = df_obs
    if len(df) < max(dias_janela + 3, 10):
        empty["dias_serie"] = int(len(df))
        return empty

    fim = df["data"].max()
    ini = fim - pd.Timedelta(days=dias_janela - 1)
    atual = df[(df["data"] >= ini) & (df["data"] <= fim)].copy()
    ano = int(fim.year)
    mes = int(fim.month)

    df = df.copy()
    df["_md"] = df["data"].dt.strftime("%m-%d")
    atual_md = set(atual["data"].dt.strftime("%m-%d").tolist())
    hist_periodo = df[(df["data"].dt.year != ano) & (df["_md"].isin(atual_md))].copy()

    periodo_cmp: dict[str, Any] = {
        "ok": False,
        "inicio_janela": str(ini.date()),
        "fim_janela": str(fim.date()),
        "n_dias_atual": int(len(atual)),
        "n_dias_historico": int(len(hist_periodo)),
        "anos_historico": sorted(
            {int(a) for a in hist_periodo["data"].dt.year.dropna().unique().tolist()}
        ),
        "dias_calendario": sorted(atual_md),
    }
    indicadores: dict[str, dict[str, float]] = {}
    n_anos = len(periodo_cmp["anos_historico"])
    if (
        not hist_periodo.empty
        and n_anos >= _MIN_ANOS_HIST
        and len(hist_periodo) >= _MIN_DIAS_HIST_MESMO_PERIODO
    ):
        for col, rotulo in _metricas():
            if not _metrica_disponivel(df, col):
                continue
            pair = _agg_atual_hist(atual, hist_periodo, col)
            if pair is None:
                continue
            a, h = pair
            zinfo = _zscore_atual_hist(atual, hist_periodo, col)
            indicadores[rotulo] = {
                "atual": a,
                "historico": h,
                "delta": float(a - h),
                "zscore": float(zinfo["zscore"]) if zinfo else 0.0,
            }
        if indicadores:
            periodo_cmp["ok"] = True
            periodo_cmp["indicadores"] = indicadores
            periodo_cmp["anos_historico_txt"] = ", ".join(
                str(a) for a in periodo_cmp["anos_historico"]
            )

    # Mês corrente vs mesmo mês em outros anos
    mes_cmp: dict[str, Any] = {"mes": mes, "ano": ano, "ok": False}
    if "tmax_media" in df.columns:
        df_m = df.copy()
        df_m["_mes"] = df_m["data"].dt.month
        df_m["_ano"] = df_m["data"].dt.year
        atual_mes = df_m[(df_m["_mes"] == mes) & (df_m["_ano"] == ano)]
        hist_mes = df_m[(df_m["_mes"] == mes) & (df_m["_ano"] != ano)]
        mes_cmp["n_dias_mes_atual"] = int(len(atual_mes))
        mes_cmp["n_dias_mesmo_mes_historico"] = int(len(hist_mes))
        mes_cmp["anos_historico"] = sorted(
            {int(a) for a in hist_mes["_ano"].dropna().unique().tolist()}
        )
        zscores: dict[str, dict[str, float]] = {}
        for col, rotulo in _metricas():
            if not _metrica_disponivel(df_m, col):
                continue
            zinfo = _zscore_atual_hist(atual_mes, hist_mes, col)
            if not zinfo:
                continue
            # alias legado para consumidores
            zinfo["media_historica_mesmo_mes"] = zinfo["media_historica_mesmo_periodo"]
            zscores[rotulo] = zinfo
        if zscores and len(mes_cmp["anos_historico"]) >= 1:
            mes_cmp["ok"] = True
            mes_cmp["indicadores"] = zscores
            mes_cmp["anos_historico_txt"] = (
                ", ".join(str(a) for a in mes_cmp["anos_historico"]) or "sem anos anteriores"
            )

    mes_nome = [
        "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ][mes]

    partes: list[str] = []

    # 1) Janela N dias — mesmo período calendário
    if periodo_cmp.get("ok") and indicadores:
        com_desvio = [
            (r, v) for r, v in indicadores.items() if abs(float(v.get("zscore") or 0)) >= 1.0
        ]
        sem_desvio = [
            (r, v) for r, v in indicadores.items() if abs(float(v.get("zscore") or 0)) < 1.0
        ]
        linhas = [
            f"**Comparação no mesmo período do calendário "
            f"({ini.strftime('%d/%m')}–{fim.strftime('%d/%m')}/{ano})**",
            "",
            (
                f"Janela atual ({ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}) "
                f"frente aos **mesmos dias do calendário** nos anos "
                f"**{periodo_cmp.get('anos_historico_txt')}** "
                f"({periodo_cmp['n_dias_historico']} dias históricos no recorte)."
            ),
            "",
            "_Critério: |z| ≥ 1 = desvio relevante frente ao padrão do mesmo período. "
            "Não mistura meses diferentes. Não substitui climatologia oficial (INMET/INPE)._",
            "",
        ]
        for rot, v in indicadores.items():
            linhas.append(
                f"- **{rot}:** {v['atual']:.1f} agora vs {v['historico']:.1f} "
                f"no mesmo período histórico (Δ {v['delta']:+.1f}"
                + (f"; z={v['zscore']:+.2f}" if v.get("zscore") is not None else "")
                + ")."
            )
        if com_desvio:
            linhas.extend(["", "**Variáveis com desvio (|z|≥1):**"])
            for rot, v in com_desvio:
                linhas.append(
                    f"- **{rot}:** {_sentido_desvio_sazonal(rot, float(v['zscore']))}."
                )
        periodo_cmp["houve_desvio"] = bool(com_desvio)
        periodo_cmp["variaveis_com_desvio"] = [r for r, _ in com_desvio]
        periodo_cmp["variaveis_sem_desvio"] = [r for r, _ in sem_desvio]
        partes.append("\n".join(linhas))
    else:
        anos_disp = sorted({int(a) for a in df["data"].dt.year.dropna().unique().tolist()})
        partes.append(
            "**Comparação no mesmo período do calendário — indisponível nesta rodada**\n\n"
            f"A janela {ini.strftime('%d/%m/%Y')}–{fim.strftime('%d/%m/%Y')} exige "
            f"os **mesmos dias MM-DD** em pelo menos {_MIN_ANOS_HIST} anos anteriores "
            f"na série operacional. "
            f"Anos disponíveis hoje: {', '.join(str(a) for a in anos_disp) or '—'}. "
            f"Histórico no recorte: {periodo_cmp['n_dias_historico']} dia(s) em "
            f"{n_anos} ano(s). "
            "Alongar `hist_clima_municipal_diario` (~5 anos via Open-Meteo Archive) "
            "antes de republicar a leitura sazonal. "
            "**Não** se usa média de meses misturados como substituto."
        )

    # 2) Mês corrente × mesmos meses
    if mes_cmp.get("ok") and mes_cmp.get("indicadores"):
        zscores = mes_cmp["indicadores"]
        com_desvio_m: list[tuple[str, dict[str, float]]] = []
        sem_desvio_m: list[tuple[str, dict[str, float]]] = []
        for rot, v in zscores.items():
            (com_desvio_m if abs(float(v["zscore"])) >= 1.0 else sem_desvio_m).append((rot, v))

        houve = bool(com_desvio_m)
        if houve:
            nomes = "; ".join(r for r, _ in com_desvio_m)
            resposta = (
                f"**Sim** — houve desvio sazonal relevante em "
                f"**{len(com_desvio_m)}** variável(eis): {nomes}."
            )
        else:
            resposta = (
                "**Não** — nenhuma das variáveis analisadas saiu do padrão típico "
                f"de {mes_nome} na série operacional (|z| < 1)."
            )

        linhas = [
            f"**Leitura sazonal — {mes_nome}/{ano} (mesmo mês em anos anteriores)**",
            "",
            (
                f"Comparamos o que já se observou em {mes_nome}/{ano} com o **mesmo mês** "
                f"nos anos anteriores da série operacional "
                f"({mes_cmp.get('anos_historico_txt')})."
            ),
            "",
            f"**Houve desvio de sazonalidade?** {resposta}",
            "",
            "_Critério: |z| ≥ 1 = desvio relevante frente ao padrão do mesmo mês. "
            "Série operacional ARARAS — não substitui climatologia oficial (INMET/INPE)._",
        ]

        if com_desvio_m:
            linhas.extend(["", "**Variáveis com desvio:**"])
            for rot, v in com_desvio_m:
                mu = v.get("media_historica_mesmo_mes", v.get("media_historica_mesmo_periodo"))
                linhas.append(
                    f"- **{rot}:** {v['atual']:.1f} agora vs média {mu:.1f} "
                    f"nos {mes_nome}s anteriores "
                    f"({_sentido_desvio_sazonal(rot, float(v['zscore']))}; z={v['zscore']:+.2f})."
                )
        if sem_desvio_m:
            linhas.extend(["", "**Variáveis no padrão esperado do mês:**"])
            for rot, v in sem_desvio_m:
                mu = v.get("media_historica_mesmo_mes", v.get("media_historica_mesmo_periodo"))
                linhas.append(
                    f"- **{rot}:** {v['atual']:.1f} vs média {mu:.1f} "
                    f"(z={v['zscore']:+.2f})."
                )

        mes_cmp["houve_desvio"] = houve
        mes_cmp["variaveis_com_desvio"] = [r for r, _ in com_desvio_m]
        mes_cmp["variaveis_sem_desvio"] = [r for r, _ in sem_desvio_m]
        mes_cmp["narrativa"] = "\n".join(linhas)
        partes.append(mes_cmp["narrativa"])

    # 3) Acumulado do ano (YTD) × mesmo intervalo Jan–MM/DD nos anos anteriores
    ytd_cmp: dict[str, Any] = {"ok": False}
    ini_ytd = pd.Timestamp(year=ano, month=1, day=1)
    atual_ytd = df[(df["data"] >= ini_ytd) & (df["data"] <= fim)].copy()
    md_fim = fim.strftime("%m-%d")
    hist_ytd_parts: list[pd.DataFrame] = []
    anos_ytd: list[int] = []
    for a in sorted({int(x) for x in df["data"].dt.year.dropna().unique().tolist()}):
        if a >= ano:
            continue
        ini_a = pd.Timestamp(year=a, month=1, day=1)
        try:
            fim_a = pd.Timestamp(year=a, month=fim.month, day=fim.day)
        except ValueError:
            # 29/02 em ano não-bissexto
            fim_a = pd.Timestamp(year=a, month=fim.month, day=28)
        chunk = df[(df["data"] >= ini_a) & (df["data"] <= fim_a)].copy()
        if len(chunk) >= _MIN_DIAS_HIST_MES:
            hist_ytd_parts.append(chunk)
            anos_ytd.append(a)
    hist_ytd = pd.concat(hist_ytd_parts, ignore_index=True) if hist_ytd_parts else pd.DataFrame()
    ytd_cmp.update(
        {
            "inicio": str(ini_ytd.date()),
            "fim": str(fim.date()),
            "n_dias_atual": int(len(atual_ytd)),
            "n_dias_historico": int(len(hist_ytd)),
            "anos_historico": anos_ytd,
            "anos_historico_txt": ", ".join(str(a) for a in anos_ytd) or "—",
            "md_corte": md_fim,
        }
    )
    ind_ytd: dict[str, dict[str, float]] = {}
    if (
        len(atual_ytd) >= _MIN_DIAS_HIST_MES
        and len(anos_ytd) >= _MIN_ANOS_HIST
        and len(hist_ytd) >= _MIN_DIAS_HIST_MESMO_PERIODO
    ):
        for col, rotulo in _metricas():
            if not _metrica_disponivel(df, col):
                continue
            # YTD: 1 observação por ano histórico (não pool de dias entre anos)
            pair = _agg_atual_hist(atual_ytd, hist_ytd, col, hist_por_ano=True)
            if pair is None:
                continue
            a_v, h_v = pair
            zinfo = _zscore_atual_hist(atual_ytd, hist_ytd, col, hist_por_ano=True)
            ind_ytd[rotulo] = {
                "atual": a_v,
                "historico": h_v,
                "delta": float(a_v - h_v),
                "zscore": float(zinfo["zscore"]) if zinfo else 0.0,
            }
        if ind_ytd:
            ytd_cmp["ok"] = True
            ytd_cmp["indicadores"] = ind_ytd
            com_d = [(r, v) for r, v in ind_ytd.items() if abs(float(v.get("zscore") or 0)) >= 1.0]
            linhas_y = [
                f"**Acumulado do ano (YTD) — 01/01/{ano} a {fim.strftime('%d/%m/%Y')}**",
                "",
                (
                    f"Mesmo intervalo calendário (1º jan → {fim.strftime('%d/%m')}) "
                    f"nos anos **{ytd_cmp['anos_historico_txt']}** "
                    f"({ytd_cmp['n_dias_historico']} dias históricos)."
                ),
                "",
                "_Critério: |z| ≥ 1 = desvio relevante. Não mistura meses fora do intervalo._",
                "",
            ]
            for rot, v in ind_ytd.items():
                linhas_y.append(
                    f"- **{rot}:** {v['atual']:.1f} em {ano} vs {v['historico']:.1f} "
                    f"no mesmo YTD histórico (Δ {v['delta']:+.1f}"
                    + (f"; z={v['zscore']:+.2f}" if v.get("zscore") is not None else "")
                    + ")."
                )
            if com_d:
                linhas_y.extend(["", "**Variáveis com desvio no YTD (|z|≥1):**"])
                for rot, v in com_d:
                    linhas_y.append(
                        f"- **{rot}:** {_sentido_desvio_sazonal(rot, float(v['zscore']))}."
                    )
            ytd_cmp["houve_desvio"] = bool(com_d)
            ytd_cmp["variaveis_com_desvio"] = [r for r, _ in com_d]
            ytd_cmp["narrativa"] = "\n".join(linhas_y)
            partes.append(ytd_cmp["narrativa"])

    if not partes:
        return empty
    return {
        "ok": True,  # narrativa sempre publicada (mesmo período ou lacuna explícita)
        "dias_serie": int(len(df)),
        "dias_janela": dias_janela,
        "inicio_janela": str(ini.date()),
        "fim_janela": str(fim.date()),
        "indicadores": indicadores,
        "periodo_cmp": periodo_cmp,
        "mes_cmp": mes_cmp,
        "ytd_cmp": ytd_cmp,
        "narrativa": "\n\n".join(p.strip() for p in partes if str(p).strip()).strip(),
        "comparacao_mesmo_periodo": bool(periodo_cmp.get("ok")),
    }


def _pick_ind(inds: dict[str, Any] | None, *keys: str) -> dict[str, float] | None:
    if not inds:
        return None
    for k in keys:
        if k in inds:
            return inds[k]
    return None


def _resposta_desvio(v: dict[str, float] | None, *, positivo_mais: str, negativo_mais: str, neutro: str) -> str:
    if not v:
        return "dados insuficientes nesta rodada para responder com o histórico operacional."
    z = float(v.get("zscore") or 0)
    atual = float(v.get("atual") or 0)
    hist = float(v.get("historico") or v.get("media_historica_mesmo_periodo") or 0)
    delta = float(v.get("delta") or (atual - hist))
    if abs(z) < 1.0:
        return (
            f"**Não** — {neutro} "
            f"({atual:.1f} vs {hist:.1f} no mesmo período; Δ {delta:+.1f}; z={z:+.2f})."
        )
    sentido = positivo_mais if z > 0 else negativo_mais
    return (
        f"**Sim** — {sentido} "
        f"({atual:.1f} vs {hist:.1f}; Δ {delta:+.1f}; z={z:+.2f})."
    )


def narrativa_qa_el_nino_clima(
    cmp_: dict[str, Any],
    *,
    enso: dict[str, Any] | None = None,
) -> str:
    """Bloco Q&A leigo: calor, chuva YTD, chuva da época e contexto ENSO."""
    enso = enso or {}
    ytd = (cmp_.get("ytd_cmp") or {}) if cmp_ else {}
    mes = (cmp_.get("mes_cmp") or {}) if cmp_ else {}
    periodo = (cmp_.get("periodo_cmp") or {}) if cmp_ else {}
    ind_ytd = ytd.get("indicadores") or {}
    ind_mes = mes.get("indicadores") or {}
    ind_janela = periodo.get("indicadores") or cmp_.get("indicadores") or {}

    tmax_ytd = _pick_ind(ind_ytd, "Tmáx média (°C)")
    utci_ytd = _pick_ind(ind_ytd, "UTCI médio")
    # Preferir o indicador com maior |z| entre Tmáx e UTCI para a resposta de calor
    calor = tmax_ytd
    if utci_ytd and (
        calor is None or abs(float(utci_ytd.get("zscore") or 0)) > abs(float(calor.get("zscore") or 0))
    ):
        calor = utci_ytd
    if calor is None:
        calor = _pick_ind(ind_mes, "Tmáx média (°C)", "UTCI médio")

    chuva_ytd = _pick_ind(ind_ytd, "Precipitação acumulada (mm)", "Precipitação média (mm)")
    chuva_epoca = _pick_ind(
        ind_mes, "Precipitação acumulada (mm)", "Precipitação média (mm)"
    ) or _pick_ind(ind_janela, "Precipitação acumulada (mm)", "Precipitação média (mm)")
    amp = _pick_ind(ind_ytd, "Amplitude térmica média (°C)") or _pick_ind(
        ind_mes, "Amplitude térmica média (°C)"
    )

    status = str(enso.get("status") or enso.get("estado") or enso.get("fase") or "").strip()
    nino34 = str(enso.get("nino34_recente") or enso.get("nino34") or "").strip()
    intensidade = str(enso.get("intensidade") or "").strip()
    enso_bits = [b for b in (status, nino34, intensidade) if b and b not in {"—", "nan", "None"}]
    enso_txt = " · ".join(enso_bits) if enso_bits else "conforme Painel El Niño / cenário oficial da rodada"

    linhas = [
        "**Perguntas frequentes — El Niño × clima operacional (MT)**",
        "",
        (
            "_Comparação com o **mesmo período do calendário** na série operacional ARARAS "
            "(~5 anos). Não prova que o El Niño *causou* o desvio; situa 2026 no cenário ENSO "
            "da rodada. Não substitui climatologia oficial (INMET/INPE). Critério: |z| ≥ 1._"
        ),
        "",
        f"**1. Este ano está mais quente?** {_resposta_desvio(calor, positivo_mais='está mais quente que o padrão do mesmo YTD/mês', negativo_mais='está mais ameno que o padrão do mesmo YTD/mês', neutro='a temperatura fica no padrão do mesmo período')}",
        "",
        f"**2. Este ano choveu mais?** {_resposta_desvio(chuva_ytd, positivo_mais='o acumulado de chuva no YTD está acima do padrão do mesmo intervalo em anos anteriores', negativo_mais='o acumulado de chuva no YTD está abaixo do padrão do mesmo intervalo em anos anteriores', neutro='o acumulado de chuva no YTD fica no padrão do mesmo intervalo')}",
        "",
        f"**3. As chuvas desta época do ano são comuns?** {_resposta_desvio(chuva_epoca, positivo_mais='choveu mais do que o típico nesta época (mês/janela) na série operacional', negativo_mais='choveu menos do que o típico nesta época (mês/janela) na série operacional', neutro='a chuva desta época está dentro do padrão esperado para o período')}",
        "",
    ]
    if amp:
        linhas.append(
            f"**Amplitude térmica (dia/noite):** {_resposta_desvio(amp, positivo_mais='amplitude maior que o padrão', negativo_mais='amplitude menor que o padrão', neutro='amplitude no padrão do período')}"
        )
        linhas.append("")
    linhas.extend(
        [
            f"**4. Como isso se situa no cenário ENSO / El Niño?** No ano sob cenário **{enso_txt}**, "
            "a série operacional acima descreve o comportamento de calor e chuva frente aos mesmos "
            "períodos em anos anteriores. A atribuição causal ao El Niño exige análise climática "
            "oficial (INMET/INPE/CPTEC) — o ARARAS apenas contextualiza a vigilância em saúde.",
        ]
    )
    return "\n".join(linhas)


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
                "\n\n**Qualidade do ar (série estadual)**\n\n"
                f"PM2,5 média {float(pm.mean()):.1f} µg/m³ "
                f"(máximo {float(pm.max()):.1f} µg/m³; {len(ar)} dias na série)."
            )
    enso: dict[str, Any] = {}
    try:
        from sisclima.engines.boletim_el_nino.cenario import load_cenario_oficial

        cen = load_cenario_oficial() or {}
        enso = cen.get("enso") or {}
    except Exception:  # noqa: BLE001
        enso = {}
    qa = narrativa_qa_el_nino_clima(cmp_, enso=enso)
    md = cmp_.get("narrativa") or "Série ambiental operacional ainda curta para comparação robusta."
    if qa:
        md = (md.rstrip() + "\n\n" + qa).strip()
    if ar_txt:
        md = (md.rstrip() + ar_txt).strip()
    return {
        "clima": clima,
        "ar": ar,
        "comparacao": cmp_,
        "qa_el_nino_clima": qa,
        "markdown": md,
        "ok": bool(cmp_.get("ok") or (ar is not None and not ar.empty)),
    }
