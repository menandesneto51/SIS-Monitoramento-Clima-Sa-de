# -*- coding: utf-8 -*-
"""Painel restrito — decretos de emergência (IOMAT + imprensa) para a Sala ARARAS."""
from __future__ import annotations

import streamlit as st

from sisclima.core.db import read_table, table_exists
from sisclima.ui.theme import callout, section_title

_TABLE = "iomat_decretos_emergencia"


def render_decretos_emergencia(*, allow_refresh: bool = True) -> None:
    """Lista atos já persistidos; opcionalmente dispara nova busca IOMAT/imprensa."""
    section_title(
        "Decretos e atos de emergência",
        "IOMAT (oficial) + sinais de imprensa — validar no Diário Oficial antes de uso institucional",
    )
    callout(
        "A busca não substitui a leitura do ato completo. Itens de imprensa são auxiliares. "
        "Cruze municípios citados com o nível ARARAS e com a priorização territorial.",
        "info",
    )

    if allow_refresh:
        c1, c2 = st.columns([1, 3])
        with c1:
            dias = st.number_input("Janela (dias)", min_value=7, max_value=180, value=60, step=7, key="dec_dias")
        with c2:
            st.caption("Atualização consulta IOMAT e, se configurado, feeds de imprensa.")
        if st.button("Atualizar busca de decretos", key="dec_refresh", type="primary"):
            with st.spinner("Consultando IOMAT / imprensa…"):
                try:
                    from sisclima.ingestion.iomat_decretos import run_busca_decretos

                    out = run_busca_decretos(dias_retroativos=int(dias))
                    n = int((out or {}).get("n") or 0)
                    st.success(f"Busca concluída: {n} registro(s) persistido(s).")
                    st.cache_data.clear()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Falha na busca: {exc}")

    if not table_exists(_TABLE):
        st.warning(
            "Tabela ainda não existe. Execute a busca acima ou "
            "`scripts/buscar_decretos_emergencia_araras.py` na estação operacional."
        )
        return

    df = read_table(_TABLE)
    if df is None or df.empty:
        st.info("Nenhum decreto/ato na base nesta rodada.")
        return

    work = df.copy()
    if "score_relevancia" in work.columns:
        work = work.sort_values("score_relevancia", ascending=False, na_position="last")
    cols = [
        c
        for c in (
            "fonte",
            "data_publicacao",
            "titulo",
            "municipios_mencionados",
            "tags",
            "score_relevancia",
            "url",
        )
        if c in work.columns
    ]
    st.caption(f"{len(work)} registro(s) na base operacional.")
    st.dataframe(work[cols] if cols else work, use_container_width=True, hide_index=True, height=360)

    md_path = None
    try:
        from pathlib import Path

        from sisclima.core.config import ROOT

        candidatos = sorted(
            (ROOT / "docs" / "apresentacoes").glob("Decretos_Emergencia_ARARAS_*.md"),
            reverse=True,
        )
        if candidatos:
            md_path = candidatos[0]
    except Exception:  # noqa: BLE001
        md_path = None
    if md_path is not None and md_path.exists():
        st.download_button(
            "Baixar último relatório MD de decretos",
            data=md_path.read_text(encoding="utf-8"),
            file_name=md_path.name,
            mime="text/markdown",
            key="dl_decretos_md",
        )
