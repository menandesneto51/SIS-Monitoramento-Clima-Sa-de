# -*- coding: utf-8 -*-
"""UI de controle de acesso: barra "Acesso restrito", login, cadastro, sessão e gestão.

O painel abre em modo público. Quem quiser acesso interno entra ou se cadastra
pelo botão "Acesso restrito" no topo. Cadastros municipal/regional/SES ficam
pendentes até um admin aprovar em "Gestão de cadastros e níveis".
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from sisclima.auth import access
from sisclima.core.db import read_table


@dataclass
class SessaoAcesso:
    user: dict | None
    papel: str
    status: str
    view: str  # 'publico' | 'interno' | 'gestao'
    escopo_regional: str | None = None
    escopo_municipios: list | None = None
    escopo_cod_ibge: list | None = None

    @property
    def autenticado(self) -> bool:
        return self.user is not None

    @property
    def pode_interno(self) -> bool:
        return self.papel in access.PAPEIS_INTERNOS and self.status == "ativo"

    @property
    def mostra_interno(self) -> bool:
        return self.view == "interno" and self.pode_interno

    @property
    def is_admin(self) -> bool:
        return self.papel == "admin" and self.status == "ativo"


_VIEW_LABEL = {
    "Painel interno": "interno",
    "Painel público": "publico",
    "Gestão de cadastros e níveis": "gestao",
}


@st.cache_data(show_spinner=False, ttl=120)
def _opcoes_territorio() -> tuple[list[tuple[str, str]], list[str]]:
    """Retorna (municípios [(label, cod_ibge)], regionais [str]) do resumo municipal."""
    df = read_table("resumo_municipal_atual")
    municipios: list[tuple[str, str]] = []
    regionais: list[str] = []
    if df is None or df.empty:
        return municipios, regionais
    if "municipio" in df.columns:
        base = df.copy()
        base["cod_ibge"] = base.get("cod_ibge", pd.Series(dtype=str)).astype(str)
        base = base.dropna(subset=["municipio"]).drop_duplicates("cod_ibge")
        for _, r in base.iterrows():
            nome = str(r.get("municipio"))
            cod = str(r.get("cod_ibge") or "")
            municipios.append((f"{nome}" + (f" ({cod})" if cod and cod != nome else ""), cod))
        municipios = sorted(municipios, key=lambda x: x[0])
    if "regional_saude" in df.columns:
        regionais = sorted(
            {str(x) for x in df["regional_saude"].dropna().astype(str) if x and x != "Regional não informada"}
        )
    return municipios, regionais


def _flash(kind: str, msg: str) -> None:
    st.session_state["araras_flash"] = (kind, msg)


def _consume_flash() -> None:
    flash = st.session_state.pop("araras_flash", None)
    if not flash:
        return
    kind, msg = flash
    {"success": st.success, "error": st.error, "warning": st.warning, "info": st.info}.get(kind, st.info)(msg)


def _form_login() -> None:
    with st.form("araras_login", clear_on_submit=False):
        st.markdown("**Entrar**")
        email = st.text_input("E-mail", key="araras_login_email")
        senha = st.text_input("Senha", type="password", key="araras_login_senha")
        ok = st.form_submit_button("Entrar", use_container_width=True)
    if ok:
        user = access.autenticar(email, senha)
        if user is None:
            _flash("error", "E-mail ou senha inválidos.")
        elif user.get("status") == "recusado":
            _flash("error", "Este cadastro foi recusado. Fale com o administrador do CIEVS.")
        else:
            st.session_state["araras_user"] = user
            if user.get("status") == "pendente":
                _flash("warning", "Login efetuado. Seu acesso interno está **pendente de aprovação**.")
            else:
                _flash("success", f"Bem-vindo(a), {user.get('nome') or user.get('email')}.")
                st.session_state["araras_view"] = (
                    "Gestão de cadastros e níveis" if user.get("papel") == "admin" else "Painel interno"
                )
        st.rerun()


def _form_cadastro() -> None:
    municipios, regionais = _opcoes_territorio()
    with st.form("araras_cadastro", clear_on_submit=False):
        st.markdown("**Criar cadastro**")
        nome = st.text_input("Nome completo", key="araras_cad_nome")
        email = st.text_input("E-mail institucional", key="araras_cad_email")
        senha = st.text_input("Senha (mín. 6 caracteres)", type="password", key="araras_cad_senha")
        nivel_label = st.selectbox(
            "Nível de acesso solicitado",
            ["Público", "Municipal (SMS)", "Regional (CRS)", "SES / CIEVS"],
            key="araras_cad_nivel",
            help="Municipal/Regional/SES aguardam aprovação de um administrador.",
        )
        papel = {
            "Público": "publico",
            "Municipal (SMS)": "municipal",
            "Regional (CRS)": "regional",
            "SES / CIEVS": "ses",
        }[nivel_label]

        muni_label = st.selectbox(
            "Município (para nível Municipal)",
            ["—"] + [m[0] for m in municipios],
            key="araras_cad_muni",
        ) if municipios else "—"
        regional_sel = st.selectbox(
            "Regional de Saúde (para nível Regional)",
            ["—"] + regionais,
            key="araras_cad_reg",
        ) if regionais else "—"

        ok = st.form_submit_button("Solicitar acesso", use_container_width=True)
    if ok:
        municipio = cod_ibge = regional = None
        if papel == "municipal":
            if muni_label and muni_label != "—":
                municipio = muni_label.split(" (")[0]
                cod_ibge = dict((m[0], m[1]) for m in municipios).get(muni_label)
        if papel == "regional" and regional_sel and regional_sel != "—":
            regional = regional_sel
        try:
            user = access.criar_usuario(
                email=email, senha=senha, nome=nome, papel=papel,
                municipio=municipio, cod_ibge=cod_ibge, regional=regional,
            )
            if user.get("status") == "ativo":
                st.session_state["araras_user"] = user
                _flash("success", "Cadastro público criado e ativado.")
            else:
                _flash("success", "Cadastro enviado. Aguarde a aprovação de um administrador do CIEVS.")
        except ValueError as exc:
            _flash("error", str(exc))
        except Exception as exc:  # noqa: BLE001
            _flash("error", f"Não foi possível cadastrar: {exc}")
        st.rerun()


def _abrir_login_cadastro() -> None:
    """Renderiza o acionador 'Acesso restrito' (popover quando disponível)."""
    popover = getattr(st, "popover", None)
    if popover is not None:
        with popover("🔒 Acesso restrito", use_container_width=True):
            tab_login, tab_cad = st.tabs(["Entrar", "Cadastrar"])
            with tab_login:
                _form_login()
            with tab_cad:
                _form_cadastro()
    else:
        with st.expander("🔒 Acesso restrito", expanded=False):
            tab_login, tab_cad = st.tabs(["Entrar", "Cadastrar"])
            with tab_login:
                _form_login()
            with tab_cad:
                _form_cadastro()


def _area_usuario(user: dict) -> None:
    nome = user.get("nome") or user.get("email")
    papel = user.get("papel", "publico")
    status = user.get("status", "ativo")
    escopo = user.get("municipio") or user.get("regional") or ""
    chip = f"👤 **{nome}** · {access.PAPEL_LABEL.get(papel, papel)}"
    if escopo:
        chip += f" · {escopo}"
    if status != "ativo":
        chip += f" · _{status}_"
    st.markdown(chip)
    if st.button("Sair", key="araras_logout", use_container_width=True):
        for k in ["araras_user", "araras_view"]:
            st.session_state.pop(k, None)
        _flash("info", "Você saiu do acesso restrito.")
        st.rerun()


def iniciar_acesso() -> SessaoAcesso:
    """Inicializa o controle de acesso, desenha a barra no topo e devolve a sessão."""
    access.ensure_schema()
    access.bootstrap_admin_from_env()

    user = st.session_state.get("araras_user")
    if user:
        fresh = access.get_user_by_email(user.get("email"))
        if fresh:
            user = fresh
            st.session_state["araras_user"] = fresh
        else:
            user = None
            st.session_state.pop("araras_user", None)

    _consume_flash()

    col_esq, col_dir = st.columns([5, 2])
    with col_dir:
        if user is None:
            _abrir_login_cadastro()
        else:
            _area_usuario(user)

    papel = (user or {}).get("papel", "publico")
    status = (user or {}).get("status", "ativo")
    pode_interno = papel in access.PAPEIS_INTERNOS and status == "ativo"

    # Alternador de visão (apenas para contas internas ativas)
    view = "publico"
    if pode_interno:
        opcoes = ["Painel interno", "Painel público"]
        if papel == "admin":
            opcoes.append("Gestão de cadastros e níveis")
        if st.session_state.get("araras_view") not in opcoes:
            st.session_state["araras_view"] = opcoes[0]
        escolha = st.radio(
            "Visão",
            opcoes,
            horizontal=True,
            key="araras_view",
            label_visibility="collapsed",
        )
        view = _VIEW_LABEL.get(escolha, "interno")
    elif user is not None and status == "pendente":
        st.info("Seu acesso interno está **pendente de aprovação**. Enquanto isso, você vê o painel público.")

    escopo_regional = escopo_municipios = escopo_cod_ibge = None
    if pode_interno and papel == "municipal":
        if user.get("cod_ibge"):
            escopo_cod_ibge = [str(user.get("cod_ibge"))]
        if user.get("municipio"):
            escopo_municipios = [str(user.get("municipio"))]
    elif pode_interno and papel == "regional" and user.get("regional"):
        escopo_regional = str(user.get("regional"))

    return SessaoAcesso(
        user=user,
        papel=papel,
        status=status,
        view=view,
        escopo_regional=escopo_regional,
        escopo_municipios=escopo_municipios,
        escopo_cod_ibge=escopo_cod_ibge,
    )


def aplicar_escopo(df: pd.DataFrame, sessao: SessaoAcesso) -> pd.DataFrame:
    """Recorta um dataframe ao território da conta (municipal por cod_ibge, regional por regional_saude)."""
    if df is None or df.empty:
        return df
    out = df
    if sessao.escopo_cod_ibge and "cod_ibge" in out.columns:
        out = out[out["cod_ibge"].astype(str).isin([str(c) for c in sessao.escopo_cod_ibge])]
    elif sessao.escopo_regional and "regional_saude" in out.columns:
        out = out[out["regional_saude"].astype(str) == sessao.escopo_regional]
    return out


# --------------------------------------------------------------------------- #
# Painel de gestão (admin)
# --------------------------------------------------------------------------- #
def render_gestao(sessao: SessaoAcesso) -> None:
    from sisclima.ui import theme as ui_theme

    ui_theme.section_title(
        "Gestão de cadastros e níveis",
        "Aprovar solicitações, definir território e ajustar níveis de acesso (somente admin).",
    )
    if not sessao.is_admin:
        st.error("Acesso restrito a administradores.")
        return

    municipios, regionais = _opcoes_territorio()
    muni_labels = [m[0] for m in municipios]
    muni_map = {m[0]: m[1] for m in municipios}
    admin_email = (sessao.user or {}).get("email")

    pendentes = access.list_users(status="pendente")
    st.markdown(f"#### Solicitações pendentes ({len(pendentes)})")
    if not pendentes:
        st.info("Nenhuma solicitação pendente.")
    for u in pendentes:
        with st.container(border=True):
            st.markdown(
                f"**{u.get('nome')}** · {u.get('email')} · solicitou "
                f"**{access.PAPEL_LABEL.get(u.get('papel'), u.get('papel'))}**"
                + (f" · {u.get('municipio') or u.get('regional') or ''}" if (u.get('municipio') or u.get('regional')) else "")
            )
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            with c1:
                papel_sel = st.selectbox(
                    "Nível",
                    ["municipal", "regional", "ses", "admin"],
                    index=["municipal", "regional", "ses", "admin"].index(u.get("papel"))
                    if u.get("papel") in ["municipal", "regional", "ses", "admin"] else 0,
                    key=f"gp_papel_{u['id']}",
                    format_func=lambda p: access.PAPEL_LABEL.get(p, p),
                )
            with c2:
                muni_default = 0
                if u.get("municipio") in muni_labels:
                    muni_default = muni_labels.index(u.get("municipio")) + 1
                if papel_sel == "municipal":
                    muni_pick = st.selectbox("Município", ["—"] + muni_labels, index=muni_default, key=f"gp_muni_{u['id']}")
                    reg_pick = "—"
                elif papel_sel == "regional":
                    reg_pick = st.selectbox("Regional", ["—"] + regionais, key=f"gp_reg_{u['id']}")
                    muni_pick = "—"
                else:
                    st.caption("Sem recorte territorial (estadual).")
                    muni_pick = reg_pick = "—"
            with c3:
                aprovar = st.button("Aprovar", key=f"gp_ok_{u['id']}", use_container_width=True)
            with c4:
                recusar = st.button("Recusar", key=f"gp_no_{u['id']}", use_container_width=True)
            if aprovar:
                municipio = cod_ibge = regional = None
                if papel_sel == "municipal" and muni_pick != "—":
                    municipio = muni_pick.split(" (")[0]
                    cod_ibge = muni_map.get(muni_pick)
                if papel_sel == "regional" and reg_pick != "—":
                    regional = reg_pick
                access.aprovar_usuario(
                    u["id"], papel_sel, municipio=municipio, cod_ibge=cod_ibge, regional=regional, admin_email=admin_email
                )
                _flash("success", f"Acesso de {u.get('email')} aprovado como {access.PAPEL_LABEL.get(papel_sel)}.")
                st.rerun()
            if recusar:
                access.recusar_usuario(u["id"], admin_email=admin_email)
                _flash("info", f"Solicitação de {u.get('email')} recusada.")
                st.rerun()

    st.divider()
    todos = access.list_users()
    st.markdown(f"#### Todos os cadastros ({len(todos)})")
    if todos:
        tabela = pd.DataFrame(todos)
        cols = [c for c in ["id", "nome", "email", "papel", "status", "municipio", "regional", "criado_em", "aprovado_por"] if c in tabela.columns]
        try:
            st.dataframe(tabela[cols], width="stretch", height=280)
        except TypeError:
            st.dataframe(tabela[cols], use_container_width=True, height=280)

        st.markdown("##### Ajustar um cadastro")
        emails = [u["email"] for u in todos]
        alvo = st.selectbox("Cadastro", emails, key="gestao_alvo")
        u = next((x for x in todos if x["email"] == alvo), None)
        if u:
            c1, c2, c3 = st.columns(3)
            with c1:
                papel_sel = st.selectbox(
                    "Nível", access.PAPEIS,
                    index=access.PAPEIS.index(u.get("papel")) if u.get("papel") in access.PAPEIS else 0,
                    key="gestao_papel", format_func=lambda p: access.PAPEL_LABEL.get(p, p),
                )
            with c2:
                status_sel = st.selectbox(
                    "Status", ["ativo", "pendente", "recusado"],
                    index=["ativo", "pendente", "recusado"].index(u.get("status")) if u.get("status") in ["ativo", "pendente", "recusado"] else 0,
                    key="gestao_status",
                )
            with c3:
                if papel_sel == "municipal":
                    muni_idx = muni_labels.index(u.get("municipio")) + 1 if u.get("municipio") in muni_labels else 0
                    territorio = st.selectbox("Município", ["—"] + muni_labels, index=muni_idx, key="gestao_muni")
                elif papel_sel == "regional":
                    territorio = st.selectbox("Regional", ["—"] + regionais, key="gestao_reg")
                else:
                    territorio = "—"
                    st.caption("Sem recorte (estadual).")
            if st.button("Salvar alterações", key="gestao_salvar"):
                municipio = cod_ibge = regional = None
                if papel_sel == "municipal" and territorio != "—":
                    municipio = territorio.split(" (")[0]
                    cod_ibge = muni_map.get(territorio)
                if papel_sel == "regional" and territorio != "—":
                    regional = territorio
                access.definir_papel_status(
                    u["id"], papel_sel, status_sel,
                    municipio=municipio, cod_ibge=cod_ibge, regional=regional, admin_email=admin_email,
                )
                _flash("success", f"Cadastro de {alvo} atualizado.")
                st.rerun()
