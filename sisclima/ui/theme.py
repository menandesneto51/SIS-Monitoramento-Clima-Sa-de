# -*- coding: utf-8 -*-
"""Tema visual alinhado ao portal oficial SES-MT (saude.mt.gov.br).

Tokens de css/style.css do portal:
- topo/footer: linear-gradient(#000444 → #1d357f)
- faixa navbar: #0071bb
- títulos/links: #1351b4
- tipografia: UniNeueRegular / UniNeueHeavy
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import streamlit as st

from sisclima.ui.explainers import INDICATOR_GLOSSARY, level_plain, section_plain

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
LOGO_PATH = ASSETS / "ses-logo.jpg"
CSS_PATH = ASSETS / "ses-panel.css"
FONT_REG = ASSETS / "fonts" / "uni-neue-regular.otf"
FONT_HEAVY = ASSETS / "fonts" / "uni-neue-heavy.otf"

SES_BLUE = "#1351B4"
SES_BLUE_DEEP = "#1D357F"
SES_BLUE_NAVY = "#000444"
SES_BLUE_ACCENT = "#0071BB"
SES_BG = "#F8F8F8"

LEVEL_COLOR_MAP = {
    "cinza": "#6b7280",
    "verde": "#16803c",
    "amarela": "#c49200",
    "laranja": "#d97706",
    "vermelha": "#dc2626",
    "roxa": "#6d28d9",
}

LAYOUT_VERSION = "SES-MT layout 2026-07-31 · azul institucional"


def _render_html(fragment: str) -> None:
    compact = " ".join(line.strip() for line in fragment.splitlines() if line.strip())
    # Preferir markdown+style (aplica no app). st.html também serve para blocos.
    st.markdown(compact, unsafe_allow_html=True)


def _font_face_block() -> str:
    """Fontes locais via file:// não funcionam no browser; usa data-URI só das fontes."""
    import base64

    parts = []
    if FONT_REG.exists():
        b64 = base64.b64encode(FONT_REG.read_bytes()).decode("ascii")
        parts.append(
            "@font-face{font-family:UniNeueRegular;src:url(data:font/otf;base64,"
            f"{b64}) format('opentype');font-weight:400;font-display:swap;}}"
        )
    if FONT_HEAVY.exists():
        b64 = base64.b64encode(FONT_HEAVY.read_bytes()).decode("ascii")
        parts.append(
            "@font-face{font-family:UniNeueHeavy;src:url(data:font/otf;base64,"
            f"{b64}) format('opentype');font-weight:800;font-display:swap;}}"
        )
    return "".join(parts)


def apply_theme() -> None:
    """Injeta CSS SES de forma confiável (sem depender de CSS gigante único)."""
    base_css = CSS_PATH.read_text(encoding="utf-8") if CSS_PATH.exists() else ""
    # Remove @font-face relativos do arquivo (não resolvem no Streamlit)
    cleaned = []
    skip = False
    for line in base_css.splitlines():
        if "@font-face" in line:
            skip = True
        if skip:
            if "}" in line:
                skip = False
            continue
        cleaned.append(line)
    body_css = "\n".join(cleaned)
    # Fallback tipográfico institucional (Calibri/Segoe) — evita injetar ~240KB de
    # base64 que em alguns clientes Streamlit falha silenciosamente e deixa o tema antigo.
    fallback_fonts = (
        "html,body,[class*=\"css\"],.stApp{"
        "font-family:Calibri,\"Segoe UI\",Tahoma,Geneva,Verdana,sans-serif!important}"
        "h1,h2,h3,h4,h5,h6,.sis-brand,.sis-section-title,.ses-masthead-brand,.sis-insight .v{"
        "font-family:Calibri,\"Segoe UI\",Tahoma,Geneva,Verdana,sans-serif!important;"
        "color:#1351B4!important}"
    )
    st.markdown(f"<style>{fallback_fonts}\n{body_css}</style>", unsafe_allow_html=True)
    # Selo visível para confirmar que o painel novo carregou
    st.markdown(
        f'<div style="background:#1351B4;color:#fff;padding:6px 12px;font:700 12px/1.3 Calibri,Segoe UI,sans-serif;'
        f'letter-spacing:.03em;text-transform:uppercase;margin:0 0 8px 0">{html.escape(LAYOUT_VERSION)}</div>',
        unsafe_allow_html=True,
    )


def ses_masthead(
    *,
    sistema: str = "SIS Clima-Saúde MT",
    subtitulo: str = "Sala de situação clima–saúde · CIEVS / SES-MT",
    base: str = "",
) -> None:
    """Chrome institucional no padrão do portal saude.mt.gov.br."""
    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    # Topo com estilo INLINE (garante azul mesmo se CSS falhar)
    st.markdown(
        f"""
        <div style="background:linear-gradient(to right,#000444 0%,#1d357f 40%,#1d357f 60%,#000444 100%);
                    color:#fff;padding:10px 14px;display:flex;flex-wrap:wrap;gap:8px 16px;
                    justify-content:space-between;align-items:center;font:400 13px UniNeueRegular,Calibri,sans-serif;">
          <div><strong style="font-family:UniNeueHeavy,Calibri,sans-serif;">Governo de Mato Grosso</strong>
            &nbsp;|&nbsp; Secretaria de Estado de Saúde &nbsp;|&nbsp; CIEVS</div>
          <div>
            <a href="https://www.saude.mt.gov.br/" target="_blank" rel="noopener" style="color:#fff;text-decoration:underline;">saude.mt.gov.br</a>
            &nbsp;|&nbsp;
            <a href="https://www.mt.gov.br/" target="_blank" rel="noopener" style="color:#fff;text-decoration:underline;">mt.gov.br</a>
            &nbsp;|&nbsp; {html.escape(hoje)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_logo, c_title, c_meta = st.columns([1.2, 3.2, 1.8], vertical_alignment="center")
    with c_logo:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=190)
        else:
            st.markdown("**SES-MT**")
    with c_title:
        st.markdown(
            f"""
            <div style="border-bottom:10px solid #0071bb;padding:6px 0 10px 0;">
              <div style="font:800 22px UniNeueHeavy,Calibri,sans-serif;color:#1351B4;">{html.escape(sistema)}</div>
              <div style="color:#57595A;font:400 14px UniNeueRegular,Calibri,sans-serif;margin-top:4px;">{html.escape(subtitulo)}</div>
              <div style="display:inline-block;margin-top:8px;background:#0071BB;color:#fff;padding:3px 8px;
                          font:700 11px UniNeueHeavy,Calibri,sans-serif;letter-spacing:.04em;text-transform:uppercase;">
                Layout oficial SES-MT
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c_meta:
        st.markdown(
            f"""
            <div style="text-align:right;color:#57595A;font:400 12px UniNeueRegular,Calibri,sans-serif;line-height:1.4;">
              <span style="display:block;font:800 14px UniNeueHeavy,Calibri,sans-serif;color:#1351B4;">SES-MT · CIEVS</span>
              Vigilância integrada clima–saúde
              {f"<br/>Base: {html.escape(base)}" if base else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )


def hero(brand: str, kicker: str, chips: list[str] | None = None) -> None:
    chips = chips or []
    chips_html = "".join(
        f'<span style="background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.28);'
        f'padding:3px 8px;font:700 11px UniNeueHeavy,Calibri,sans-serif;letter-spacing:.03em;'
        f'text-transform:uppercase;color:#fff;">{html.escape(c)}</span>'
        for c in chips
    )
    st.markdown(
        f"""
        <div style="background:linear-gradient(to right,#000444 0%,#1d357f 40%,#1d357f 60%,#000444 100%);
                    color:#fff;padding:16px 18px;margin:8px 0 12px 0;border-bottom:4px solid #0071bb;">
          <div style="font:800 24px UniNeueHeavy,Calibri,sans-serif;color:#fff;">{html.escape(brand)}</div>
          <div style="opacity:.95;font:400 14px UniNeueRegular,Calibri,sans-serif;margin:6px 0 10px 0;max-width:78ch;">{html.escape(kicker)}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">{chips_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def ses_footer() -> None:
    st.markdown(
        """
        <div style="margin-top:18px;padding:16px;
                    background:linear-gradient(to right,#000444 0%,#1d357f 40%,#1d357f 60%,#000444 100%);
                    color:#fff;font:400 13px UniNeueRegular,Calibri,sans-serif;line-height:1.45;">
          <div style="display:flex;flex-wrap:wrap;gap:10px 22px;justify-content:space-between;">
            <div>
              <strong style="font-family:UniNeueHeavy,Calibri,sans-serif;">SES-MT — Secretaria de Estado de Saúde de Mato Grosso</strong><br/>
              Palácio Paiaguás, Rua D, S/N, Bloco 5 — Centro Político Administrativo<br/>
              Cuiabá-MT · CEP 78049-902 · Tel. (65) 3613-5387
            </div>
            <div>
              <strong style="font-family:UniNeueHeavy,Calibri,sans-serif;">CIEVS / SIS Clima-Saúde</strong><br/>
              Uso interno da sala de situação · validar antes de comunicação oficial<br/>
              <a href="https://www.saude.mt.gov.br/ouvidoria" target="_blank" rel="noopener" style="color:#fff;">Ouvidoria</a>
              · Contato: notifica@ses.mt.gov.br
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def level_banner(nivel: str, municipio: str, motivo: str, orientacao: str = "") -> None:
    color = LEVEL_COLOR_MAP.get(str(nivel).lower(), "#334155")
    guide = level_plain(nivel)
    extra = f"<p style='margin:.28rem 0 0;color:#fff;'><b>Em linguagem simples:</b> {html.escape(guide['o_que_fazer'])}</p>"
    if orientacao:
        extra += f"<p style='margin:.28rem 0 0;color:#fff;'>{html.escape(orientacao)}</p>"
    st.markdown(
        f"""
        <div style="background:{color};color:#fff;padding:14px 16px;margin:6px 0 12px 0;
                    border-left:8px solid rgba(255,255,255,.45);">
          <h3 style="margin:0;font:800 18px UniNeueHeavy,Calibri,sans-serif;color:#fff !important;">
            Nível operacional estadual · {html.escape(str(nivel).upper())}
          </h3>
          <p style="margin:.28rem 0 0;color:#fff;"><b>Município mais crítico:</b> {html.escape(str(municipio))}</p>
          <p style="margin:.28rem 0 0;color:#fff;">{html.escape(str(motivo))}</p>
          {extra}
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div style="font:800 19px UniNeueHeavy,Calibri,sans-serif;color:#1351B4;border-bottom:2px solid #dbe8fb;'
        f'padding-bottom:6px;margin:8px 0 4px 0;">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f'<div style="color:#57595A;font:400 14px UniNeueRegular,Calibri,sans-serif;margin:0 0 10px 0;">{html.escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )


def callout(text: str, kind: str = "info") -> None:
    styles = {
        "info": ("#dbe8fb", "#a9c7ef", "#093089"),
        "warn": ("#fff7ed", "#fdba74", "#7c2d12"),
        "tip": ("#edf3fc", "#b7cef0", "#1d357f"),
    }
    bg, border, color = styles.get(kind, styles["info"])
    st.markdown(
        f'<div style="background:{bg};border:1px solid {border};color:{color};padding:12px 14px;margin:8px 0 12px 0;">'
        f"{html.escape(text)}</div>",
        unsafe_allow_html=True,
    )


def section_guide(secao: str) -> None:
    g = section_plain(secao)
    if not g:
        return
    st.markdown(
        '<div style="background:#fff;border:1px solid #e7e7e7;border-left:5px solid #1351B4;padding:12px 14px;margin:6px 0 12px 0;">'
        '<h4 style="margin:0 0 6px 0;color:#1351B4;font:800 15px UniNeueHeavy,Calibri,sans-serif;">Como ler esta seção</h4>'
        f"<p style='margin:4px 0;color:#333;'><span style='font-weight:700;color:#1351B4;'>Para que serve:</span> {html.escape(g['para_que_serve'])}</p>"
        f"<p style='margin:4px 0;color:#333;'><span style='font-weight:700;color:#1351B4;'>Como usar:</span> {html.escape(g['como_usar'])}</p>"
        f"<p style='margin:4px 0;color:#333;'><span style='font-weight:700;color:#1351B4;'>Cuidado:</span> {html.escape(g['cuidado'])}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def insight_cards(items: list[tuple[str, str, str]]) -> None:
    cards = []
    for label, value, hint in items:
        cards.append(
            '<div style="background:#fff;border:1px solid #e7e7e7;border-top:3px solid #1351B4;padding:10px 12px;">'
            f'<div style="font:700 11px UniNeueHeavy,Calibri,sans-serif;color:#57595A;text-transform:uppercase;letter-spacing:.04em;">{html.escape(label)}</div>'
            f'<div style="font:800 22px UniNeueHeavy,Calibri,sans-serif;color:#1351B4;margin-top:3px;">{html.escape(str(value))}</div>'
            f'<div style="font:400 12px UniNeueRegular,Calibri,sans-serif;color:#57595A;margin-top:3px;">{html.escape(hint)}</div>'
            "</div>"
        )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin:6px 0 12px 0;">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def level_legend() -> None:
    cards = []
    for key, color in LEVEL_COLOR_MAP.items():
        if key == "cinza":
            continue
        g = level_plain(key)
        cards.append(
            f'<div style="background:{color};color:#fff;padding:10px 12px;min-height:74px;">'
            f"<strong style='font:800 14px UniNeueHeavy,Calibri,sans-serif;'>{html.escape(g['titulo'])}</strong>"
            f"<div style='font:400 12px UniNeueRegular,Calibri,sans-serif;opacity:.95;margin-top:4px;'>{html.escape(g['o_que_fazer'])}</div>"
            "</div>"
        )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin:6px 0 12px 0;">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def glossary_expander(keys: list[str] | None = None) -> None:
    keys = keys or list(INDICATOR_GLOSSARY.keys())
    with st.expander("O que significam estes indicadores? (linguagem simples)", expanded=False):
        for k in keys:
            meta = INDICATOR_GLOSSARY.get(k)
            if not meta:
                continue
            st.markdown(
                f"**{meta['nome']}**  \n"
                f"{meta['leigo']}  \n"
                f"*Como ler:* {meta['como_ler']}"
            )
