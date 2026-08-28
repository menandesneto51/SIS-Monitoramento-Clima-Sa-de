# -*- coding: utf-8 -*-
"""Sala de Situação / Plano El Niño — restrita (ses+). Sem evidência no painel público."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from sisclima.auth.access import current_user, is_admin
from sisclima.plano.acesso import (
    MATRIZ_ACESSO_PAINEL,
    capacidades_usuario,
    contexto_plano,
    gravar_vinculo,
    listar_vinculos,
    pode_abrir_sala,
    pode_editar_area,
)
from sisclima.plano.areas import AREAS_CANONICAS
from sisclima.plano.catalogo import carregar_catalogo
from sisclima.plano.constants import EVENTOS_NOTIFICACAO, PERFIS_PLANO, STATUS_ACAO, STATUS_COR
from sisclima.plano.operacao import resumo_sala, status_cor
from sisclima.ui.theme import callout, insight_cards, section_title


@st.cache_data(ttl=120, show_spinner="Lendo fontes automáticas…")
def _coleta_automaticos_cached() -> list[dict]:
    from sisclima.plano.conectores import coletar_automaticos

    return coletar_automaticos()


def render_sala_situacao_plano() -> None:
    user = current_user()
    section_title(
        "Sala de Situação / Plano El Niño",
        "ARARAS MT — registro oficial do Plano. E-mail e WhatsApp só cobram; não substituem este módulo.",
    )
    if not pode_abrir_sala(user):
        st.warning("Módulo restrito à SES/CIEVS (nível ses ou admin). O painel público não exibe evidências nem documentos.")
        return

    ctx = contexto_plano(user)
    st.caption(
        f"Perfil do Plano: **{ctx['rotulo_perfil']}**"
        + (f" · área `{ctx['area_id']}`" if ctx.get("area_id") else " · sem área vinculada (leitura)")
    )
    callout(
        "Números abaixo vêm do catálogo da planilha + atualizações gravadas. "
        "Sem preenchimento das áreas, implementação é 0% — não há valor inventado. "
        "100% só é oficial após validação CIEVS.",
        "info",
    )

    tab_brief, tab_ind, tab_cob, tab_acoes, tab_val, tab_acs = st.tabs(
        ["Briefing", "Indicadores", "Cobrança", "Ações", "Validação CIEVS", "Acessos"]
    )
    with tab_brief:
        _render_briefing(ctx, user)
    with tab_ind:
        _render_indicadores(ctx, user)
    with tab_cob:
        _render_cobranca(ctx, user)
    with tab_acoes:
        _render_acoes(ctx, user)
    with tab_val:
        _render_validacao(ctx, user)
    with tab_acs:
        _render_acessos(user)


def _render_briefing(ctx: dict, user: dict | None) -> None:
    resumo = resumo_sala()
    insight_cards(
        [
            ("Implementação (bruta)", f"{resumo['percentual_bruto']:.0f}%", f"{resumo['n_acoes']} ações no catálogo"),
            ("Índice oficial", "sim" if resumo["indice_oficial"] else "não", "exige validação de todos os itens"),
            ("Pendentes", str(resumo["pendentes"]), "não iniciada / em andamento / em validação"),
            ("Vencidas", str(resumo["vencidas"]), "prazo ISO vencido (ainda raro na planilha)"),
        ]
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Eixos", resumo["n_eixos"])
    c2.metric("Indicadores (fonte)", resumo["n_indicadores"])
    c3.metric("No índice de implementação", resumo["n_indicadores_indice"])
    from sisclima.plano.catalogo import resumo_adequacao

    adq = resumo_adequacao()
    papeis = adq.get("por_papel") or {}
    callout(
        "Adequação 28/08/2026: risco, estágio de resposta, desempenho e completude são campos diferentes. "
        f"{papeis.get('operacional', 0)} operacionais · {papeis.get('preparacao', 0)} gates de prontidão · "
        f"{papeis.get('gatilho', 0)} gatilhos (fora do índice) · {papeis.get('hibrido', 0)} híbridos · "
        f"{papeis.get('alias', 0)} aliases (068/073/074). Sem dado nunca vira 0. Denominador 0 = N/A. "
        "SLA segue perfis S1–S12 conforme o estágio de ativação.",
        "info",
    )
    a1, a2, a3, a4, a5 = st.columns(5)
    a1.metric("Operacional", papeis.get("operacional", 0))
    a2.metric("Prontidão", papeis.get("preparacao", 0))
    a3.metric("Gatilho", papeis.get("gatilho", 0))
    a4.metric("Híbrido", papeis.get("hibrido", 0))
    a5.metric("Alias", papeis.get("alias", 0))
    if ctx.get("pode_validar") or str((user or {}).get("nivel") or "") == "admin":
        if st.button("Atualizar indicadores automáticos (tabelas do pipeline)", key="sala_btn_auto"):
            from sisclima.plano.indicadores import atualizar_automaticos

            out = atualizar_automaticos()
            _coleta_automaticos_cached.clear()
            st.info(
                f"Automáticos: {out['gravados']} gravados · "
                f"{out.get('inalterados', 0)} inalterados · "
                f"{out['aguardando_fonte']} aguardando fonte · {out['erros']} erros. "
                "Sem dado da fonte, o ARARAS não inventa valor."
            )
            st.rerun()

    por_status = resumo.get("por_status") or {}
    if por_status:
        df_st = pd.DataFrame(
            [
                {"Status": k, "Rótulo": dict(STATUS_ACAO).get(k, k), "N": v, "Cor": status_cor(k)}
                for k, v in por_status.items()
            ]
        )
        st.markdown("#### Por status")
        st.dataframe(df_st.drop(columns=["Cor"]), use_container_width=True, hide_index=True)
        cores = " · ".join(f"{dict(STATUS_ACAO).get(k, k)} `{STATUS_COR.get(k, '')}`" for k, _ in STATUS_ACAO)
        st.caption(cores)

    por_eixo = resumo.get("por_eixo") or {}
    if por_eixo:
        st.markdown("#### Por eixo")
        st.dataframe(
            pd.DataFrame(
                [{"Eixo": k, "Ações": v.get("total", 0), "Concluídas": v.get("concluida", 0)} for k, v in por_eixo.items()]
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Risco × ativação (não são a mesma coisa)")
    try:
        from sisclima.plano.ativacao import quadro_dois_estados, registrar_estagio

        dois = quadro_dois_estados()
        r1, r2, r3 = st.columns(3)
        r1.metric("Nível de risco (dado)", str(dois.get("nivel_risco") or "indisponível"))
        r2.metric("Estágio de ativação (Comando)", str(dois.get("estagio_ativacao") or "verde"))
        r3.metric("Origem da ativação", str(dois.get("origem_ativacao") or "padrao"))
        st.caption(
            "Risco vem do painel climático. Estágio de ativação só o CIEVS/Comando grava. "
            "Mudar o estágio não recalcula o risco — só a cadência/SLA esperada."
        )
        if ctx.get("pode_validar") or str((user or {}).get("nivel") or "") == "admin":
            with st.expander("Registrar estágio de ativação (CIEVS)", expanded=False):
                novo = st.selectbox(
                    "Estágio",
                    ["verde", "amarelo", "laranja", "vermelho", "roxo"],
                    index=["verde", "amarelo", "laranja", "vermelho", "roxo"].index(
                        str(dois.get("estagio_ativacao") or "verde")
                    ),
                    key="sala_estagio_ativacao",
                )
                obs = st.text_input("Observação (PAI / decisão)", key="sala_estagio_obs")
                if st.button("Gravar estágio", key="sala_btn_estagio"):
                    ok, msg = registrar_estagio(user=user or {}, estagio=novo, observacao=obs)
                    st.success(msg) if ok else st.error(msg)
                    if ok:
                        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Dois estados indisponíveis nesta sessão: {exc}")

    st.markdown("#### Fila desta semana (indicadores do índice)")
    try:
        from sisclima.plano.indicadores import cumprimento_indice, linhas_painel_indicadores, quadro_indicadores
        from sisclima.plano.sugestoes import fila_para_indice

        quadro_ind = quadro_indicadores(so_indice=False)
        try:
            leituras_ind = _coleta_automaticos_cached()
        except Exception:  # noqa: BLE001
            leituras_ind = []
        linhas_ind = linhas_painel_indicadores(quadro=quadro_ind, leituras_auto=leituras_ind)
        cump_ind = cumprimento_indice(quadro_ind)
        fila = fila_para_indice(linhas_ind)
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Operacional", f"{cump_ind['percentual_operacional']:.0f}%")
        f2.metric("Oficial CIEVS", f"{cump_ind['percentual_oficial']:.0f}%")
        f3.metric("Onda 1 (Sim+SEI)", str(len(fila["onda1"])))
        f4.metric("Pendências no índice", str(fila["n_pendentes_indice"]))
        st.caption(
            "Operacional é a média só de quem já tem leitura. Oficial só sobe com validação CIEVS. "
            "Não registrar zero na Visa (onda 4)."
        )
        if fila["onda1"]:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "id": r["id"],
                            "indicador": (r.get("nome") or "")[:80],
                            "área": r.get("area"),
                            "ação": "Sim + link SEI na Sala",
                        }
                        for r in fila["onda1"]
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Onda 1 sem pendência nesta rodada.")
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Fila de indicadores indisponível nesta sessão: {exc}")

    with st.expander("PAI — ações a partir do Amarelo", expanded=False):
        from sisclima.plano.pai import listar_acoes_pai, pai_aplicavel, registrar_acao_pai

        if not pai_aplicavel():
            st.caption("PAI só abre a partir do estágio Amarelo. No Verde o foco é prontidão.")
        else:
            st.caption("Cada linha vira ação rastreável. Sem envio automático de e-mail.")
            iid_pai = st.text_input("Indicador (ex.: IND-007)", key="sala_pai_ind")
            desc_pai = st.text_input("Ação do PAI", key="sala_pai_desc")
            prazo_pai = st.text_input("Prazo", key="sala_pai_prazo")
            if st.button("Abrir ação no PAI", key="sala_pai_btn"):
                ok, msg, _ = registrar_acao_pai(
                    user=user or {},
                    indicador_id=iid_pai,
                    descricao=desc_pai,
                    prazo=prazo_pai,
                )
                st.success(msg) if ok else st.error(msg)
        abertas = listar_acoes_pai(so_abertas=True)
        if abertas:
            st.dataframe(pd.DataFrame(abertas), use_container_width=True, hide_index=True)

    with st.expander("Indicadores CIEVS (governança da Sala — catálogo)", expanded=False):
        from sisclima.plano.pai import indicadores_cievs_sala

        cievs = indicadores_cievs_sala()
        st.caption(
            "30 indicadores de governança da Sala. Só viram número quando a Sala já gravar "
            "decisão, briefing e validade de fonte. Catálogo agora; cálculo depois."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "id": c.get("id"),
                        "nome": c.get("nome"),
                        "classe": c.get("classe_emergencia"),
                        "perfil": c.get("perfil_escalonamento"),
                        "tipo": c.get("tipo_emergencia"),
                    }
                    for c in cievs
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Clima, sazonalidade e grupos mais afetados")
    try:
        from sisclima.plano.analise_clima_sala import painel_sala_clima

        clima = painel_sala_clima()
        if not clima.get("disponivel"):
            st.caption("Sem série climática ou OR nesta rodada — o ARARAS não inventa curva.")
        else:
            st.caption(
                "Linha do tempo = média estadual diária (Open-Meteo/biometeo). "
                "Sazonalidade compara o mês atual com o histórico de Tmáx. "
                "OR é ecológico (município/janela), não causal individual."
            )
            serie = clima.get("serie_clima")
            if serie is not None and not serie.empty:
                ycols = [c for c in ("tmax", "utci_proxy", "pm25_ugm3", "precipitacao_mm", "risco_calor_diario", "risco_cumulativo_3d") if c in serie.columns]
                plot = serie.set_index("data")[ycols] if ycols and "data" in serie.columns else None
                if plot is not None and not plot.empty:
                    st.line_chart(plot, use_container_width=True)
                st.caption(f"{int(clima.get('n_dias_clima') or 0)} dias na série climática.")
            saz = clima.get("sazonalidade")
            if saz is not None and not saz.empty and "indice_sazonal" in saz.columns:
                idx_col = "mes_rotulo" if "mes_rotulo" in saz.columns else "mes"
                st.bar_chart(saz.set_index(idx_col)["indice_sazonal"], use_container_width=True)
                pico = clima.get("pico_sazonal") or {}
                atual = clima.get("indice_mes_atual")
                if pico:
                    txt = f"Pico histórico: {pico.get('rotulo')} (índice {pico.get('indice'):.2f})."
                    if atual is not None:
                        txt += f" Mês corrente: índice {atual:.2f} (>1 = acima da média histórica)."
                    st.caption(txt)
            or_t = clima.get("or_timeline")
            if or_t is not None and not or_t.empty and "or" in or_t.columns:
                st.markdown("##### Odds ratio no tempo (janela 28 dias)")
                ot = or_t.copy()
                if "data" in ot.columns:
                    st.line_chart(ot.set_index("data")[["or"]], use_container_width=True)
                st.caption("OR > 1: desfecho alto mais frequente nos dias de alta exposição. Não é risco individual.")
            grupos = clima.get("or_grupos")
            pares = clima.get("or_pares")
            g1, g2 = st.columns(2)
            with g1:
                st.markdown("##### Grupos territoriais (OR)")
                if grupos is not None and not grupos.empty:
                    show = grupos[[c for c in ("grupo", "exposicao", "desfecho", "or", "ic95_inferior", "ic95_superior", "p_value", "n_municipios") if c in grupos.columns]].head(12)
                    st.dataframe(show, use_container_width=True, hide_index=True)
                else:
                    st.caption("Sem regional com N suficiente para OR por grupo nesta rodada.")
            with g2:
                st.markdown("##### Pares exposição → desfecho")
                if pares is not None and not pares.empty:
                    show = pares[[c for c in ("exposicao", "desfecho", "or", "ic95_inferior", "ic95_superior", "p_value", "significativo_005") if c in pares.columns]].head(12)
                    st.dataframe(show, use_container_width=True, hide_index=True)
                else:
                    st.caption("Sem par OR calculável no resumo municipal.")
    except Exception as exc:  # noqa: BLE001
        st.caption(f"Análise climática/OR indisponível nesta sessão: {exc}")

    with st.expander("Como o coordenador atualiza uma ação", expanded=False):
        st.markdown(
            "1. Entrar com conta **ses/admin** e vínculo `coordenador_area` + `area_id`.\n"
            "2. Escolher a ação da **própria área** (Assistência Farmacêutica não grava Vigilância Sanitária).\n"
            "3. Registrar atualização **append-only** (status, valor, observação).\n"
            "4. Anexar evidência: **link SEI** (oficial) e PDF opcional no ARARAS.\n"
            "5. Situação vai para `em_validacao`. CIEVS valida ou rejeita (rejeição gera nova linha, não apaga a anterior).\n"
            "6. E-mail avisa prazo 15/7/3 dias, vencido, evidência e escalonamento — não é o registro oficial."
        )
    with st.expander("Eventos de notificação (e-mail primeiro)", expanded=False):
        st.table(pd.DataFrame(EVENTOS_NOTIFICACAO, columns=["evento", "descrição", "canal"]))
    st.caption(
        "Evidências e PDFs não entram no painel público. Integração de login institucional STI fica para etapa seguinte "
        "(vínculos em `plano_vinculo`)."
    )


def _render_cobranca(ctx: dict, user: dict | None) -> None:
    from sisclima.plano.cobranca import (
        csv_cobranca,
        exportar_rascunhos,
        relatorio_cobranca,
        rascunhos_email,
        texto_rascunho,
    )
    from sisclima.plano.conectores import coletar_automaticos
    from sisclima.plano.indicadores import linhas_painel_indicadores, quadro_indicadores
    from sisclima.plano.relatorio_pdf import pdf_bytes_cobranca

    try:
        leituras = _coleta_automaticos_cached()
    except Exception:  # noqa: BLE001
        leituras = coletar_automaticos()
    linhas = linhas_painel_indicadores(quadro=quadro_indicadores(so_indice=False), leituras_auto=leituras)
    rel = relatorio_cobranca(linhas)
    hoje = datetime.now().strftime("%Y%m%d")
    st.markdown("#### Ofício de cobrança")
    st.caption(
        "E-mail não dispara sozinho. Copie o rascunho, envie pelo correio da SES e peça à área "
        "para registrar na Sala. Cópia CIEVS: menandesneto@ses.mt.gov.br e tatianabelmonte@ses.mt.gov.br."
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Para a área informar", str(rel["n_cobrar_area"]))
    m2.metric("Aguardando fonte", str(rel["n_aguardar_fonte"]))
    m3.metric("Documentais sem SEI", str(rel["n_documentais"]))
    m4.metric("Carga defasada", str(rel["n_carga_defasada"]))
    if rel.get("areas_sem_focal"):
        nomes = ", ".join(a.get("area") or a.get("area_id") for a in rel["areas_sem_focal"])
        callout(f"Pontos focais ausentes no cadastro da Portaria 0590: {nomes} (IND-001 = 9/11).", "warn")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "Baixar PDF de cobrança",
            data=pdf_bytes_cobranca(rel),
            file_name=f"cobranca_indicadores_plano_{hoje}.pdf",
            mime="application/pdf",
            key="sala_tab_pdf_cobranca",
        )
    with c2:
        st.download_button(
            "Baixar CSV de cobrança",
            data=csv_cobranca(rel).encode("utf-8-sig"),
            file_name=f"cobranca_indicadores_plano_{hoje}.csv",
            mime="text/csv",
            key="sala_tab_csv_cobranca",
        )
    if ctx.get("pode_validar") or str((user or {}).get("nivel") or "") == "admin":
        if st.button("Gerar arquivos .txt dos rascunhos (pasta apresentações)", key="sala_btn_rascunhos"):
            pasta = exportar_rascunhos(relatorio=rel)
            st.success(f"Rascunhos em {pasta}")
    drafts = rascunhos_email(rel)
    st.markdown("#### Rascunhos por área")
    for i, draft in enumerate(drafts):
        titulo = f"{draft.get('area')} — {draft.get('para')}"
        with st.expander(titulo, expanded=i == 0):
            st.text_input("Para", draft.get("para") or "", key=f"cob_para_{i}", disabled=True)
            st.text_input("Cc", draft.get("cc") or "", key=f"cob_cc_{i}", disabled=True)
            st.text_input("Assunto", draft.get("assunto") or "", key=f"cob_ass_{i}", disabled=True)
            st.text_area("Corpo", draft.get("corpo") or "", height=220, key=f"cob_corpo_{i}")
            st.download_button(
                "Baixar este rascunho (.txt)",
                data=texto_rascunho(draft).encode("utf-8"),
                file_name=f"cobranca_{draft.get('area_id') or i}_{hoje}.txt",
                mime="text/plain",
                key=f"cob_dl_{i}",
            )


def _render_indicadores(ctx: dict, user: dict | None) -> None:
    from sisclima.plano.indicadores import (
        csv_painel_indicadores,
        cumprimento_indice,
        linhas_painel_indicadores,
        quadro_indicadores,
        registrar_leitura,
        resumo_painel_indicadores,
    )

    area_filtro = ctx.get("area_id") if ctx["perfil_plano"] in {"coordenador_area", "tecnico_area"} else None
    quadro = quadro_indicadores(area_id=area_filtro, so_indice=False)
    cump = cumprimento_indice(quadro)
    try:
        leituras = _coleta_automaticos_cached()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Coleta automática indisponível nesta sessão: {exc}")
        leituras = []
    linhas = linhas_painel_indicadores(quadro=quadro, leituras_auto=leituras, area_id=area_filtro)
    resumo_ind = resumo_painel_indicadores(linhas)

    st.markdown("#### Situação da coleta")
    st.caption(
        f"Fonte: {resumo_ind['n']} indicadores do catálogo · {resumo_ind['n_automaticos']} automáticos. "
        "Denominador estadual = 142 (IBGE 510000 excluído). Ausência de registro não vira zero."
    )
    i1, i2, i3, i4 = st.columns(4)
    i1.metric("Automáticos coletados", f"{resumo_ind['n_coletados']}/{resumo_ind['n_automaticos']}")
    i2.metric("Aguardando fonte", str(resumo_ind["n_aguardando"]))
    i3.metric("Índice operacional", f"{cump['percentual_operacional']:.0f}%")
    i4.metric("Índice oficial", f"{cump['percentual_oficial']:.0f}%" + (" · oficial" if cump["oficial"] else " · não oficial"))

    aguardando = [r for r in linhas if r.get("situacao") == "aguardando_fonte"]
    if aguardando:
        blocos = sorted({r.get("bloco_pendente") or "sem bloco" for r in aguardando})
        callout(
            "Sem conector nesta rodada: "
            + "; ".join(f"{b} ({sum(1 for r in aguardando if (r.get('bloco_pendente') or 'sem bloco') == b)})" for b in blocos)
            + ". O ARARAS não inventa valor.",
            "warn",
        )
    if any(r.get("nota") for r in linhas):
        callout(
            "IND-024, IND-025, IND-058 e IND-059 leem estoque; a carga pode estar defasada — "
            "não tratar como ruptura atual.",
            "info",
        )

    filtro = st.radio(
        "Filtro",
        [
            "Todos",
            "Automáticos",
            "Aguardando fonte",
            "Não informados pela área",
            "Do e-mail às áreas",
            "Sugeridos",
            "Onda 1 (Sim+SEI)",
            "Operacional",
            "Prontidão",
            "Gatilho",
            "Híbrido",
            "Classe A",
            "Classe B (parametrizar)",
            "Prontidão (C)",
            "Aliases (D)",
        ],
        horizontal=True,
        key="sala_filtro_ind",
    )
    visiveis = linhas
    if filtro == "Automáticos":
        visiveis = [r for r in linhas if r.get("modo") == "automatico"]
    elif filtro == "Aguardando fonte":
        visiveis = [r for r in linhas if r.get("situacao") == "aguardando_fonte"]
    elif filtro == "Não informados pela área":
        visiveis = [r for r in linhas if r.get("situacao") == "nao_informado"]
    elif filtro == "Do e-mail às áreas":
        visiveis = [r for r in linhas if r.get("bloco_pendente")]
    elif filtro == "Sugeridos":
        visiveis = [r for r in linhas if r.get("sugestao")]
    elif filtro == "Onda 1 (Sim+SEI)":
        visiveis = [r for r in linhas if str(r.get("onda") or "") == "1"]
    elif filtro == "Operacional":
        visiveis = [r for r in linhas if str(r.get("papel_operacional") or "") == "operacional"]
    elif filtro == "Prontidão":
        visiveis = [r for r in linhas if str(r.get("papel_operacional") or "") == "preparacao"]
    elif filtro == "Gatilho":
        visiveis = [r for r in linhas if str(r.get("papel_operacional") or "") == "gatilho"]
    elif filtro == "Híbrido":
        visiveis = [r for r in linhas if str(r.get("papel_operacional") or "") == "hibrido"]
    elif filtro == "Classe A":
        visiveis = [r for r in linhas if str(r.get("classe_emergencia") or "") == "A"]
    elif filtro == "Classe B (parametrizar)":
        visiveis = [r for r in linhas if str(r.get("classe_emergencia") or "") == "B"]
    elif filtro == "Prontidão (C)":
        visiveis = [r for r in linhas if str(r.get("classe_emergencia") or "") == "C" or r.get("gate_prontidao")]
    elif filtro == "Aliases (D)":
        visiveis = [r for r in linhas if str(r.get("classe_emergencia") or "") == "D"]

    df_ind = pd.DataFrame(
        [
            {
                "id": r["id"],
                "indicador": (r.get("nome") or "")[:90],
                "papel": r.get("papel_operacional") or "—",
                "área": r.get("area"),
                "modo": r.get("modo"),
                "situação": r.get("situacao"),
                "leitura": r.get("leitura"),
                "%": r.get("percentual"),
                "semáforo": r.get("semaforo"),
                "índice": "sim" if r.get("entra_no_indice") else "não",
                "fonte / motivo": r.get("fonte"),
                "sugestão": r.get("sugestao") or "—",
                "onda": r.get("onda") or "—",
                "classe": r.get("classe_emergencia") or "—",
                "S": r.get("perfil_s") or r.get("perfil_escalonamento") or "—",
                "C": r.get("padrao_completude") or "—",
                "completude": r.get("completude"),
                "bloco": r.get("bloco_pendente") or "—",
            }
            for r in visiveis
        ]
    )
    st.dataframe(df_ind, use_container_width=True, hide_index=True)
    hoje = datetime.now().strftime("%Y%m%d")
    from sisclima.plano.cobranca import csv_cobranca, relatorio_cobranca
    from sisclima.plano.relatorio_pdf import (
        pdf_bytes_cobranca,
        pdf_bytes_indicadores_automaticos,
        pdf_bytes_indicadores_plano,
    )

    autos = [r for r in linhas if r.get("modo") == "automatico"]
    cobranca = relatorio_cobranca(linhas)
    c_csv, c_pdf, c_pdf88, c_cob = st.columns(4)
    with c_csv:
        st.download_button(
            "Baixar relatório CSV da rodada",
            data=csv_painel_indicadores(linhas).encode("utf-8-sig"),
            file_name=f"indicadores_plano_el_nino_{hoje}.csv",
            mime="text/csv",
            key="sala_csv_ind",
        )
    with c_pdf:
        st.download_button(
            "Baixar PDF dos automáticos",
            data=pdf_bytes_indicadores_automaticos(autos),
            file_name=f"indicadores_automaticos_plano_{hoje}.pdf",
            mime="application/pdf",
            key="sala_pdf_auto",
        )
    with c_pdf88:
        st.download_button(
            "Baixar PDF dos 88",
            data=pdf_bytes_indicadores_plano(linhas),
            file_name=f"indicadores_plano_el_nino_{hoje}.pdf",
            mime="application/pdf",
            key="sala_pdf_88",
        )
    with c_cob:
        st.download_button(
            "Baixar PDF de cobrança às áreas",
            data=pdf_bytes_cobranca(cobranca),
            file_name=f"cobranca_indicadores_plano_{hoje}.pdf",
            mime="application/pdf",
            key="sala_pdf_cobranca",
        )
    st.download_button(
        "Baixar CSV de cobrança (e-mails da Portaria 0590)",
        data=csv_cobranca(cobranca).encode("utf-8-sig"),
        file_name=f"cobranca_indicadores_plano_{hoje}.csv",
        mime="text/csv",
        key="sala_csv_cobranca",
    )
    if cobranca.get("n_cobrar_area"):
        callout(
            f"{cobranca['n_cobrar_area']} indicadores para a área informar na Sala · "
            f"{cobranca['n_aguardar_fonte']} aguardando fonte · "
            f"{cobranca['n_documentais']} documentais sem SEI. "
            "O PDF de cobrança agrupa por área e e-mail da Portaria 0590.",
            "warn",
        )

    editaveis = [
        r
        for r in quadro
        if r.get("editavel") and pode_editar_area(user, str(r.get("area_id") or ""))
    ]
    if not editaveis:
        return
    st.markdown("#### Informar dado (a área não calcula o %)")
    opcoes = {f"{r['id']} — {r['nome'][:80]}": r for r in editaveis}
    escolha = st.selectbox("Indicador da sua área", list(opcoes), key="sala_ind_escolha")
    alvo = opcoes[escolha]
    if alvo.get("modo") == "documental":
        binario = st.radio("Documento / condição atendida?", ["Não", "Sim"], horizontal=True, key="sala_ind_doc")
        obs = st.text_input("Descrição da evidência (SEI, NT, ata…)", key="sala_ind_obs_doc")
        if st.button("Registrar e enviar à validação CIEVS", key="sala_ind_btn_doc"):
            ok, msg, _ = registrar_leitura(
                user=user,
                indicador_id=str(alvo["id"]),
                binario=binario == "Sim",
                observacao=obs,
                enviar_validacao=True,
            )
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()
    else:
        from sisclima.plano.sugestoes import sugerir_indicador

        iid = str(alvo["id"])
        sug = sugerir_indicador(iid) or {}
        if sug.get("nota") or sug.get("denominador") or sug.get("numerador") is not None:
            frac = ""
            if sug.get("denominador"):
                n_s = sug["numerador"] if sug.get("numerador") is not None else "—"
                frac = f" Valor sugerido (não gravado): {n_s}/{sug['denominador']}."
            st.info((str(sug.get("nota") or "Sugestão do ARARAS.") + frac).strip())
        den_catalogo = int(alvo.get("denominador") or 0)
        c_n, c_d = st.columns(2)
        numerador = c_n.number_input(
            "Realizado (numerador)",
            min_value=0,
            step=1,
            value=0,
            key=f"sala_ind_num_{iid}",
        )
        denominador = c_d.number_input(
            "Previsto (denominador)",
            min_value=1,
            step=1,
            value=max(den_catalogo, 1),
            key=f"sala_ind_den_{iid}",
        )
        obs = st.text_input("O que mudou nesta atualização", key=f"sala_ind_obs_{iid}")
        if st.button("Calcular e enviar à validação CIEVS", key="sala_ind_btn"):
            ok, msg, _ = registrar_leitura(
                user=user,
                indicador_id=str(alvo["id"]),
                numerador=float(numerador),
                denominador=float(denominador),
                observacao=obs,
                enviar_validacao=True,
            )
            st.success(msg) if ok else st.error(msg)
            if ok:
                st.rerun()


def _render_acoes(ctx: dict, user: dict | None) -> None:
    cat = carregar_catalogo()
    acoes = list(cat.get("acoes") or [])
    if not acoes:
        st.info("Catálogo de ações ainda não carregado.")
        return
    visiveis = acoes
    if ctx["perfil_plano"] in {"coordenador_area", "tecnico_area"} and ctx.get("area_id"):
        visiveis = [a for a in acoes if str(a.get("area_id") or "") == ctx["area_id"]]
        st.caption("Listando apenas a sua área (isolamento).")
    df = pd.DataFrame(
        [
            {
                "id": a.get("id"),
                "área": a.get("area_id"),
                "ação": (a.get("descricao") or "")[:180],
                "responsável": a.get("responsavel"),
                "prazo": a.get("prazo"),
                "prioridade": a.get("prioridade"),
                "pode_editar": pode_editar_area(user, str(a.get("area_id") or "")),
            }
            for a in visiveis
        ]
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_validacao(ctx: dict, user: dict | None) -> None:
    from sisclima.plano.acesso import pode_validar
    from sisclima.plano.indicadores import quadro_indicadores
    from sisclima.plano.operacao import validar_atualizacao

    if not pode_validar(user):
        st.info("A fila de validação é da secretaria-executiva CIEVS / administração ARARAS.")
        return
    area_filtro = ctx.get("area_id") if ctx["perfil_plano"] in {"coordenador_area", "tecnico_area"} else None
    quadro = quadro_indicadores(area_id=area_filtro, so_indice=False)
    fila = [r for r in quadro if r.get("situacao_validacao") == "em_validacao"]
    if not fila:
        st.info("Nenhum indicador em validação neste momento.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "id": r["id"],
                    "indicador": r["nome"],
                    "resultado": f"{r.get('numerador')}/{r.get('denominador')}",
                    "%": r.get("percentual"),
                }
                for r in fila
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    from sisclima.core.db import db_conn, fetchall

    with db_conn() as conn:
        pend = fetchall(
            conn,
            "SELECT id, alvo_codigo, valor FROM atualizacao WHERE alvo='indicador' AND situacao_validacao='em_validacao' ORDER BY id DESC",
        )
    if not pend:
        return
    labels = {f"#{p['id']} {p['alvo_codigo']} ({p['valor']})": int(p["id"]) for p in pend}
    escolhido = st.selectbox("Atualização a validar", list(labels), key="sala_val_escolha")
    decisao = st.radio("Decisão", ["validado", "rejeitado"], horizontal=True, key="sala_val_decisao")
    nota = st.text_input("Nota da validação", key="sala_val_nota")
    if st.button("Registrar validação", key="sala_val_btn"):
        ok, msg = validar_atualizacao(
            user=user,
            atualizacao_id=labels[escolhido],
            decisao=decisao,
            observacao=nota,
        )
        st.success(msg) if ok else st.error(msg)
        if ok:
            st.rerun()


def _render_acessos(user: dict | None) -> None:
    cap = capacidades_usuario(user)
    st.markdown("#### Esta sessão")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "e-mail": cap["email"] or "—",
                    "nível do painel": cap["nivel"],
                    "abre interno": "sim" if cap["abre_interno"] else "não",
                    "abre Sala": "sim" if cap["abre_sala"] else "não",
                    "perfil do Plano": cap["rotulo_perfil"] or "—",
                    "área": cap["area_rotulo"] or "sem vínculo de área",
                    "edita a própria área": "sim" if cap["pode_editar_area"] else "não",
                    "valida CIEVS": "sim" if cap["pode_validar"] else "não",
                }
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    st.markdown("#### Matriz do painel restrito")
    st.caption("Níveis do painel climático (cadastro). O perfil do Plano é um vínculo à parte.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Nível": r["rotulo"],
                    "Painel interno": r["abre_interno"],
                    "Sala / Plano": r["abre_sala"],
                    "Recorte": r["recorte"],
                    "Plano El Niño": r["plano"],
                }
                for r in MATRIZ_ACESSO_PAINEL
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    vinculos = listar_vinculos(so_ativos=True)
    from sisclima.plano.participantes import (
        aplicar_vinculos_catalogo,
        carregar_participantes,
        participantes_com_email,
    )

    cat = carregar_participantes()
    pessoas = participantes_com_email(cat)
    st.markdown("#### Participantes catalogados (Portaria 0590)")
    st.caption(
        f"Fonte: {cat.get('fonte') or 'config/plano_el_nino_participantes.yaml'} · "
        f"{len(pessoas)} com e-mail. Não cria senha. SMS não entra nesta Sala."
    )
    if pessoas:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "nome": p.get("nome"),
                        "e-mail": p.get("email"),
                        "perfil sugerido": p.get("perfil_rotulo"),
                        "área": p.get("area_rotulo"),
                        "papel": p.get("papel"),
                        "indicação": (p.get("status_indicacao") or "")[:80],
                    }
                    for p in pessoas
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    sem_email = cat.get("sem_email") or []
    if sem_email:
        st.caption("Sem e-mail no catálogo: " + "; ".join(sem_email))
    mun_est = cat.get("municipios_estrategicos") or []
    if mun_est:
        st.markdown("#### Municípios estratégicos da Portaria × e-mail SMS (COSEMS)")
        st.caption(
            f"{sum(1 for m in mun_est if m.get('email_sms'))}/{len(mun_est)} com e-mail. "
            "Validação operacional ainda PENDENTE — não abre a Sala e não dispara fan-out."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "município": m.get("municipio"),
                        "regional": m.get("regional_saude"),
                        "e-mail SMS": m.get("email_sms") or "—",
                        "indicação local": m.get("indicacao_local") or "—",
                    }
                    for m in mun_est
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### Vínculos ativos do Plano")
    if vinculos:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "e-mail": v.get("email"),
                        "perfil": v.get("perfil_rotulo"),
                        "área": v.get("area_rotulo") or "—",
                        "desde": str(v.get("criado_em") or "")[:19],
                    }
                    for v in vinculos
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhum vínculo em `plano_vinculo`. Conta ses entra como consulta; admin entra como administração ARARAS.")

    if not is_admin(user):
        st.caption("Somente administração grava vínculo de área. Municipal e regional não abrem esta Sala.")
        return
    st.markdown("#### Aplicar catálogo da Portaria")
    st.caption("Gera `plano_vinculo` para e-mails @ses.mt.gov.br / @saude.mt.gov.br. Não cria senha nem conta.")
    if st.button("Aplicar vínculos sugeridos do catálogo", key="sala_vinc_catalogo"):
        out = aplicar_vinculos_catalogo(ator_email=str((user or {}).get("email") or ""), so_institucional=True)
        if out["erros"]:
            st.error(" · ".join(out["erros"][:5]))
        st.success(f"{out['gravados']} vínculos gravados · {out['pulados']} e-mails não institucionais ignorados.")
        st.rerun()
    st.markdown("#### Gravar vínculo")
    emails = sorted({str(v.get("email") or "") for v in vinculos if v.get("email")})
    from sisclima.auth.access import list_users

    emails += [
        str(r.get("email") or "")
        for r in list_users()
        if str(r.get("nivel") or "") in {"ses", "admin"} and str(r.get("status") or "") == "ativo"
    ]
    emails = sorted({e for e in emails if e})
    if not emails:
        email = st.text_input("E-mail institucional", key="sala_vinc_email")
    else:
        email = st.selectbox("E-mail", emails, key="sala_vinc_email")
    perfil_opts = {lbl: key for key, lbl in PERFIS_PLANO}
    perfil_lbl = st.selectbox("Perfil do Plano", list(perfil_opts), key="sala_vinc_perfil")
    perfil = perfil_opts[perfil_lbl]
    area_opts = {lbl: key for key, lbl in AREAS_CANONICAS}
    precisa_area = perfil in {"coordenador_area", "tecnico_area"}
    area = ""
    if precisa_area or st.checkbox("Vincular a uma área", value=precisa_area, key="sala_vinc_area_chk"):
        area_lbl = st.selectbox("Área", list(area_opts), key="sala_vinc_area")
        area = area_opts[area_lbl]
    if st.button("Salvar vínculo", key="sala_vinc_btn"):
        ok, msg = gravar_vinculo(
            email=str(email or ""),
            perfil_plano=perfil,
            area_id=area,
            ator_email=str((user or {}).get("email") or ""),
        )
        st.success(msg) if ok else st.error(msg)
        if ok:
            st.rerun()
