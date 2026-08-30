# -*- coding: utf-8 -*-
"""Aba pública/restrita: série histórica ambiental e comparação com a janela atual."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from sisclima.engines.serie_historica_ambiente import resumo_serie_ambiente_boletim
from sisclima.ui.theme import callout, insight_cards, section_title


def render_serie_historica_ambiente(*, publico: bool = True) -> None:
    section_title(
        "Série histórica ambiental",
        "Clima e qualidade do ar no tempo — comparar a semana atual com a série disponível",
    )
    callout(
        "Série operacional do ARARAS (Open-Meteo / consolidação estadual). "
        "Não substitui climatologia oficial de longo prazo do INMET/INPE. "
        "Desvios positivos em calor ou PM2,5 indicam condição mais crítica que a média da série.",
        "info",
    )

    pack = resumo_serie_ambiente_boletim()
    clima = pack.get("clima") if isinstance(pack.get("clima"), pd.DataFrame) else pd.DataFrame()
    ar = pack.get("ar") if isinstance(pack.get("ar"), pd.DataFrame) else pd.DataFrame()
    cmp_ = pack.get("comparacao") or {}

    if cmp_.get("ok"):
        callout(str(cmp_.get("narrativa") or ""), "warn" if _delta_critico(cmp_) else "tip")
        cards = []
        for rot, vals in (cmp_.get("indicadores") or {}).items():
            cards.append(
                (
                    rot,
                    f"{vals['atual']:.1f}",
                    f"hist. {vals['historico']:.1f} · Δ {vals['delta']:+.1f}",
                )
            )
        if cards:
            insight_cards(cards[:6])
    else:
        callout(str(pack.get("markdown") or cmp_.get("narrativa") or "Série ainda curta."), "warn")

    st.markdown("#### Temperatura e estresse térmico (média estadual diária)")
    if clima is not None and not clima.empty:
        plot_cols = [c for c in ("tmax_media", "tmax_max", "utci_proxy_media") if c in clima.columns]
        if plot_cols:
            long = clima.melt(
                id_vars=["data"],
                value_vars=plot_cols,
                var_name="indicador",
                value_name="valor",
            )
            fig = px.line(
                long,
                x="data",
                y="valor",
                color="indicador",
                title="Série estadual — temperatura e UTCI",
            )
            # marca janela atual
            if cmp_.get("inicio_janela"):
                fig.add_vline(x=cmp_["inicio_janela"], line_dash="dot")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Colunas climáticas indisponíveis nesta rodada.")
        if not publico and "risco_cumulativo_3d_media" in clima.columns:
            fig_r = px.line(
                clima,
                x="data",
                y="risco_cumulativo_3d_media",
                title="Risco cumulativo 3 dias (média estadual)",
            )
            st.plotly_chart(fig_r, use_container_width=True)
    else:
        st.info("Tabela met_biometeo sem série agregável nesta rodada.")

    st.markdown("#### Qualidade do ar (série estadual)")
    if ar is not None and not ar.empty:
        y_cols = [c for c in ("pm25_ugm3", "pm10_ugm3", "o3_ugm3", "iq_ar_score") if c in ar.columns]
        if y_cols and "data" in ar.columns:
            long = ar.melt(id_vars=["data"], value_vars=y_cols, var_name="poluente", value_name="valor")
            fig_a = px.line(long, x="data", y="valor", color="poluente", title="Série estadual — ar")
            st.plotly_chart(fig_a, use_container_width=True)
        st.caption(f"Fonte: qualidade_ar_estado_serie_v6 · {len(ar)} dias.")
    else:
        st.info("Série estadual de qualidade do ar ainda não disponível.")

    st.markdown("#### Como usar com a sazonalidade")
    st.markdown(
        "1. Veja se a **janela atual** (linha pontilhada) está acima da média da série.  \n"
        "2. Na aba **Sazonalidade / OR**, compare o mês/semana epidemiológica com o padrão histórico de agravos.  \n"
        "3. Cruze com **óbitos e clima** e com a trajetória ~7 dias na visão executiva."
    )
    if not publico:
        st.caption(
            f"Dias na série climática: {cmp_.get('dias_serie', 0)} · "
            "Geração: `sisclima.engines.serie_historica_ambiente`."
        )


def _delta_critico(cmp_: dict) -> bool:
    for vals in (cmp_.get("indicadores") or {}).values():
        if float(vals.get("delta") or 0) > 0.5:
            return True
    return False
