# -*- coding: utf-8 -*-
"""Painel público (leigo): situação, mapa de risco 3d, calor/fumaça, tendência, o que fazer."""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from sisclima.engines.geospatial import LEVEL_COLOR_MAP
from sisclima.engines.stages import STAGE_ORDER
from sisclima.ui.explainers import LEVEL_GUIDE
from sisclima.ui.theme import callout, insight_cards, level_legend, section_title

ACOES_POPULACAO: dict[str, list[str]] = {
    "verde": [
        "Mantenha hidratação habitual e evite exposição longa ao sol do meio-dia.",
        "Acompanhe idosos, crianças e pessoas com doença respiratória ou cardíaca.",
    ],
    "amarela": [
        "Beba água ao longo do dia, mesmo sem sede. Evite exercícios ao ar livre no pico de calor.",
        "Procure sombra e ambientes arejados. Se o ar estiver ruim, reduza atividade externa.",
    ],
    "laranja": [
        "Priorize cuidados com idosos sozinhos, gestantes, crianças e quem tem asma ou DPOC.",
        "Use máscara do tipo PFF2 se a qualidade do ar estiver ruim e houver sintomas respiratórios.",
        "Na UBS ou UPA: desidratação, desmaio, falta de ar ou febre alta merecem avaliação.",
    ],
    "vermelha": [
        "Evite rua nas horas mais quentes. Fique em local sombreado ou climatizado.",
        "Não deixe crianças ou idosos em veículos. Reforce água e refeições leves.",
        "Procure a rede de saúde ao primeiro sinal de mal-estar grave.",
    ],
    "roxa": [
        "Siga os avisos da SES e da Defesa Civil. Limite exposição ao calor e à fumaça.",
        "Ajude vizinhos vulneráveis. Em emergência, ligue para o serviço de saúde local.",
    ],
    "cinza": [
        "Há lacunas de dados neste recorte. Não interprete ausência de número como ‘tudo bem’.",
    ],
}


def _nivel(resumo: pd.DataFrame) -> str:
    if resumo is None or resumo.empty or "nivel" not in resumo.columns:
        return "cinza"
    ranks = resumo["nivel"].astype(str).str.lower().map(STAGE_ORDER).fillna(-1)
    if ranks.max() < 0:
        return "cinza"
    idx = ranks.idxmax()
    return str(resumo.loc[idx, "nivel"]).lower()


def _frase_agora(nivel: str, n_alerta: int, n_total: int) -> str:
    meta = LEVEL_GUIDE.get(nivel, LEVEL_GUIDE["cinza"])
    return (
        f"{meta['o_que_e']} "
        f"No Estado, {n_alerta} de {n_total} municípios estão em vermelha ou roxa nesta rodada."
    )


def render_painel_publico(
    *,
    resumo: pd.DataFrame,
    map_df: pd.DataFrame,
    geojson: dict | None,
    choropleth: Callable[..., Any],
    tmax=None,
    utci=None,
    pm25=None,
    n_subindo: int = 0,
) -> None:
    if resumo is None or resumo.empty:
        st.warning("Sem resumo municipal para o painel público nesta rodada.")
        return
    nivel = _nivel(resumo)
    n_total = max(len(resumo), 1)
    n_alerta = int(resumo["nivel"].astype(str).str.lower().isin(["vermelha", "roxa"]).sum()) if "nivel" in resumo.columns else 0
    meta = LEVEL_GUIDE.get(nivel, LEVEL_GUIDE["cinza"])
    color = LEVEL_COLOR_MAP.get(nivel, "#334155")

    section_title("O que está acontecendo agora", "Leitura para a população e a atenção básica — sem jargão operacional")
    st.markdown(
        f"""
        <div class="sis-card" style="border-left:8px solid {color}">
          <b>{meta['titulo']}</b><br/>
          <span>{_frase_agora(nivel, n_alerta, n_total)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    callout(
        "As cores do ARARAS são classificação operacional de apoio. Não substituem decreto de emergência nem boletim oficial do INMET.",
        "warn",
    )
    insight_cards(
        [
            ("Situação do Estado", str(nivel).upper(), meta["analogia"]),
            ("Municípios em alerta", f"{n_alerta}/{n_total}", "vermelha + roxa"),
            ("Tendência em 7 dias", f"{n_subindo} mun. em alta", "priorização climática/saúde"),
        ]
    )

    section_title("Mapa de risco para 3 dias", "Quanto mais intenso o vermelho, maior o acúmulo de calor recente")
    if map_df is not None and not map_df.empty and "risco_cumulativo_3d" in map_df.columns:
        choropleth(
            map_df,
            geojson,
            "risco_cumulativo_3d",
            "Risco cumulativo de calor — 3 dias",
            hover_cols=["municipio", "regional_saude", "nivel", "tmax", "utci_proxy"],
            categorical=False,
        )
    else:
        st.info("Mapa de risco 3 dias indisponível nesta rodada.")

    section_title("Calor e fumaça", "Números em linguagem simples")
    c1, c2, c3 = st.columns(3)
    c1.metric("Temperatura máxima", "—" if tmax is None or pd.isna(tmax) else f"{float(tmax):.1f} °C")
    c2.metric("Desconforto térmico (UTCI)", "—" if utci is None or pd.isna(utci) else f"{float(utci):.1f}")
    c3.metric("Fumaça (PM2,5)", "—" if pm25 is None or pd.isna(pm25) else f"{float(pm25):.1f}")
    st.caption("UTCI é um índice de como o corpo sente o calor (temperatura + umidade + vento). PM2,5 mede partículas finas no ar.")

    section_title("O que a população e a APS podem fazer", meta["o_que_fazer"])
    for item in ACOES_POPULACAO.get(nivel, ACOES_POPULACAO["cinza"]):
        st.markdown(f"- {item}")

    section_title("Guia das cores", "Verde → Roxa")
    level_legend()
    for key in ("verde", "amarela", "laranja", "vermelha", "roxa"):
        info = LEVEL_GUIDE[key]
        st.markdown(
            f"**{info['titulo']}** — {info['o_que_e']}  \n*O que fazer:* {info['o_que_fazer']}"
        )
    st.caption("Fonte: SES-MT / CIEVS-MT · ARARAS MT. Em dúvida, procure a unidade de saúde do seu município.")
