# -*- coding: utf-8 -*-
"""Aba Sazonalidade / OR — destaque de significância + dados frescos."""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import plotly.express as px
import streamlit as st

from sisclima.engines.sazonalidade_frescor import load_sazonalidade_fresco
from sisclima.ui import theme as ui_theme

LEVEL_COLOR_MAP = {
    "verde": "#2E7D32",
    "amarelo": "#F9A825",
    "laranja": "#EF6C00",
    "vermelho": "#C62828",
    "roxo": "#6A1B9A",
}


def _fmt_ts(ts: Any) -> str:
    if ts is None:
        return "—"
    try:
        return pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def _sig_mask(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty or "significativo_005" not in df.columns:
        return pd.Series(dtype=bool)
    return pd.to_numeric(df["significativo_005"], errors="coerce").fillna(0).astype(int).eq(1)


def _style_or_sig(row: pd.Series) -> list[str]:
    sig = False
    if "significativo_005" in row.index:
        try:
            sig = bool(int(float(row["significativo_005"])))
        except Exception:
            sig = bool(row["significativo_005"])
    if not sig:
        return [""] * len(row)
    return ["background-color: #FFF3E0; font-weight: 600"] * len(row)


def render_sazonalidade_or(
    *,
    resumo: pd.DataFrame,
    publico: bool = False,
    show_df: Callable[..., None] | None = None,
    render_interpretacao: Callable[..., None] | None = None,
    guide: str | None = None,
    narrativa_fn: Callable[[pd.DataFrame, pd.DataFrame], str] | None = None,
    persist: bool = True,
    max_age_hours: float = 24.0,
) -> None:
    """Renderiza a aba com OR ao vivo e sazonalidade/lags atualizados."""
    ui_theme.section_title(
        "Sazonalidade e Odds Ratio",
        "Padrão histórico e chance relativa clima–agravos — com destaque estatístico",
    )
    ui_theme.callout(
        "Esta aba descreve padrão histórico e chance relativa entre grupos de municípios. "
        "Não prova que o clima causou o caso individual. Resultados com p < 0,05 aparecem em destaque.",
        "info",
    )

    with st.spinner("Atualizando sazonalidade e OR…"):
        pack = load_sazonalidade_fresco(
            resumo,
            persist=persist,
            max_age_hours=max_age_hours,
        )

    odds = pack.get("odds") if isinstance(pack.get("odds"), pd.DataFrame) else pd.DataFrame()
    mensal = pack.get("mensal") if isinstance(pack.get("mensal"), pd.DataFrame) else pd.DataFrame()
    heat = pack.get("heatmap") if isinstance(pack.get("heatmap"), pd.DataFrame) else pd.DataFrame()
    picos = pack.get("picos") if isinstance(pack.get("picos"), pd.DataFrame) else pd.DataFrame()
    lags = pack.get("lags") if isinstance(pack.get("lags"), pd.DataFrame) else pd.DataFrame()
    meta = pack.get("meta") or {}

    # Contexto ambiental (temp / umidade vs sazão)
    try:
        from sisclima.engines.serie_historica_ambiente import resumo_serie_ambiente_boletim

        amb = resumo_serie_ambiente_boletim()
        cmp_ = amb.get("comparacao") or {}
        if cmp_.get("ok"):
            ui_theme.section_title(
                "Situação atual × série ambiental",
                "Desvio da janela de 7 dias e z-score do mês corrente vs mesmo mês em anos anteriores",
            )
            ui_theme.callout(str(cmp_.get("narrativa") or ""), "warn")
            mes = cmp_.get("mes_cmp") or {}
            if mes.get("ok") and mes.get("indicadores"):
                cards = []
                for rot, vals in mes["indicadores"].items():
                    z = float(vals.get("zscore") or 0)
                    destaque = " · |z|≥1" if abs(z) >= 1.0 else ""
                    cards.append(
                        (
                            rot,
                            f"z={z:+.2f}{destaque}",
                            f"{vals['atual']:.1f} vs {vals['media_historica_mesmo_mes']:.1f}",
                        )
                    )
                # prioriza umidade e temperatura no topo
                def _prio(item: tuple) -> int:
                    nome = str(item[0]).lower()
                    if "umidade" in nome:
                        return 0
                    if "tmáx" in nome or "tmax" in nome:
                        return 1
                    return 2

                cards = sorted(cards, key=_prio)
                if cards:
                    ui_theme.insight_cards(cards[:6])
            st.caption(
                "Detalhe gráfico na aba **Série ambiental**. "
                "|z| ≥ 1 = desvio relevante do padrão do mês (ex.: temperatura mais amena ou umidade acima do esperado)."
            )
    except Exception:
        pass

    st.caption(
        f"Frescor — OR: {_fmt_ts(meta.get('or_proc'))} · "
        f"Sazonalidade/lags: {_fmt_ts(meta.get('saz_proc'))} · "
        f"OR sig.: {meta.get('or_sig', 0)}/{meta.get('or_n', 0)} · "
        f"Lags sig.: {meta.get('lag_sig', 0)} · "
        f"Clima: {meta.get('clima_n', 0)}/{meta.get('clima_catalogo', 0)} vars"
    )

    # Cobertura Open-Meteo + Copernicus
    cov_src = pack.get("cobertura_fontes") or {}
    cobertura = pack.get("cobertura") if isinstance(pack.get("cobertura"), pd.DataFrame) else pd.DataFrame()
    st.markdown("#### Cobertura climática (Open-Meteo + Copernicus/CAMS)")
    om = cov_src.get("openmeteo") or []
    cp = cov_src.get("copernicus") or []
    der = cov_src.get("derivados") or []
    from sisclima.engines.clima_exposicoes import CLIMA_ROTULOS

    def _lbls(cols: list) -> str:
        return ", ".join(CLIMA_ROTULOS.get(c, c) for c in cols) if cols else "—"

    c_om, c_cp, c_der = st.columns(3)
    c_om.metric("Open-Meteo", len(om))
    c_cp.metric("Copernicus / IQA", len(cp))
    c_der.metric("Derivados ARARAS", len(der))
    if om or cp or der:
        st.caption(
            f"**Open-Meteo:** {_lbls(om)}  \n"
            f"**Copernicus/CAMS + IQA:** {_lbls(cp)}  \n"
            f"**Derivados:** {_lbls(der)}"
        )
    faltando = cov_src.get("faltando_catalogo") or []
    if faltando:
        st.caption(
            "Ainda sem dados nesta rodada (fonte offline ou série curta): "
            + ", ".join(CLIMA_ROTULOS.get(c, c) for c in faltando[:12])
            + ("…" if len(faltando) > 12 else "")
        )
    if not cobertura.empty and not publico:
        with st.expander("Inventário detalhado da série sazonal (dias válidos)"):
            show_cols = [c for c in ["variavel", "n_dias_validos", "media", "data_processamento"] if c in cobertura.columns]
            if show_df:
                show_df(cobertura, show_cols, height=220)
            else:
                st.dataframe(cobertura[show_cols], use_container_width=True, height=220)

    st.markdown(
        """
**Como ler estes dados**

1. **Índice sazonal mensal** — acima de 1 o mês é historicamente mais crítico do que a média do período.
2. **Heatmap semana × ano** — cores mais quentes indicam semanas em que o indicador costuma subir.
3. **Odds Ratio (OR)** — OR > 1 sugere maior chance do desfecho no grupo mais exposto; destaque = p < 0,05.
4. **Lags (0–14 dias)** — defasagem clima→desfecho; pontos/linhas com p < 0,05 são hipóteses prioritárias (não causalidade).
        """
    )

    if not publico:
        ui_theme.callout(
            "Odds Ratio e correlações temporais são análises ecológicas exploratórias: "
            "ajudam na priorização, não comprovam causalidade individual.",
            "warn",
        )
        if render_interpretacao and guide and narrativa_fn:
            render_interpretacao(
                "sazonal_or",
                guide,
                lambda: narrativa_fn(odds, mensal),
            )
        st.markdown(
            "- Análise ecológica de sazonalidade e odds ratio clima–agravos do ARARAS "
            "(calor, umidade, arboviroses, SRAG, ocupação).  \n"
            "- Documento local: `docs/ANALISE_OR_SAZONALIDADE.md`."
        )

    if mensal.empty and heat.empty and odds.empty and lags.empty:
        st.info(
            "Sazonalidade e odds ratio ainda não disponíveis neste recorte."
            if publico
            else "Tabelas de sazonalidade/OR ainda não geradas. Rode completar_sistema_operacional.py "
            "ou aguarde o refresh automático desta aba."
        )
        return

    c1, c2, c3, c4 = st.columns(4)
    if not mensal.empty and "indice_sazonal" in mensal.columns:
        top = mensal.sort_values("indice_sazonal", ascending=False).head(1)
        c1.metric("Mês de pico sazonal", str(top["mes_rotulo"].iloc[0]) if not top.empty else "—")
    else:
        c1.metric("Mês de pico sazonal", "—")

    if not picos.empty:
        se = picos[picos["tipo"] == "se_atual_vs_media"].head(1)
        if (
            not se.empty
            and pd.notna(se.get("valor_atual").iloc[0])
            and pd.notna(se.get("valor_medio_historico").iloc[0])
        ):
            atual = float(se["valor_atual"].iloc[0])
            media = float(se["valor_medio_historico"].iloc[0])
            c2.metric("SE atual vs média", f"{atual:.2f}", delta=f"{(atual - media):+.2f}")
        else:
            c2.metric("SE atual vs média", "—")
    else:
        c2.metric("SE atual vs média", "—")

    n_or_sig = int(_sig_mask(odds).sum()) if not odds.empty else 0
    n_lag_sig = int(_sig_mask(lags).sum()) if not lags.empty else 0
    c3.metric("OR significativos (p<0,05)", n_or_sig)
    c4.metric("Lags significativos (p<0,05)", n_lag_sig)

    # Destaque: pares OR significativos
    st.markdown("#### Em destaque — OR com significância estatística (p < 0,05)")
    if not odds.empty and n_or_sig > 0:
        sig_or = odds.loc[_sig_mask(odds)].copy()
        sig_or["or"] = pd.to_numeric(sig_or["or"], errors="coerce")
        sig_or = sig_or.sort_values("or", ascending=False)
        cards_or = []
        for _, r in sig_or.head(6).iterrows():
            orv = float(r["or"]) if pd.notna(r.get("or")) else float("nan")
            p = float(r["p_value"]) if pd.notna(r.get("p_value")) else float("nan")
            cards_or.append(
                (
                    f"{r.get('exposicao', '—')} → {r.get('desfecho', '—')}",
                    f"OR {orv:.2f}" if pd.notna(orv) else "OR —",
                    f"p={p:.3g}"
                    + (
                        f" · IC95 [{float(r['ic95_inferior']):.2f}; {float(r['ic95_superior']):.2f}]"
                        if pd.notna(r.get("ic95_inferior")) and pd.notna(r.get("ic95_superior"))
                        else ""
                    ),
                )
            )
        ui_theme.insight_cards(cards_or)
        ui_theme.callout(
            "Priorize vigilância nos pares destacados (exposição–desfecho). "
            "Com tempestades e umidade acima do esperado, revise especialmente precipitações/umidade × arboviroses e SRAG.",
            "tip",
        )
    else:
        st.info("Nenhum OR com p < 0,05 nesta rodada (ou amostra insuficiente para Fisher).")

    st.markdown("#### Índice sazonal mensal")
    if not mensal.empty:
        sm = mensal.copy()
        sm["indice_sazonal"] = pd.to_numeric(sm["indice_sazonal"], errors="coerce")
        fig = px.bar(
            sm.sort_values("mes"),
            x="mes_rotulo",
            y="indice_sazonal",
            color="acima_media" if "acima_media" in sm.columns else None,
            color_discrete_map={True: LEVEL_COLOR_MAP["laranja"], False: LEVEL_COLOR_MAP["verde"]},
            title="Índice sazonal mensal (acima de 1 = acima da média histórica)",
        )
        fig.add_hline(y=1.0, line_dash="dash")
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem série mensal para índice sazonal.")

    st.markdown("#### Heatmap semana epidemiológica × ano")
    if not heat.empty:
        h = heat.copy()
        h["valor"] = pd.to_numeric(h["valor"], errors="coerce")
        mat = h.pivot_table(index="ano_epi", columns="semana_epi", values="valor", aggfunc="mean")
        if not mat.empty:
            fig_h = px.imshow(
                mat,
                aspect="auto",
                color_continuous_scale="YlOrRd",
                title="Heatmap sazonal (SE × ano)",
                labels={"x": "Semana epidemiológica", "y": "Ano epidemiológico", "color": "valor"},
            )
            st.plotly_chart(fig_h, use_container_width=True)
        else:
            st.info("Heatmap vazio nesta rodada.")
    else:
        st.info("Sem dados para heatmap sazonal.")

    st.markdown("#### Odds Ratio clima–agravos/ocupação")
    so_sig = st.checkbox("Mostrar apenas OR significativos (p < 0,05)", value=False, key="sazon_or_only_sig")
    if not odds.empty:
        or_df = odds.copy()
        if so_sig and "significativo_005" in or_df.columns:
            or_df = or_df.loc[_sig_mask(or_df)]
        if "significativo_005" in or_df.columns:
            or_df = or_df.sort_values(["significativo_005", "or"], ascending=[False, False])
        cols = [
            c
            for c in [
                "exposicao",
                "desfecho",
                "n_analisado",
                "limiar_exposicao",
                "limiar_desfecho",
                "or",
                "ic95_inferior",
                "ic95_superior",
                "p_value",
                "significativo_005",
                "interpretacao",
            ]
            if c in or_df.columns
        ]
        if show_df and not or_df.empty:
            try:
                styled = or_df[cols].style.apply(_style_or_sig, axis=1)
                st.dataframe(styled, use_container_width=True, height=340)
            except Exception:
                show_df(or_df, cols, height=340)
        elif not or_df.empty:
            st.dataframe(or_df[cols], use_container_width=True, height=340)
        else:
            st.info("Filtro sem linhas — desmarque 'apenas significativos' para ver todos.")
    else:
        st.info("Sem OR calculado nesta rodada.")

    st.markdown("#### Lags clima–desfecho (0–14 dias)")
    so_lag_sig = st.checkbox(
        "Destacar / filtrar lags significativos (p < 0,05)",
        value=True,
        key="sazon_lag_only_sig",
    )
    if not lags.empty:
        lg = lags.copy()
        lg["lag_dias"] = pd.to_numeric(lg["lag_dias"], errors="coerce")
        lg["abs_spearman"] = pd.to_numeric(lg["abs_spearman"], errors="coerce")
        if "significativo_005" not in lg.columns and "p_value" in lg.columns:
            lg["significativo_005"] = pd.to_numeric(lg["p_value"], errors="coerce").lt(0.05)
        if so_lag_sig and "significativo_005" in lg.columns and _sig_mask(lg).any():
            lg_plot = lg.loc[_sig_mask(lg)].copy()
            if lg_plot.empty:
                lg_plot = lg.head(150)
        else:
            lg_plot = lg.head(150)
        # cor por significância quando disponível
        if "significativo_005" in lg_plot.columns:
            lg_plot["_sig_label"] = _sig_mask(lg_plot).map({True: "p<0,05", False: "n.s."})
            color_col = "_sig_label"
        else:
            color_col = "desfecho"
        fig_l = px.scatter(
            lg_plot,
            x="lag_dias",
            y="abs_spearman",
            color=color_col,
            symbol="exposicao",
            title="Força da correlação temporal por lag (|Spearman|)",
            hover_data=[
                c
                for c in ["exposicao", "desfecho", "spearman", "pearson", "p_value", "n_dias_validos"]
                if c in lg_plot.columns
            ],
            color_discrete_map={"p<0,05": LEVEL_COLOR_MAP["laranja"], "n.s.": "#90A4AE"},
        )
        st.plotly_chart(fig_l, use_container_width=True)

        if n_lag_sig > 0:
            st.markdown("##### Melhores lags significativos")
            best = lg.loc[_sig_mask(lg)].sort_values("abs_spearman", ascending=False).head(12)
            cards_l = []
            for _, r in best.head(6).iterrows():
                cards_l.append(
                    (
                        f"{r.get('exposicao')} → {r.get('desfecho')}",
                        f"lag {int(r['lag_dias'])}d",
                        f"|ρ|={float(r['abs_spearman']):.2f} · p={float(r['p_value']):.3g}"
                        if pd.notna(r.get("p_value"))
                        else f"|ρ|={float(r['abs_spearman']):.2f}",
                    )
                )
            if cards_l:
                ui_theme.insight_cards(cards_l)

        tbl = lg.sort_values(
            ["significativo_005", "abs_spearman", "n_dias_validos"]
            if "significativo_005" in lg.columns
            else ["abs_spearman", "n_dias_validos"],
            ascending=[False, False, False] if "significativo_005" in lg.columns else [False, False],
        )
        if so_lag_sig and "significativo_005" in tbl.columns:
            tbl_show = tbl.loc[_sig_mask(tbl)]
            if tbl_show.empty:
                tbl_show = tbl.head(80)
        else:
            tbl_show = tbl.head(80)
        lag_cols = [
            c
            for c in [
                "exposicao",
                "desfecho",
                "lag_dias",
                "spearman",
                "pearson",
                "abs_spearman",
                "p_value",
                "significativo_005",
                "n_dias_validos",
            ]
            if c in tbl_show.columns
        ]
        if show_df:
            show_df(tbl_show, lag_cols, height=300)
        else:
            st.dataframe(tbl_show[lag_cols], use_container_width=True, height=300)
    else:
        st.info("Sem tabela de lags nesta rodada.")

    if not publico:
        ui_theme.glossary_expander(
            ["indice_sazonal", "odds_ratio", "ocupacao_leitos_pct", "pressao_calor_pct"]
        )
