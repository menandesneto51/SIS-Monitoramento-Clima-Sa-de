# -*- coding: utf-8 -*-
"""Botão de acesso restrito, login, cadastro e gestão de níveis."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from sisclima.auth.access import (
    GATE_KEY,
    MODO_KEY,
    NIVEIS,
    authenticate,
    catalogo_municipios,
    catalogo_regionais,
    current_user,
    is_interno,
    list_users,
    login_to_session,
    lookup_territorio,
    logout_session,
    register_user,
    rotulo_nivel,
    set_user_status,
)


def render_access_bar(
    regionais: list[str] | None = None,
    municipios: list[str] | None = None,
) -> dict | None:
    """Faixa superior: botão Acesso restrito, sessão e troca público/interno."""
    user = current_user()
    left, right = st.columns([2.4, 1.6])
    with left:
        if user:
            st.caption(
                f"**{user.get('nome')}** · {rotulo_nivel(str(user.get('nivel') or 'publico'))}"
                + (f" · {user.get('municipio')}" if user.get("municipio") else "")
                + (f" · {user.get('regional_saude')}" if user.get("regional_saude") and not user.get("municipio") else "")
            )
        else:
            st.caption("Painel público · dados agregados do Estado. Decisões operacionais exigem acesso restrito.")
    with right:
        c1, c2 = st.columns(2)
        if user:
            if is_interno(user):
                modo = str(st.session_state.get(MODO_KEY) or "interno")
                if modo == "interno":
                    if c1.button("Painel público", key="btn_ver_publico"):
                        st.session_state[MODO_KEY] = "publico"
                        st.rerun()
                else:
                    if c1.button("Painel interno", key="btn_ver_interno"):
                        st.session_state[MODO_KEY] = "interno"
                        st.rerun()
            if c2.button("Sair", key="btn_logout_araras"):
                logout_session(st.session_state)
                st.rerun()
        else:
            abrir = bool(st.session_state.get(GATE_KEY))
            if c2.button("Acesso restrito", key="btn_acesso_restrito", type="primary"):
                st.session_state[GATE_KEY] = not abrir
                st.rerun()
    if not user and st.session_state.get(GATE_KEY):
        render_acesso_restrito(regionais=regionais, municipios=municipios)
    return user


def render_acesso_restrito(regionais: list[str] | None = None, municipios: list[str] | None = None) -> None:
    st.markdown("#### Área de acesso restrito")
    st.caption(
        "Público fica ativo na hora. Municipal (SMS), Regional (CRS) e SES/CIEVS aguardam aprovação. "
        "Nível administrador não pode ser autoatribuído."
    )
    regs = list(regionais or catalogo_regionais())
    muns = list(municipios or catalogo_municipios())
    tab_login, tab_cadastro = st.tabs(["Entrar", "Cadastrar"])
    with tab_login:
        from sisclima.auth.sti_oidc import novo_state, sti_pronto, url_autorizacao, concluir_login_sti

        params = st.query_params
        code = str(params.get("code") or "")
        state_q = str(params.get("state") or "")
        if code and state_q and state_q == str(st.session_state.get("sti_oidc_state") or ""):
            user_sti, msg_sti = concluir_login_sti(code)
            st.query_params.clear()
            if user_sti:
                login_to_session(user_sti, st.session_state)
                st.success("Acesso institucional STI reconhecido.")
                st.rerun()
            else:
                st.error(msg_sti)
        if sti_pronto():
            st.caption("Conta SES/MT: entre com o login institucional da STI (OpenID).")
            if st.button("Entrar com conta SES / STI", type="primary"):
                state, nonce = novo_state()
                st.session_state["sti_oidc_state"] = state
                st.session_state["sti_oidc_nonce"] = nonce
                st.link_button("Continuar na STI", url_autorizacao(state=state, nonce=nonce))
            st.divider()
            st.caption("Ou use e-mail e senha locais (cadastro ARARAS).")
        with st.form("form_login_araras"):
            email = st.text_input("E-mail institucional")
            senha = st.text_input("Senha", type="password")
            ok = st.form_submit_button("Entrar", type="primary")
        if ok:
            user, msg = authenticate(email, senha)
            if user:
                login_to_session(user, st.session_state)
                st.success(f"Olá, {user.get('nome')}.")
                st.rerun()
            else:
                st.error(msg)
    with tab_cadastro:
        niveis_opts = {lbl: key for key, lbl in NIVEIS if key != "admin"}
        nivel_lbl = st.selectbox("Nível solicitado", list(niveis_opts.keys()), key="cad_nivel_lbl")
        nivel = niveis_opts[nivel_lbl]
        regional = ""
        municipio = ""
        if nivel == "municipal":
            municipio = st.selectbox("Município (SMS)", muns, key="cad_municipio") if muns else st.text_input(
                "Município (SMS)", key="cad_municipio_txt"
            )
            _m, regional, _ibge = lookup_territorio(municipio=str(municipio or ""))
            if regional:
                st.caption(f"Regional de Saúde: **{regional}**")
        elif nivel == "regional":
            regional = st.selectbox("Regional de Saúde (CRS)", regs, key="cad_regional") if regs else st.text_input(
                "Regional de Saúde (CRS)", key="cad_regional_txt"
            )
        with st.form("form_cadastro_araras"):
            nome = st.text_input("Nome completo")
            email = st.text_input("E-mail institucional")
            instituicao = st.text_input("Instituição (SMS, CRS, CIEVS, SES…)")
            senha = st.text_input("Senha (mín. 8 caracteres)", type="password")
            senha2 = st.text_input("Confirme a senha", type="password")
            enviar = st.form_submit_button("Enviar cadastro")
        if enviar:
            if senha != senha2:
                st.error("As senhas não coincidem.")
            else:
                ok_reg, msg = register_user(
                    email=email,
                    nome=nome,
                    password=senha,
                    instituicao=instituicao,
                    nivel_solicitado=nivel,
                    regional_saude=regional,
                    municipio=municipio,
                )
                if ok_reg:
                    st.success(msg)
                else:
                    st.error(msg)


def render_gestao_usuarios() -> None:
    rows = list_users()
    if not rows:
        st.info("Nenhum cadastro ainda.")
        return
    view = pd.DataFrame(rows)
    cols = [
        c
        for c in [
            "email",
            "nome",
            "instituicao",
            "nivel_solicitado",
            "nivel",
            "status",
            "regional_saude",
            "municipio",
            "criado_em",
        ]
        if c in view.columns
    ]
    st.dataframe(view[cols], width="stretch", height=280)
    pendentes = [r for r in rows if str(r.get("status") or "") == "pendente"]
    alvo_opts = [str(r.get("email")) for r in rows if str(r.get("status") or "") == "pendente"]
    alvo_opts += [str(r.get("email")) for r in rows if str(r.get("email")) not in alvo_opts]
    if not alvo_opts:
        return
    email = st.selectbox("Usuário", alvo_opts, key="admin_user_email")
    escolhido = next((r for r in rows if str(r.get("email")) == email), {}) or {}
    pedido = str(escolhido.get("nivel_solicitado") or "ses")
    niveis = [k for k, _ in NIVEIS]
    nivel = st.selectbox(
        "Nível a conceder",
        niveis,
        index=niveis.index(pedido) if pedido in niveis else niveis.index("ses"),
        help="Administração não é autoatribuída no cadastro; só um admin pode conceder este nível.",
    )
    if escolhido.get("municipio") or escolhido.get("regional_saude"):
        st.caption(
            f"Território do cadastro: {escolhido.get('municipio') or '—'} · "
            f"{escolhido.get('regional_saude') or '—'}"
        )
    c1, c2, c3 = st.columns(3)
    admin = current_user() or {}
    who = str(admin.get("email") or "admin")
    if c1.button("Aprovar / ativar", key="admin_aprovar"):
        ok, msg = set_user_status(email, status="ativo", nivel=nivel, aprovado_por=who)
        st.success(msg) if ok else st.error(msg)
        st.rerun()
    if c2.button("Recusar", key="admin_recusar"):
        ok, msg = set_user_status(email, status="recusado", nivel="publico", aprovado_por=who)
        st.success(msg) if ok else st.error(msg)
        st.rerun()
    if c3.button("Suspender", key="admin_suspender"):
        ok, msg = set_user_status(email, status="suspenso", aprovado_por=who)
        st.success(msg) if ok else st.error(msg)
        st.rerun()
    if pendentes:
        st.caption(f"{len(pendentes)} cadastro(s) aguardando aprovação.")
    if str(escolhido.get("nivel") or pedido) in {"ses", "admin"} or nivel in {"ses", "admin"}:
        st.markdown("##### Vínculo do Plano El Niño")
        st.caption("A Sala só abre para ses/admin. Coordenador e técnico precisam da área.")
        from sisclima.plano.acesso import gravar_vinculo
        from sisclima.plano.areas import AREAS_CANONICAS
        from sisclima.plano.constants import PERFIS_PLANO

        perfil_opts = {lbl: key for key, lbl in PERFIS_PLANO}
        perfil_lbl = st.selectbox("Perfil do Plano", list(perfil_opts), key="admin_perfil_plano")
        area_opts = {lbl: key for key, lbl in AREAS_CANONICAS}
        area_lbl = st.selectbox("Área (se coordenador/técnico)", ["—"] + list(area_opts), key="admin_area_plano")
        if st.button("Gravar vínculo do Plano", key="admin_vinc_plano"):
            area = "" if area_lbl == "—" else area_opts[area_lbl]
            ok_v, msg_v = gravar_vinculo(
                email=email,
                perfil_plano=perfil_opts[perfil_lbl],
                area_id=area,
                ator_email=who,
            )
            st.success(msg_v) if ok_v else st.error(msg_v)
