# -*- coding: utf-8 -*-
"""Tema visual alinhado ao portal oficial SES-MT (saude.mt.gov.br).

Tokens de css/style.css do portal:
- topo/footer: linear-gradient(#000444 → #1d357f)
- faixa navbar: #0071bb
- títulos/links: #1351b4
- tipografia: UniNeue / Calibri (fallback institucional)
"""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import streamlit as st

from sisclima.branding import (
    ARARAS_LOGO_PATH,
    CIEVS_MT_LOGO_PATH,
    GOV_SES_LOCKUP_PATH,
    GOV_SES_LOGO_PATH,
    REDE_CIEVS_LOGO_PATH,
    SYSTEM_EXPANSION,
    SYSTEM_NAME,
    SYSTEM_TAGLINE,
    VIGIDESASTRES_LOGO_PATH,
)
from sisclima.ui.explainers import INDICATOR_GLOSSARY, level_plain, section_plain

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"
LOGO_PATH = GOV_SES_LOGO_PATH
CSS_PATH = ASSETS / "ses-panel.css"
FONT_REG = ASSETS / "fonts" / "uni-neue-regular.otf"
FONT_HEAVY = ASSETS / "fonts" / "uni-neue-heavy.otf"

SES_BLUE = "#1351B4"
SES_BLUE_DEEP = "#1D357F"
SES_BLUE_NAVY = "#000444"
SES_BLUE_ACCENT = "#0071BB"
SES_BG = "#F4F7FB"

LEVEL_COLOR_MAP = {
    "cinza": "#6b7280",
    "verde": "#16803c",
    "amarela": "#e6b800",
    "laranja": "#d97706",
    "vermelha": "#dc2626",
    "roxa": "#5b21b6",
}

LAYOUT_VERSION = "ARARAS MT layout institucional 2026-08-11"


def _strip_font_faces(css: str) -> str:
    cleaned = []
    skip = False
    for line in css.splitlines():
        if "@font-face" in line:
            skip = True
        if skip:
            if "}" in line:
                skip = False
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _critical_css() -> str:
    """CSS mínimo INLINE — garante azul SES mesmo se o arquivo/fonte falhar."""
    return f"""
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main, section.main {{
  background: {SES_BG} !important;
  background-color: {SES_BG} !important;
}}
[data-testid="stHeader"], [data-testid="stToolbar"] {{
  background: transparent !important;
}}
.block-container {{
  padding-top: 0.15rem !important;
  max-width: 1280px !important;
}}
h1, h2, h3, h4, h5, h6 {{
  color: {SES_BLUE} !important;
  font-family: Calibri, "Segoe UI", Tahoma, sans-serif !important;
}}
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"] {{
  display: none !important;
}}
section[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, #000444 0%, #1d357f 58%, #1351b4 100%) !important;
  border-right: 4px solid #0071bb !important;
  min-width: 272px !important;
}}
section[data-testid="stSidebar"] > div:first-child {{
  padding: 12px 14px 28px 14px !important;
}}
.sis-nav-kicker {{
  font: 800 12px Calibri, sans-serif !important;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: #ffffff !important;
  margin: 2px 0 4px 0;
}}
.sis-nav-group {{
  font: 800 11px Calibri, sans-serif !important;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: rgba(255,255,255,.72) !important;
  margin: 16px 2px 6px 2px;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label {{
  background: rgba(255,255,255,.12) !important;
  border: 1px solid rgba(255,255,255,.28) !important;
  border-left: 3px solid transparent !important;
  border-radius: 6px !important;
  padding: 10px 12px !important;
  margin: 4px 0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label span:not([data-testid="stIconMaterial"]) {{
  color: #ffffff !important;
  font: 700 14px Calibri, "Segoe UI", sans-serif !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
  background: rgba(255,255,255,.22) !important;
  border-left-color: #7ec8f0 !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{
  background: #0071bb !important;
  border-color: #ffffff !important;
  border-left-color: #ffffff !important;
}}
section[data-testid="stSidebar"] [data-testid="stRadio"] input {{
  appearance: none !important;
  width: 0 !important;
  height: 0 !important;
  margin: 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button {{
  background: rgba(255,255,255,.12) !important;
  color: #ffffff !important;
  border: 1px solid rgba(255,255,255,.28) !important;
  border-left: 3px solid transparent !important;
  border-radius: 6px !important;
  font: 700 14px Calibri, "Segoe UI", sans-serif !important;
  justify-content: flex-start !important;
  text-align: left !important;
  padding: 10px 12px !important;
  margin: 3px 0 !important;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
  background: rgba(255,255,255,.22) !important;
  border-left-color: #7ec8f0 !important;
  color: #ffffff !important;
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
  background: #0071bb !important;
  border-color: #ffffff !important;
  border-left: 3px solid #ffffff !important;
  color: #ffffff !important;
}}
[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"],
[data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
[data-testid="collapsedControl"] [data-testid="stIconMaterial"] {{
  font-size: 0 !important;
  line-height: 0 !important;
  width: 0 !important;
  height: 0 !important;
  overflow: hidden !important;
  color: transparent !important;
}}
"""


def apply_theme() -> None:
    """Injeta tema SES em camadas (crítico → arquivo → selo). Sem base64 gigante."""
    # 1) Crítico primeiro (nunca depende de arquivo/fonte)
    st.markdown(f"<style>{_critical_css()}</style>", unsafe_allow_html=True)

    # 2) CSS completo do arquivo (sem @font-face relativos)
    if CSS_PATH.exists():
        body_css = _strip_font_faces(CSS_PATH.read_text(encoding="utf-8"))
        st.markdown(f"<style>{body_css}</style>", unsafe_allow_html=True)

    # 3) Tipografia + contraste (depois do CSS arquivo para vencer h1–h6 azul em fundos escuros)
    st.markdown(
        "<style>"
        "html,body,.stApp{"
        "font-family:Calibri,\"Segoe UI\",Tahoma,Geneva,Verdana,sans-serif!important}"
        "h1,h2,h3,h4,h5,h6,.sis-section-title,.ses-masthead-brand,.sis-insight .v{"
        f"font-family:Calibri,\"Segoe UI\",sans-serif!important;color:{SES_BLUE}!important}}"
        ".sis-hero,.sis-hero *,.sis-hero h1,.sis-hero h2,.sis-hero h3,"
        ".sis-hero .sis-brand,.sis-brand,"
        ".ses-topbar,.ses-topbar *,.ses-footer,.ses-footer *,"
        ".sis-level-banner,.sis-level-banner *,"
        ".sis-level-tile,.sis-level-tile *,"
        ".sis-level-card,.sis-level-card *{color:#fff!important}"
        ".sis-level-banner-amarela,.sis-level-banner-amarela *,"
        ".sis-level-banner-cinza,.sis-level-banner-cinza *,"
        ".sis-level-tile-amarela,.sis-level-tile-amarela *,"
        ".sis-level-tile-cinza,.sis-level-tile-cinza *,"
        ".sis-level-card-amarela,.sis-level-card-amarela *,"
        ".sis-level-card-cinza,.sis-level-card-cinza *{color:#1a1a1a!important}"
        ".sis-level-banner-title{font:800 18px Calibri,Segoe UI,sans-serif!important;"
        "margin:0!important}"
        ".sis-level-banner:not(.sis-level-banner-amarela):not(.sis-level-banner-cinza) "
        ".sis-level-banner-title{color:#fff!important}"
        ".sis-level-banner-amarela .sis-level-banner-title,"
        ".sis-level-banner-cinza .sis-level-banner-title{color:#1a1a1a!important}"
        "h3[id*=\"nivel-operacional\"],h3[id*=\"nivel-operacional\"] span,"
        "h3[id*=\"nivel-operacional\"] a{color:#fff!important}"
        ".stAlertContainer,[data-testid=\"stAlertContainer\"]{"
        "background:#DBE8FB!important;background-color:#DBE8FB!important;"
        "color:#093089!important;border-radius:0!important;"
        "border:1px solid #A9C7EF!important;border-left:5px solid #1351B4!important}"
        ".stAlertContainer *,[data-testid=\"stAlertContainer\"] *{color:#093089!important}"
        "div[data-testid=\"stAlert\"]:has([data-testid=\"stAlertContentWarning\"]) "
        "[data-testid=\"stAlertContainer\"]{background:#FFF7ED!important;"
        "border-color:#FDBA74!important;border-left-color:#D97706!important}"
        "[data-testid=\"stAlertContentWarning\"],[data-testid=\"stAlertContentWarning\"] *{"
        "color:#7c2d12!important}"
        "div[data-testid=\"stAlert\"]:has([data-testid=\"stAlertContentError\"]) "
        "[data-testid=\"stAlertContainer\"]{background:#FEF2F2!important;"
        "border-color:#FECACA!important;border-left-color:#DC2626!important}"
        "[data-testid=\"stAlertContentError\"],[data-testid=\"stAlertContentError\"] *{"
        "color:#7f1d1d!important}"
        "div[data-testid=\"stAlert\"]:has([data-testid=\"stAlertContentSuccess\"]) "
        "[data-testid=\"stAlertContainer\"]{background:#ECFDF5!important;"
        "border-color:#A7F3D0!important;border-left-color:#16803C!important}"
        "[data-testid=\"stAlertContentSuccess\"],[data-testid=\"stAlertContentSuccess\"] *{"
        "color:#14532d!important}"
        ".sis-callout.info,.sis-callout.info *{color:#093089!important}"
        ".sis-callout.warn,.sis-callout.warn *{color:#7c2d12!important}"
        ".sis-callout.tip,.sis-callout.tip *{color:#1d357f!important}"
        "</style>",
        unsafe_allow_html=True,
    )

    # 4) Selo discreto (sem faixa azul dominante / canário de versão)
    st.markdown(
        f'<div style="color:{SES_BLUE_DEEP};font:600 11px Calibri,Segoe UI,sans-serif;'
        f'margin:0 0 6px 0;opacity:.85;">ARARAS MT · SES-MT · CIEVS-MT · Rede CIEVS · Vigidesastres</div>',
        unsafe_allow_html=True,
    )


def ses_masthead(
    *,
    sistema: str = SYSTEM_NAME,
    subtitulo: str = SYSTEM_TAGLINE,
    base: str = "",
) -> None:
    """Chrome institucional no padrão do portal saude.mt.gov.br (estilos INLINE)."""
    hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(
        f"""
        <div style="background:linear-gradient(to right,#000444 0%,#1d357f 40%,#1d357f 60%,#000444 100%);
                    color:#fff;padding:10px 14px;display:flex;flex-wrap:wrap;gap:8px 16px;
                    justify-content:space-between;align-items:center;
                    font:400 13px Calibri,Segoe UI,sans-serif;">
          <div><strong style="font-family:Calibri,Segoe UI,sans-serif;font-weight:800;">Governo de Mato Grosso</strong>
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

    c_logo, c_title, c_meta = st.columns([1.05, 3.55, 1.55], vertical_alignment="center")
    with c_logo:
        _ses = GOV_SES_LOCKUP_PATH if GOV_SES_LOCKUP_PATH.exists() else GOV_SES_LOGO_PATH
        if _ses.exists():
            st.image(str(_ses), width=168)
        else:
            st.markdown("**SES-MT**")
    with c_title:
        if ARARAS_LOGO_PATH.exists():
            st.image(str(ARARAS_LOGO_PATH), use_container_width=True)
        st.markdown(
            f'<div style="color:#57595A;font:400 13px Calibri,Segoe UI,sans-serif;margin-top:-8px;">'
            f'{html.escape(SYSTEM_EXPANSION)}</div>'
            f'<span style="display:inline-block;margin-top:6px;background:{SES_BLUE_ACCENT};color:#fff;padding:3px 8px;'
            f'font:700 11px Calibri,Segoe UI,sans-serif;letter-spacing:.04em;text-transform:uppercase;">'
            f'Sala de situação</span>',
            unsafe_allow_html=True,
        )
    with c_meta:
        if CIEVS_MT_LOGO_PATH.exists():
            st.image(str(CIEVS_MT_LOGO_PATH), width=148)
        else:
            st.markdown(
                f'<div style="text-align:center;color:{SES_BLUE};font:800 14px Calibri,Segoe UI,sans-serif;">CIEVS-MT</div>',
                unsafe_allow_html=True,
            )
        if REDE_CIEVS_LOGO_PATH.exists():
            st.image(str(REDE_CIEVS_LOGO_PATH), width=132)
        if VIGIDESASTRES_LOGO_PATH.exists():
            st.image(str(VIGIDESASTRES_LOGO_PATH), width=48)
        if base:
            st.markdown(
                f"<div style='text-align:center;margin-top:2px'><span style='display:inline-block;background:#EDF3FC;"
                f"color:{SES_BLUE_DEEP};border:1px solid #B7CEF0;padding:2px 8px;font:700 11px Calibri,sans-serif;'>"
                f"Base {html.escape(base)}</span></div>",
                unsafe_allow_html=True,
            )


def hero(brand: str, kicker: str, chips: list[str] | None = None) -> None:
    chips = chips or []
    chips_html = "".join(
        f'<span style="background:rgba(255,255,255,.14);border:1px solid rgba(255,255,255,.32);'
        f'padding:3px 8px;font:700 11px Calibri,Segoe UI,sans-serif;letter-spacing:.03em;'
        f'text-transform:uppercase;color:#fff;">{html.escape(c)}</span>'
        for c in chips
    )
    st.markdown(
        f"""
        <div style="background:linear-gradient(115deg,#000444 0%,#1d357f 45%,#1351b4 78%,#0071bb 100%);
                    color:#fff;padding:16px 18px;margin:8px 0 12px 0;border-bottom:4px solid {SES_BLUE_ACCENT};">
          <div style="font:800 24px Calibri,Segoe UI,sans-serif;color:#fff;line-height:1.15;">{html.escape(brand)}</div>
          <div style="opacity:.96;font:400 14px Calibri,Segoe UI,sans-serif;margin:6px 0 10px 0;max-width:78ch;">{html.escape(kicker)}</div>
          <div style="display:flex;flex-wrap:wrap;gap:6px;">{chips_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_strip(items: list[tuple[str, str]], note: str = "") -> None:
    pills = "".join(
        f"<span style='display:inline-flex;align-items:center;gap:4px;background:#EDF3FC;color:{SES_BLUE_DEEP};"
        f"border:1px solid #B7CEF0;padding:3px 8px;font:700 11px Calibri,sans-serif;"
        f"letter-spacing:.03em;text-transform:uppercase;'>"
        f"<strong style='color:{SES_BLUE};'>{html.escape(k)}</strong>&nbsp;{html.escape(v)}</span>"
        for k, v in items
        if v not in (None, "", "—")
    )
    note_html = f"<span style='color:#57595A;font:400 13px Calibri,sans-serif;'>{html.escape(note)}</span>" if note else ""
    st.markdown(
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#fff;"
        f"border:1px solid #E2E8F0;border-left:4px solid {SES_BLUE_ACCENT};padding:8px 12px;margin:4px 0 10px 0;'>"
        f"{pills}{note_html}</div>",
        unsafe_allow_html=True,
    )


def panel_open(title: str = "", *, soft: bool = False) -> None:
    border = SES_BLUE_ACCENT if soft else SES_BLUE
    bg = "#FBFDFF" if soft else "#fff"
    title_html = (
        f"<div style='font:800 12px Calibri,sans-serif;letter-spacing:.05em;text-transform:uppercase;"
        f"color:#57595A;margin:0 0 8px 0;'>{html.escape(title)}</div>"
        if title
        else ""
    )
    st.markdown(
        f"<div style='background:{bg};border:1px solid #E2E8F0;border-top:3px solid {border};"
        f"padding:12px 14px;margin:6px 0 12px 0;'>{title_html}",
        unsafe_allow_html=True,
    )


def panel_close() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def ses_footer() -> None:
    st.markdown(
        f"""
        <div style="margin-top:18px;padding:16px;
                    background:linear-gradient(to right,#000444 0%,#1d357f 40%,#1d357f 60%,#000444 100%);
                    color:#fff;font:400 13px Calibri,Segoe UI,sans-serif;line-height:1.45;">
          <div style="display:flex;flex-wrap:wrap;gap:10px 22px;justify-content:space-between;">
            <div>
              <strong style="font-weight:800;">SES-MT — Secretaria de Estado de Saúde de Mato Grosso</strong><br/>
              Palácio Paiaguás, Rua D, S/N, Bloco 5 — Centro Político Administrativo<br/>
              Cuiabá-MT · CEP 78049-902 · Tel. (65) 3613-5387
            </div>
            <div>
              <strong style="font-weight:800;">CIEVS-MT / ARARAS MT</strong><br/>
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
    """Faixa do nível operacional — texto escuro em amarela; branco nos demais.

    Usa st.html (não markdown) para o Streamlit não promover o título a h3 azul SES.
    """
    niv = str(nivel).lower()
    color = LEVEL_COLOR_MAP.get(niv, "#334155")
    fg = "#1a1a1a" if niv in {"amarela", "cinza"} else "#ffffff"
    guide = level_plain(nivel)
    extra = (
        f"<p style='margin:.28rem 0 0;color:{fg} !important;'><b>Em linguagem simples:</b> "
        f"{html.escape(guide['o_que_fazer'])}</p>"
    )
    if orientacao:
        extra += (
            f"<p style='margin:.28rem 0 0;color:{fg} !important;'>"
            f"{html.escape(orientacao)}</p>"
        )
    markup = (
        f"<div class='sis-level-banner-wrap' style='background:{SES_BG};padding:0 0 10px 0;margin:0;'>"
        f"<div class='sis-level-banner sis-level-banner-{html.escape(niv)}' "
        f"style='background:{color};color:{fg} !important;padding:14px 16px;"
        f"border-left:8px solid {SES_BLUE};border-right:8px solid {SES_BLUE_ACCENT};"
        f"box-shadow:inset 0 0 0 1px rgba(0,4,68,.15);'>"
        f"<div class='sis-level-banner-title' style='margin:0;font:800 18px Calibri,Segoe UI,sans-serif;"
        f"color:{fg} !important;line-height:1.25;'>"
        f"Nível operacional estadual · {html.escape(str(nivel).upper())}"
        f"</div>"
        f"<p style='margin:.28rem 0 0;color:{fg} !important;'>"
        f"<b>Município mais crítico:</b> {html.escape(str(municipio))}</p>"
        f"<p style='margin:.28rem 0 0;color:{fg} !important;'>{html.escape(str(motivo))}</p>"
        f"{extra}"
        f"</div></div>"
    )
    # st.html evita o markdown promover o título a <h3> com cor azul institucional
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def section_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div style="font:800 19px Calibri,Segoe UI,sans-serif;color:{SES_BLUE};border-bottom:2px solid #dbe8fb;'
        f'padding-bottom:6px;margin:8px 0 4px 0;">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(
            f'<div style="color:#57595A;font:400 14px Calibri,Segoe UI,sans-serif;margin:0 0 10px 0;">{html.escape(subtitle)}</div>',
            unsafe_allow_html=True,
        )


def callout(text: str, kind: str = "info") -> None:
    kind = kind if kind in {"info", "warn", "tip"} else "info"
    st.markdown(
        f'<div class="sis-callout {kind}">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def section_guide(secao: str) -> None:
    g = section_plain(secao)
    if not g:
        return
    st.markdown(
        f'<div style="background:#fff;border:1px solid #e7e7e7;border-left:5px solid {SES_BLUE};padding:12px 14px;margin:6px 0 12px 0;">'
        f'<h4 style="margin:0 0 6px 0;color:{SES_BLUE};font:800 15px Calibri,Segoe UI,sans-serif;">Como ler esta seção</h4>'
        f"<p style='margin:4px 0;color:#333;'><span style='font-weight:700;color:{SES_BLUE};'>Para que serve:</span> {html.escape(g['para_que_serve'])}</p>"
        f"<p style='margin:4px 0;color:#333;'><span style='font-weight:700;color:{SES_BLUE};'>Como usar:</span> {html.escape(g['como_usar'])}</p>"
        f"<p style='margin:4px 0;color:#333;'><span style='font-weight:700;color:{SES_BLUE};'>Cuidado:</span> {html.escape(g['cuidado'])}</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def insight_cards(items: list[tuple[str, str, str]]) -> None:
    cards = []
    for label, value, hint in items:
        cards.append(
            f'<div style="background:#fff;border:1px solid #e7e7e7;border-top:3px solid {SES_BLUE};padding:10px 12px;min-height:92px;">'
            f'<div style="font:700 11px Calibri,sans-serif;color:#57595A;text-transform:uppercase;letter-spacing:.04em;">{html.escape(label)}</div>'
            f'<div style="font:800 22px Calibri,sans-serif;color:{SES_BLUE};margin-top:3px;">{html.escape(str(value))}</div>'
            f'<div style="font:400 12px Calibri,sans-serif;color:#57595A;margin-top:3px;">{html.escape(hint)}</div>'
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
        fg = "#1a1a1a" if key in {"amarela", "cinza"} else "#ffffff"
        cards.append(
            f'<div class="sis-level-card sis-level-card-{html.escape(key)}" '
            f'style="background:{color};color:{fg};padding:10px 12px;min-height:74px;">'
            f"<strong style='font:800 14px Calibri,sans-serif;color:{fg} !important;'>"
            f"{html.escape(g['titulo'])}</strong>"
            f"<div style='font:400 12px Calibri,sans-serif;opacity:.95;margin-top:4px;"
            f"color:{fg} !important;'>{html.escape(g['o_que_fazer'])}</div>"
            "</div>"
        )
    st.markdown(
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin:6px 0 12px 0;">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def nav_label(text: str = "Navegação do painel") -> None:
    st.markdown(
        f'<div class="sis-nav-group">{html.escape(text)}</div>',
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
