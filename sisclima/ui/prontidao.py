# -*- coding: utf-8 -*-
"""Aba Prontidão Climática Municipal (Nível 1)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sisclima.core.db import read_table, table_exists
from sisclima.engines.prontidao_climatica import run_prontidao_climatica
from sisclima.ui.theme import callout, insight_cards, section_title

try:
    from sisclima.ui.interpretacoes import GUIDE_PRONTIDAO, render_interpretacao
except ImportError:  # módulo em reload parcial do Streamlit
    from sisclima.ui.interpretacoes import guide_card, render_interpretacao

    GUIDE_PRONTIDAO = guide_card(
        "Como ler Prontidão Climática Municipal",
        [
            "<b>Fluxo</b>: cenário climático → impacto sanitário → vulneráveis → demanda → insumos → cobertura → plano.",
            "<b>IPFC</b>: prontidão farmacêutica. Sem BNAFAR mostra CONFERIR, não inventa unidades de estoque.",
            "<b>IPMEC</b>: 0–100 combinando farmácia, CNES, água, vigilância e vulnerabilidade.",
            "<b>Territórios</b>: aldeias FUNAI, quilombos Palmares, assentamentos INCRA e barragens DPA alto.",
        ],
    )


_EMOJI = {
    "muito_alto": "🔴",
    "alto": "🔴",
    "moderado": "🟠",
    "baixo": "🟡",
    "muito_baixo": "🟢",
    "sem dado": "⚪",
    "verde": "🟢",
    "amarelo": "🟡",
    "laranja": "🟠",
    "vermelho": "🔴",
    "ALTO": "🔴",
    "MODERADO": "🟠",
    "BAIXO": "🟢",
    "CONFERIR": "🟡",
    "INDETERMINADO": "⚪",
}


def _ensure(resumo: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    snap = read_table("prontidao_municipal") if table_exists("prontidao_municipal") else pd.DataFrame()
    precisa = snap is None or snap.empty or "n_aldeias" not in (snap.columns if snap is not None else [])
    if precisa:
        out = run_prontidao_climatica(resumo, persist=True)
        return out.get("snap", pd.DataFrame()), out.get("redist", pd.DataFrame()), out.get("plano", pd.DataFrame())
    redist = read_table("prontidao_redistribuicao_regional") if table_exists("prontidao_redistribuicao_regional") else pd.DataFrame()
    plano = read_table("prontidao_plano_acao") if table_exists("prontidao_plano_acao") else pd.DataFrame()
    return snap, redist, plano


def _pontos_geo(cod_ibge: str | None = None) -> pd.DataFrame:
    pts = read_table("vigibarragens_populacoes") if table_exists("vigibarragens_populacoes") else pd.DataFrame()
    if pts is None or pts.empty:
        return pd.DataFrame()
    out = pts.copy()
    out["lat"] = pd.to_numeric(out.get("lat"), errors="coerce")
    out["lon"] = pd.to_numeric(out.get("lon"), errors="coerce")
    out = out.dropna(subset=["lat", "lon"])
    if cod_ibge and "cod_ibge" in out.columns:
        codigo = str(cod_ibge).zfill(7)
        out = out[out["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False) == codigo]
    return out


def render_mapa_territorios(cod_ibge: str | None = None, altura: int = 420) -> None:
    pts = _pontos_geo(cod_ibge)
    if pts.empty:
        st.caption("Sem coordenadas para plotar neste recorte (quilombos/assentamentos muitas vezes só têm IBGE).")
        return
    import plotly.express as px

    hover = [c for c in ["municipio", "fonte", "familias", "moradores", "detalhe"] if c in pts.columns]
    try:
        fig = px.scatter_map(
            pts,
            lat="lat",
            lon="lon",
            color="categoria",
            hover_name="nome",
            hover_data=hover,
            zoom=4.6 if not cod_ibge else 8,
            height=altura,
        )
        fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0), legend_title_text="")
    except Exception:
        fig = px.scatter_geo(
            pts,
            lat="lat",
            lon="lon",
            color="categoria",
            hover_name="nome",
            hover_data=hover,
            height=altura,
        )
        fig.update_geos(
            fitbounds="locations",
            visible=False,
            projection_type="mercator",
            lataxis_range=[-18.6, -7.0],
            lonaxis_range=[-62.0, -50.0],
        )
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), legend_title_text="")
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def render_prontidao(resumo: pd.DataFrame) -> None:
    section_title(
        "Prontidão Climática Municipal",
        "Evento previsto → impacto sanitário → vulneráveis → demanda → insumos → cobertura → plano de 24h/72h/7d",
    )
    callout(
        "Nível 1 (agora): clima, epidemiologia, CNES e população — diz o que conferir e preparar. "
        "Nível 2 (BNAFAR/Hórus): estoque, validade e unidades reais. "
        "A IA consulta a matriz validada; não prescreve medicamentos nem cria protocolo clínico.",
        "info",
    )
    render_interpretacao("prontidao", GUIDE_PRONTIDAO, lambda: _narrativa(resumo))

    snap, redist, plano = _ensure(resumo)
    if snap is None or snap.empty:
        st.warning("Não foi possível calcular a prontidão neste recorte.")
        return

    n = len(snap)
    n_conf = int((snap.get("estoque_nivel", pd.Series(dtype=str)).astype(str) == "nivel_1_conferir").sum()) if "estoque_nivel" in snap.columns else n
    n_verm = int((snap.get("nivel_prontidao", pd.Series(dtype=str)).astype(str) == "vermelho").sum()) if "nivel_prontidao" in snap.columns else 0
    n_terr = int((pd.to_numeric(snap.get("n_territorios_tradicionais"), errors="coerce").fillna(0) > 0).sum()) if "n_territorios_tradicionais" in snap.columns else 0
    insight_cards(
        [
            ("Municípios", str(n), "recorte IBGE 142"),
            ("IPMEC vermelho", str(n_verm), "prontidão <40/100"),
            ("Com território tradicional", str(n_terr), "aldeia, quilombo ou assentamento"),
            ("Estoque BNAFAR", f"{n - n_conf}/{n}", "com cobertura em dias"),
        ]
    )

    st.caption(
        "Fase 1 no Mato Grosso: seca/estiagem + baixa umidade + queimadas/fumaça (fenômenos interligados). "
        "Territórios: Vigibarragens (FUNAI, Palmares, INCRA, SNISB). Distância ao eixo de barragem não é cota de inundação."
    )

    mun_opts = ["(visão estadual)"] + sorted(snap["municipio"].dropna().astype(str).unique().tolist()) if "municipio" in snap.columns else ["(visão estadual)"]
    escolha = st.selectbox("Município", mun_opts, index=0)
    if escolha != "(visão estadual)":
        _ficha_municipal(snap, plano, escolha)
    else:
        _visao_estadual(snap, redist)

    with st.expander("Matriz de cenários (o que conferir)", expanded=False):
        st.markdown(
            """
| Cenário | Impactos | Estoques/capacidade | Ações antecipatórias |
|---|---|---|---|
| Seca / estiagem | DDA, desidratação, dermatites, insegurança hídrica | SRO, hidratação venosa, água segura, crônicos | Vigiagua, estoque, busca de vulneráveis |
| Baixa umidade | asma/DPOC, irritação, desidratação | respiratórios padronizados, inalatórios | APS, escolas, ILPI, sentinelas |
| Queimadas / fumaça | respiratório e cardiovascular | broncodilatadores, oxigênio, urgência | redução de exposição, PFF2 conforme IQA |
| Kit calamidade MS | desabrigados/desalojados | 32 medicamentos + 16 insumos (até 500 pessoas / 3 meses) | só em calamidade — não é lista universal climática |
"""
        )


def _visao_estadual(snap: pd.DataFrame, redist: pd.DataFrame) -> None:
    st.markdown("#### Ranking de prontidão (IPMEC)")
    cols = [
        c
        for c in [
            "municipio",
            "regional_saude",
            "nivel_prontidao",
            "ipmec",
            "ipfc",
            "cenario_dominante",
            "risco_climatico_rotulo",
            "risco_respiratorio_rotulo",
            "demanda_projetada_pct",
            "risco_ruptura",
            "populacao_vulneravel_estimada",
            "n_aldeias",
            "n_quilombos",
            "n_assentamentos",
            "n_barragens_dpa_alto",
            "ipmec_completude_pct",
        ]
        if c in snap.columns
    ]
    view = snap.sort_values(["ipmec", "ipfc"], ascending=[True, True]) if "ipmec" in snap.columns else snap
    st.dataframe(view[cols], use_container_width=True, hide_index=True, height=380)
    if redist is not None and not redist.empty:
        st.markdown("#### Estoque/capacidade inteligente regional")
        st.caption("Sinal técnico para a Sala de Situação. Quantidade de unidades só após BNAFAR.")
        st.dataframe(redist, use_container_width=True, hide_index=True, height=220)

    st.markdown("#### Populações vulneráveis × risco climático")
    st.caption(
        "Aldeias (FUNAI), quilombos certificados (Palmares) e assentamentos (INCRA). "
        "Barragem DPA alto entra como risco territorial, não como comunidade. "
        "ZAS/ZSS pública de inundação no MT ainda é incompleta."
    )
    tcols = [
        c
        for c in [
            "municipio",
            "cenario_dominante",
            "risco_climatico_rotulo",
            "n_aldeias",
            "n_terras_indigenas",
            "n_quilombos",
            "n_assentamentos",
            "familias_assentamentos",
            "n_barragens_dpa_alto",
            "cuidados_territoriais",
        ]
        if c in snap.columns
    ]
    if tcols:
        terr = snap.copy()
        nterr = pd.to_numeric(terr.get("n_territorios_tradicionais"), errors="coerce").fillna(0) if "n_territorios_tradicionais" in terr.columns else pd.Series(0, index=terr.index)
        zas = pd.to_numeric(terr.get("n_barragens_dpa_alto"), errors="coerce").fillna(0) if "n_barragens_dpa_alto" in terr.columns else pd.Series(0, index=terr.index)
        terr = terr[(nterr > 0) | (zas > 0)]
        if terr.empty:
            st.info("Nenhum município do recorte cruzou com o Vigibarragens ainda. Confira VIGIBARRAGENS_DATA_DIR.")
        else:
            st.dataframe(terr[tcols], use_container_width=True, hide_index=True, height=320)
    render_mapa_territorios()


def _ficha_municipal(snap: pd.DataFrame, plano: pd.DataFrame, municipio: str) -> None:
    row = snap[snap["municipio"].astype(str) == municipio]
    if row.empty:
        st.info("Município fora da tabela de prontidão.")
        return
    r = row.iloc[0]
    rc = str(r.get("risco_climatico_rotulo") or "sem dado")
    rr = str(r.get("risco_respiratorio_rotulo") or "sem dado")
    nv = str(r.get("nivel_prontidao") or "—")
    st.markdown(f"### {municipio}")
    insight_cards(
        [
            ("Risco climático", f"{_EMOJI.get(rc, '⚪')} {rc.replace('_', ' ')}", str(r.get("cenario_dominante") or "—")),
            ("Risco respiratório", f"{_EMOJI.get(rr, '⚪')} {rr.replace('_', ' ')}", "fumaça + umidade + SRAG"),
            ("Pop. vulnerável est.", (f"{pd.to_numeric(r.get('populacao_vulneravel_estimada'), errors='coerce'):,.0f}".replace(",", ".") if pd.notna(pd.to_numeric(r.get("populacao_vulneravel_estimada"), errors="coerce")) else "—"), "idosos, crianças, rural"),
            ("Demanda projetada", f"↑ {r.get('demanda_projetada_pct')}%", f"fator {r.get('fonte_fator_epidemiologico')}"),
            ("IPFC", str(r.get("ipfc")), str(r.get("risco_ruptura"))),
            ("IPMEC", f"{r.get('ipmec')}/100 {_EMOJI.get(nv, '')}", f"{r.get('ipmec_completude_pct')}% dimensões"),
        ]
    )
    cob = r.get("cobertura_dias")
    if pd.isna(cob):
        st.warning(
            "Cobertura em dias indisponível: **Nível 1**. Conferir estoque utilizável (físico − vencimentos − reservas + compras) "
            f"e comparar com consumo previsto (fator {r.get('fator_consumo')}) e lead time de {r.get('lead_time_reposicao_dias')} dias."
        )
    else:
        st.success(
            f"Cobertura estimada: **{cob} dias** · lead time {r.get('lead_time_reposicao_dias')} d · ruptura {r.get('risco_ruptura')}."
        )
    st.markdown(f"**Impactos sanitários:** {r.get('impactos_prioritarios')}")
    st.markdown(f"**Insumos críticos a conferir:** {r.get('insumos_criticos')}")
    st.caption(
        f"Regra: `{r.get('regras_aplicadas')}` · {r.get('estoque_nivel')} · "
        f"Não prescreve fármaco — classes REMUME/RENAME. Lacunas IPMEC: {r.get('ipmec_lacunas') or '—'}"
    )

    st.markdown("#### Territórios tradicionais e barragens")
    insight_cards(
        [
            ("Aldeias FUNAI", str(int(pd.to_numeric(r.get("n_aldeias"), errors="coerce") or 0)), f"TIs: {int(pd.to_numeric(r.get('n_terras_indigenas'), errors='coerce') or 0)}"),
            ("Quilombos Palmares", str(int(pd.to_numeric(r.get("n_quilombos"), errors="coerce") or 0)), "certificados — não só titulados"),
            ("Assentamentos INCRA", str(int(pd.to_numeric(r.get("n_assentamentos"), errors="coerce") or 0)), f"famílias: {int(pd.to_numeric(r.get('familias_assentamentos'), errors='coerce') or 0)}"),
            ("Barragens DPA alto", str(int(pd.to_numeric(r.get("n_barragens_dpa_alto"), errors="coerce") or 0)), "não é polígono de inundação"),
        ]
    )
    cuidados = str(r.get("cuidados_territoriais") or "").strip()
    if cuidados:
        st.info(cuidados)
    else:
        st.caption("Nenhum território tradicional ou DPA alto neste município no cadastro Vigibarragens.")
    render_mapa_territorios(str(r.get("cod_ibge") or ""), altura=360)
    lista = read_table("vigibarragens_populacoes") if table_exists("vigibarragens_populacoes") else pd.DataFrame()
    if lista is not None and not lista.empty and "cod_ibge" in lista.columns:
        codigo = str(r.get("cod_ibge") or "").zfill(7)
        loc = lista[lista["cod_ibge"].astype(str).str.extract(r"(\d{7})", expand=False) == codigo]
        show_cols = [c for c in ["categoria", "nome", "familias", "moradores", "fonte"] if c in loc.columns]
        if not loc.empty and show_cols:
            st.dataframe(loc[show_cols], use_container_width=True, hide_index=True, height=220)

    st.markdown("#### Plano de ação municipal")
    p = plano[plano["municipio"].astype(str) == municipio] if plano is not None and not plano.empty else pd.DataFrame()
    if p.empty:
        st.info("Plano ainda não gerado para este município.")
        return
    for horiz in ["0-24h", "24-72h", "3-7d", "manutencao"]:
        bloco = p[p["horizonte"].astype(str) == horiz]
        if bloco.empty:
            continue
        st.markdown(f"**{horiz}**")
        for _, a in bloco.iterrows():
            st.markdown(f"- *{a.get('publico')}* — {a.get('acao')}")
        meta = bloco.iloc[0]
        st.caption(
            f"Fonte: {meta.get('fonte')} · Confiança: {meta.get('confianca')} · "
            f"Validação: {meta.get('validador')} · Dados: {meta.get('data_analise')}"
        )


def _narrativa(resumo: pd.DataFrame) -> str:
    if resumo is None or resumo.empty:
        return "Sem recorte municipal para prontidão."
    n = len(resumo)
    n_al = int(pd.to_numeric(resumo.get("n_aldeias"), errors="coerce").fillna(0).sum()) if resumo is not None and "n_aldeias" in resumo.columns else 0
    n_q = int(pd.to_numeric(resumo.get("n_quilombos"), errors="coerce").fillna(0).sum()) if resumo is not None and "n_quilombos" in resumo.columns else 0
    return (
        f"Recorte de {n} municípios. O IPMEC combina farmácia (o que conferir), assistência (CNES/leitos), "
        "água (WASH), vigilância e vulnerabilidade. Dimensões sem dado não são inventadas — reduzem a completude. "
        f"Territórios Vigibarragens neste recorte: {n_al} aldeias e {n_q} quilombos. "
        "Cuidados (SESAI/DSEI, APS rural, Defesa Civil) seguem o cenário climático dominante do município. "
        "Distância ao eixo de barragem não substitui polígono de inundação."
    )
