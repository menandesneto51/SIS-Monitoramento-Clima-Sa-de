# -*- coding: utf-8 -*-
"""Aba interna: notificar e triar eventos em saúde (padrão CIEVS)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from sisclima.auth.access import catalogo_municipios, current_user, lookup_territorio
from sisclima.engines.eventos_saude import (
    SITUACAO_LABEL,
    SITUACOES,
    TIPO_LABEL,
    TIPOS,
    criar_evento,
    listar_eventos,
    pode_notificar,
    pode_triar,
    recorte_eventos,
    resumo_fila,
    triar_evento,
)
from sisclima.ui.theme import callout, insight_cards, section_title


def _mun_options(user: dict, resumo: pd.DataFrame) -> list[str]:
    rec = recorte_eventos(user)
    if rec.get("municipio"):
        return [rec["municipio"]]
    if rec.get("regional_saude"):
        return catalogo_municipios(rec["regional_saude"]) or []
    if resumo is not None and not resumo.empty and "municipio" in resumo.columns:
        return sorted(resumo["municipio"].dropna().astype(str).unique().tolist())
    return catalogo_municipios()


def _ibge_regional(municipio: str, resumo: pd.DataFrame) -> tuple[str, str]:
    mun, reg, ibge = lookup_territorio(municipio=municipio)
    if (not ibge or not reg) and resumo is not None and not resumo.empty:
        hit = resumo[resumo["municipio"].astype(str).str.casefold() == municipio.casefold()]
        if not hit.empty:
            row = hit.iloc[0]
            ibge = ibge or str(row.get("cod_ibge") or "")
            reg = reg or str(row.get("regional_saude") or "")
    return ibge, reg


def render_eventos_saude(resumo: pd.DataFrame) -> None:
    user = current_user()
    section_title(
        "Eventos em saúde",
        "Canal CIEVS para rumor, cluster e impacto climático — não substitui o SINAN",
    )
    callout(
        "Use esta ficha para o que o município/regional está vendo no território "
        "(calor, fumaça, estiagem, fogo, surto). Não informe nome, CPF nem prontuário.",
        "info",
    )
    if not pode_notificar(user):
        st.warning("Entre com acesso municipal, regional ou SES/CIEVS para notificar ou triar.")
        return

    df = listar_eventos(user)
    fila = resumo_fila(df)
    insight_cards(
        [
            ("Na fila (rumor)", str(fila.get("rumor", 0)), "aguardando verificação"),
            ("Em verificação", str(fila.get("em_verificacao", 0)), "CIEVS/CRS"),
            ("Confirmados", str(fila.get("confirmado", 0)), "em acompanhamento"),
            ("Registros", str(len(df)), "no recorte da sua conta"),
        ]
    )

    tab_form, tab_fila, tab_mapa = st.tabs(["Notificar", "Fila de triagem", "Mapa"])

    with tab_form:
        muns = _mun_options(user, resumo)
        if not muns:
            st.error("Catálogo municipal indisponível.")
            return
        mun = st.selectbox("Município", muns, index=0)
        ibge, reg = _ibge_regional(mun, resumo)
        c1, c2, c3 = st.columns(3)
        tipo = c1.selectbox("Tipo", [k for k, _ in TIPOS], format_func=lambda k: TIPO_LABEL[k])
        data_ev = c2.date_input("Data do evento", value=date.today())
        n_af = c3.number_input("N.º aproximado de afetados (opcional)", min_value=0, value=0, step=1)
        terr = st.text_input("Território tradicional / local (opcional)", placeholder="aldeia, quilombo, comunidade, bairro…")
        cobrade = st.text_input("COBRADE / código de desastre (opcional)")
        desc = st.text_area(
            "O que está acontecendo",
            placeholder="Fatos, local, duração, serviços afetados. Sem identificação de paciente.",
            height=120,
        )
        anexo = st.text_input("Link de ofício/foto/decreto (opcional)")
        if st.button("Registrar evento", type="primary"):
            ok, msg, uid = criar_evento(
                user=user,
                municipio=mun,
                tipo=tipo,
                descricao=desc,
                data_evento=data_ev.isoformat(),
                cod_ibge=ibge,
                regional_saude=reg,
                n_afetados_aprox=int(n_af) or None,
                territorio_tradicional=terr,
                cobrade=cobrade,
                link_anexo=anexo,
            )
            if ok:
                st.success(f"{msg} Protocolo {uid}.")
                st.rerun()
            else:
                st.error(msg)

    with tab_fila:
        if df.empty:
            st.info("Nenhum evento no recorte da sua conta.")
        else:
            cols = [
                c
                for c in [
                    "criado_em",
                    "municipio",
                    "tipo_rotulo",
                    "situacao_rotulo",
                    "data_evento",
                    "n_afetados_aprox",
                    "descricao",
                    "notificado_por_nome",
                    "uid",
                ]
                if c in df.columns
            ]
            st.dataframe(df[cols], use_container_width=True, hide_index=True, height=360)
            if pode_triar(user):
                st.markdown("#### Triagem CIEVS")
                uid_sel = st.selectbox("Protocolo", df["uid"].astype(str).tolist())
                nova = st.selectbox(
                    "Nova situação",
                    [k for k, _ in SITUACOES],
                    format_func=lambda k: SITUACAO_LABEL[k],
                )
                nota = st.text_input("Nota de triagem (opcional)")
                if st.button("Atualizar situação"):
                    ok, msg = triar_evento(user=user, uid=uid_sel, situacao=nova, nota=nota)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
            else:
                st.caption("A triagem (confirmar/encerrar/descartar) é exclusiva SES/CIEVS.")

    with tab_mapa:
        _mapa(df, resumo)


def _mapa(df: pd.DataFrame, resumo: pd.DataFrame) -> None:
    if df is None or df.empty:
        st.info("Sem eventos para mapear.")
        return
    geo = resumo.copy() if resumo is not None else pd.DataFrame()
    lat_col = next((c for c in ("lat", "latitude") if geo is not None and c in geo.columns), None)
    lon_col = next((c for c in ("lon", "longitude") if geo is not None and c in geo.columns), None)
    if geo.empty or not lat_col or not lon_col or "municipio" not in geo.columns:
        st.caption("Mapa pontual indisponível neste recorte — listando municípios com evento.")
        if "municipio" in df.columns:
            st.dataframe(
                df.groupby(
                    [c for c in ["municipio", "situacao_rotulo"] if c in df.columns],
                    as_index=False,
                ).size(),
                hide_index=True,
            )
        return
    pts = df.merge(geo[["municipio", lat_col, lon_col]].drop_duplicates("municipio"), on="municipio", how="inner")
    pts[lat_col] = pd.to_numeric(pts[lat_col], errors="coerce")
    pts[lon_col] = pd.to_numeric(pts[lon_col], errors="coerce")
    pts = pts.dropna(subset=[lat_col, lon_col])
    if pts.empty:
        st.caption("Eventos sem coordenada municipal no recorte.")
        return
    import plotly.express as px

    kwargs = dict(
        lat=lat_col,
        lon=lon_col,
        color="situacao_rotulo" if "situacao_rotulo" in pts.columns else None,
        hover_name="municipio",
        hover_data=[c for c in ["tipo_rotulo", "data_evento"] if c in pts.columns],
        zoom=4.5,
        height=420,
    )
    try:
        fig = px.scatter_map(pts, **kwargs)
        fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=0, b=0))
    except Exception:
        fig = px.scatter_geo(
            pts,
            lat=lat_col,
            lon=lon_col,
            color="situacao_rotulo" if "situacao_rotulo" in pts.columns else None,
            hover_name="municipio",
            height=420,
        )
        fig.update_geos(fitbounds="locations", visible=False, lataxis_range=[-18.6, -7.0], lonaxis_range=[-62.0, -50.0])
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, use_container_width=True)
