# -*- coding: utf-8 -*-
"""Tema visual do painel SIS Clima-Saúde MT."""
from __future__ import annotations

import html
import streamlit as st

from sisclima.ui.explainers import INDICATOR_GLOSSARY, level_plain, section_plain

LEVEL_COLOR_MAP = {
    "cinza": "#6b7280",
    "verde": "#16803c",
    "amarela": "#c49200",
    "laranja": "#d97706",
    "vermelha": "#dc2626",
    "roxa": "#6d28d9",
}

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=Source+Sans+3:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
}

[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(900px 380px at 8% -5%, rgba(15,110,86,0.07), transparent 60%),
    radial-gradient(700px 320px at 95% 8%, rgba(180,83,9,0.05), transparent 55%),
    linear-gradient(180deg, #eef4f1 0%, #f3f6f4 40%, #f7f9f8 100%);
}

.block-container {
  padding-top: 1.0rem !important;
  padding-bottom: 2.8rem !important;
  max-width: 1320px !important;
}

[data-testid="stSidebar"],
section[data-testid="stSidebar"],
[data-testid="stSidebarNav"],
[data-testid="stSidebarNavItems"],
[data-testid="stSidebarContent"],
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarUserContent"],
div[data-testid="collapsedControl"],
button[kind="headerNoPadding"],
[data-testid="stBaseButton-headerNoPadding"] {
  display: none !important;
  width: 0 !important;
  min-width: 0 !important;
  max-width: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
  opacity: 0 !important;
}
section.main > div,
[data-testid="stAppViewContainer"] > .main,
.stApp [data-testid="stMain"] {
  padding-left: 1rem !important;
  margin-left: 0 !important;
}
header[data-testid="stHeader"] {
  background: transparent;
}

.sis-hero {
  background:
    radial-gradient(1000px 380px at 8% -20%, rgba(255,255,255,0.16), transparent 50%),
    radial-gradient(800px 300px at 90% 120%, rgba(11,61,52,0.35), transparent 55%),
    linear-gradient(128deg, #08352e 0%, #0f6e56 46%, #1a8a6e 100%);
  color: #f4faf7;
  border-radius: 24px;
  padding: 1.45rem 1.6rem 1.25rem 1.6rem;
  margin-bottom: 1rem;
  box-shadow: 0 20px 44px rgba(11, 61, 52, 0.20);
  position: relative;
  overflow: hidden;
}

.sis-hero::after {
  content: "";
  position: absolute;
  inset: auto -40px -60px auto;
  width: 220px;
  height: 220px;
  border-radius: 50%;
  background: rgba(255,255,255,0.06);
  pointer-events: none;
}

.sis-brand {
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.85rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 0;
  line-height: 1.12;
}

.sis-kicker {
  opacity: 0.9;
  font-size: 0.98rem;
  margin: 0.4rem 0 0.9rem 0;
  max-width: 62ch;
}

.sis-level-banner {
  border-radius: 18px;
  padding: 1.05rem 1.2rem;
  color: white;
  margin: 0.45rem 0 0.85rem 0;
  box-shadow: 0 10px 28px rgba(0,0,0,0.12);
}

.sis-level-banner h3 {
  margin: 0;
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.28rem;
}

.sis-level-banner p {
  margin: 0.35rem 0 0 0;
  opacity: 0.96;
  font-size: 0.95rem;
}

.sis-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  margin-top: 0.7rem;
}

.sis-chip {
  background: rgba(255,255,255,0.14);
  border: 1px solid rgba(255,255,255,0.22);
  border-radius: 999px;
  padding: 0.28rem 0.72rem;
  font-size: 0.76rem;
  font-weight: 600;
}

.sis-section-title {
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.4rem;
  margin: 0.25rem 0 0.4rem 0;
  color: #12352d;
}

.sis-muted {
  color: #5b6f68;
  font-size: 0.94rem;
  margin-bottom: 0.85rem;
  max-width: 78ch;
}

.sis-card {
  background: #ffffff;
  border: 1px solid #d5e3dc;
  border-radius: 16px;
  padding: 0.9rem 1rem;
  margin-bottom: 0.75rem;
  box-shadow: 0 4px 14px rgba(18, 53, 45, 0.04);
}

.sis-guide {
  background: linear-gradient(180deg, #ffffff 0%, #f4faf7 100%);
  border: 1px solid #cfe0d8;
  border-left: 5px solid #0f6e56;
  border-radius: 14px;
  padding: 0.9rem 1.05rem;
  margin: 0.35rem 0 1rem 0;
}

.sis-guide h4 {
  margin: 0 0 0.4rem 0;
  font-family: "Fraunces", Georgia, serif;
  color: #0b3d34;
  font-size: 1.05rem;
}

.sis-guide p {
  margin: 0.25rem 0;
  color: #334740;
  font-size: 0.92rem;
  line-height: 1.45;
}

.sis-guide .lbl {
  font-weight: 700;
  color: #0f6e56;
}

.sis-callout {
  border-radius: 14px;
  padding: 0.85rem 1rem;
  margin: 0.5rem 0 0.9rem 0;
  border: 1px solid transparent;
}

.sis-callout.info {
  background: #e8f5f0;
  border-color: #b7dccf;
  color: #12352d;
}
.sis-callout.warn {
  background: #fff7ed;
  border-color: #fdba74;
  color: #7c2d12;
}
.sis-callout.tip {
  background: #eff6ff;
  border-color: #93c5fd;
  color: #1e3a5f;
}

.sis-insight-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.65rem;
  margin: 0.4rem 0 1rem 0;
}

.sis-insight {
  background: #fff;
  border: 1px solid #d5e3dc;
  border-radius: 14px;
  padding: 0.75rem 0.85rem;
  box-shadow: 0 3px 10px rgba(18,53,45,0.04);
}

.sis-insight .k {
  font-size: 0.75rem;
  font-weight: 600;
  color: #5b6f68;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.sis-insight .v {
  font-family: "Fraunces", Georgia, serif;
  font-size: 1.45rem;
  font-weight: 700;
  color: #0b3d34;
  line-height: 1.2;
  margin-top: 0.2rem;
}

.sis-insight .h {
  font-size: 0.8rem;
  color: #5b6f68;
  margin-top: 0.25rem;
}

.sis-level-tile {
  color: white;
  border-radius: 14px;
  padding: 0.9rem 0.6rem;
  text-align: center;
  box-shadow: 0 6px 16px rgba(0,0,0,0.10);
}

.sis-level-tile .lbl {
  font-size: 0.78rem;
  font-weight: 600;
  opacity: 0.92;
}

.sis-level-tile .val {
  font-size: 1.7rem;
  font-weight: 800;
  line-height: 1.2;
}

.sis-level-legend {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.55rem;
  margin: 0.5rem 0 1rem 0;
}

.sis-level-card {
  border-radius: 12px;
  padding: 0.7rem 0.8rem;
  color: #fff;
  min-height: 92px;
}

.sis-level-card strong {
  display: block;
  font-size: 0.92rem;
  margin-bottom: 0.25rem;
}

.sis-level-card span {
  font-size: 0.8rem;
  opacity: 0.95;
  line-height: 1.35;
}

div[data-testid="stMetric"] {
  background: #ffffff;
  border: 1px solid #d5e3dc;
  border-radius: 14px;
  padding: 0.6rem 0.8rem;
  box-shadow: 0 3px 10px rgba(18,53,45,0.03);
}

div[role="radiogroup"] {
  gap: 0.4rem !important;
  flex-wrap: wrap !important;
}
div[role="radiogroup"] label {
  background: #ffffff !important;
  border: 1px solid #c9dbd3 !important;
  border-radius: 999px !important;
  padding: 0.38rem 0.9rem !important;
  margin: 0.1rem !important;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.12s ease;
}
div[role="radiogroup"] label:hover {
  transform: translateY(-1px);
  border-color: #0f6e56 !important;
}
div[role="radiogroup"] label:has(input:checked) {
  background: #0f6e56 !important;
  border-color: #0f6e56 !important;
  color: #ffffff !important;
}
div[role="radiogroup"] label:has(input:checked) p,
div[role="radiogroup"] label:has(input:checked) span {
  color: #ffffff !important;
}

div[data-testid="stExpander"] {
  background: #ffffff;
  border: 1px solid #d5e3dc;
  border-radius: 14px;
}

.guide-card {
  background: linear-gradient(180deg, #f7fbf9 0%, #ffffff 100%);
  border: 1px solid #cfe0d8;
  border-left: 5px solid #0f6e56;
  border-radius: 14px;
  padding: 0.95rem 1.1rem;
  margin: 0.35rem 0 0.9rem 0;
  color: #1f2937;
  line-height: 1.45;
  font-size: 0.95rem;
}

.ai-box {
  background: #0b3d34;
  color: #e8f5f0;
  border-radius: 14px;
  padding: 1rem 1.15rem;
  margin: 0.4rem 0 0.8rem 0;
  line-height: 1.5;
  font-size: 0.95rem;
  box-shadow: 0 12px 28px rgba(11, 61, 52, 0.18);
}
"""


def _render_html(fragment: str) -> None:
    """Renderiza HTML sem cair em bloco de código do Markdown (indentação)."""
    compact = " ".join(line.strip() for line in fragment.splitlines() if line.strip())
    if hasattr(st, "html"):
        st.html(compact)
    else:
        st.markdown(compact, unsafe_allow_html=True)


def apply_theme() -> None:
    _render_html(f"<style>{CSS}</style>")


def hero(brand: str, kicker: str, chips: list[str] | None = None) -> None:
    chips = chips or []
    chips_html = "".join(f'<span class="sis-chip">{html.escape(c)}</span>' for c in chips)
    _render_html(
        f'<div class="sis-hero">'
        f'<p class="sis-brand">{html.escape(brand)}</p>'
        f'<p class="sis-kicker">{html.escape(kicker)}</p>'
        f'<div class="sis-chip-row">{chips_html}</div>'
        f"</div>"
    )


def level_banner(nivel: str, municipio: str, motivo: str, orientacao: str = "") -> None:
    color = LEVEL_COLOR_MAP.get(str(nivel).lower(), "#334155")
    guide = level_plain(nivel)
    extra = f"<p><b>Em linguagem simples:</b> {html.escape(guide['o_que_fazer'])}</p>"
    if orientacao:
        extra += f"<p>{html.escape(orientacao)}</p>"
    _render_html(
        f'<div class="sis-level-banner" style="background:{color}">'
        f"<h3>Nível operacional estadual · {html.escape(str(nivel).upper())}</h3>"
        f"<p><b>Município mais crítico:</b> {html.escape(str(municipio))}</p>"
        f"<p>{html.escape(str(motivo))}</p>"
        f"{extra}"
        f"</div>"
    )


def section_title(title: str, subtitle: str = "") -> None:
    _render_html(f'<div class="sis-section-title">{html.escape(title)}</div>')
    if subtitle:
        _render_html(f'<div class="sis-muted">{html.escape(subtitle)}</div>')


def callout(text: str, kind: str = "info") -> None:
    kind = kind if kind in {"info", "warn", "tip"} else "info"
    _render_html(f'<div class="sis-callout {kind}">{html.escape(text)}</div>')


def section_guide(secao: str) -> None:
    g = section_plain(secao)
    if not g:
        return
    _render_html(
        '<div class="sis-guide">'
        "<h4>Como ler esta seção</h4>"
        f"<p><span class=\"lbl\">Para que serve:</span> {html.escape(g['para_que_serve'])}</p>"
        f"<p><span class=\"lbl\">Como usar:</span> {html.escape(g['como_usar'])}</p>"
        f"<p><span class=\"lbl\">Cuidado:</span> {html.escape(g['cuidado'])}</p>"
        "</div>"
    )


def insight_cards(items: list[tuple[str, str, str]]) -> None:
    """items: (label, value, hint)"""
    cards = []
    for label, value, hint in items:
        cards.append(
            '<div class="sis-insight">'
            f'<div class="k">{html.escape(label)}</div>'
            f'<div class="v">{html.escape(str(value))}</div>'
            f'<div class="h">{html.escape(hint)}</div>'
            "</div>"
        )
    _render_html(f'<div class="sis-insight-grid">{"".join(cards)}</div>')


def level_legend() -> None:
    cards = []
    for key, color in LEVEL_COLOR_MAP.items():
        if key == "cinza":
            continue
        g = level_plain(key)
        cards.append(
            f'<div class="sis-level-card" style="background:{color}">'
            f"<strong>{html.escape(g['titulo'])}</strong>"
            f"<span>{html.escape(g['o_que_fazer'])}</span>"
            "</div>"
        )
    _render_html(f'<div class="sis-level-legend">{"".join(cards)}</div>')


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
