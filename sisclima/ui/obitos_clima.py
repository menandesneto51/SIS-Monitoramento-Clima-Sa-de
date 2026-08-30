# -*- coding: utf-8 -*-
"""Aba pública/restrita: óbitos SIM sensíveis ao clima + metodologia."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from sisclima.engines.obitos_clima_contexto import resumo_obitos_clima
from sisclima.ui.theme import callout, insight_cards, section_title


def render_obitos_clima(*, publico: bool = True) -> None:
    section_title(
        "Óbitos e clima",
        "SIM — óbitos em grupos CID sensíveis ao calor/clima (vigilância ecológica)",
    )
    callout(
        "Estes números NÃO significam óbitos 'causados pelo clima' no indivíduo. "
        "São contagens SIM em grupos de CID usados na vigilância de extremos térmicos e vias intermediárias.",
        "warn",
    )

    pack = resumo_obitos_clima()
    insight_cards(
        [
            ("Série estadual (soma)", str(pack.get("total_serie") or 0), f"último mês: {pack.get('ultimo_mes') or '—'}"),
            (
                "Municípios com registro",
                str(pack.get("n_municipios_com_obito") or 0),
                f"{pack.get('total_municipal') or 0} óbitos no recorte municipal",
            ),
            (
                "Grupos operacionais",
                str(len(pack.get("por_grupo") or {})),
                "ver metodologia abaixo",
            ),
        ]
    )
    callout(str(pack.get("narrativa") or ""), "info")

    serie = pack.get("serie") if isinstance(pack.get("serie"), pd.DataFrame) else pd.DataFrame()
    st.markdown("#### Série mensal estadual")
    if serie is not None and not serie.empty:
        s = serie.copy()
        s["obitos"] = pd.to_numeric(s["obitos"], errors="coerce")
        if "mes" in s.columns:
            s["mes_dt"] = pd.to_datetime(s["mes"].astype(str) + "-01", errors="coerce")
            color = "grupo_obito_calor" if "grupo_obito_calor" in s.columns else None
            fig = px.line(
                s.sort_values("mes_dt"),
                x="mes_dt",
                y="obitos",
                color=color,
                markers=True,
                title="Óbitos SIM sensíveis ao calor — série estadual mensal",
            )
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(s.drop(columns=["mes_dt"], errors="ignore"), use_container_width=True, hide_index=True)
    else:
        st.info("Série `sim_obitos_calor_estado_serie_v6` indisponível nesta rodada.")

    mun = pack.get("municipal") if isinstance(pack.get("municipal"), pd.DataFrame) else pd.DataFrame()
    st.markdown("#### Ranking municipal (consolidação atual)")
    if mun is not None and not mun.empty:
        m = mun.copy()
        m["obitos"] = pd.to_numeric(m["obitos"], errors="coerce").fillna(0)
        top = m.sort_values("obitos", ascending=False).head(25)
        cols = [c for c in ("municipio", "regional_saude", "grupo_obito_calor", "obitos", "cod_ibge") if c in top.columns]
        st.dataframe(top[cols], use_container_width=True, hide_index=True)
    else:
        st.info("Tabela municipal de óbitos sensíveis ao calor indisponível.")

    st.markdown("#### Metodologia")
    st.markdown(pack.get("metodologia_md") or "")

    if not publico:
        st.caption("Fontes: DW SIM / epi_sim_obitos_calor → consolidação v6 (`saude_calor_consolida`).")
