# -*- coding: utf-8 -*-
"""Cabeçalho e rodapé institucionais SES-MT / CIEVS para PDFs ReportLab."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from sisclima.branding import (
    ARARAS_LOGO_PATH,
    CIEVS_MT_LOGO_PATH,
    DEVELOPER_CREDIT,
    GOV_SES_LOCKUP_PATH,
    GOV_SES_LOGO_PATH,
    SYSTEM_NAME,
    SYSTEM_TAGLINE,
)

SES_NAVY = colors.HexColor("#000444")
SES_BLUE = colors.HexColor("#1351B4")
SES_ACCENT = colors.HexColor("#0071BB")

PAGE_W, PAGE_H = A4
MARGIN_L = 2.0 * cm
MARGIN_R = 2.0 * cm
TOP_BAR_H = 0.55 * cm
ACCENT_BAR_H = 0.12 * cm
HEADER_BODY_H = 2.85 * cm
FOOTER_H = 1.35 * cm

HEADER_TOTAL = TOP_BAR_H + HEADER_BODY_H + ACCENT_BAR_H
CONTENT_TOP_MARGIN = HEADER_TOTAL + 0.55 * cm
CONTENT_BOTTOM_MARGIN = FOOTER_H + 0.30 * cm

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONTS_READY = False


def register_institutional_fonts() -> tuple[str, str]:
    """Registra Calibri (Windows) para cabeçalho/rodapé e conteúdo."""
    global _FONT, _FONT_BOLD, _FONTS_READY
    if _FONTS_READY:
        return _FONT, _FONT_BOLD
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    regular = fonts_dir / "calibri.ttf"
    bold = fonts_dir / "calibrib.ttf"
    if regular.exists():
        pdfmetrics.registerFont(TTFont("Calibri", str(regular)))
        _FONT = "Calibri"
    if bold.exists():
        pdfmetrics.registerFont(TTFont("Calibri-Bold", str(bold)))
        _FONT_BOLD = "Calibri-Bold"
    elif regular.exists():
        _FONT_BOLD = "Calibri"
    _FONTS_READY = True
    return _FONT, _FONT_BOLD


def _gov_logo() -> Path:
    # Preferir lockup oficial Governo/SES (alta resolução no projeto)
    if GOV_SES_LOCKUP_PATH.exists():
        return GOV_SES_LOCKUP_PATH
    if GOV_SES_LOGO_PATH.exists():
        return GOV_SES_LOGO_PATH
    return GOV_SES_LOCKUP_PATH


def _draw_image_fit(
    canvas: Canvas,
    path: Path,
    x: float,
    y: float,
    max_w: float,
    max_h: float,
    *,
    center: bool = True,
) -> None:
    if not path.exists():
        return
    img = ImageReader(str(path))
    iw, ih = img.getSize()
    if iw <= 0 or ih <= 0:
        return
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    dx = x + ((max_w - w) / 2.0 if center else 0)
    dy = y + ((max_h - h) / 2.0 if center else 0)
    canvas.drawImage(img, dx, dy, width=w, height=h, preserveAspectRatio=True, mask="auto")


def draw_institutional_page(
    canvas: Canvas,
    doc,
    *,
    doc_title: str = "",
) -> None:
    """Desenha faixa SES no topo e rodapé CIEVS em todas as páginas."""
    font, font_bold = register_institutional_fonts()
    canvas.saveState()

    # Faixa superior (padrão portal SES-MT)
    canvas.setFillColor(SES_NAVY)
    canvas.rect(0, PAGE_H - TOP_BAR_H, PAGE_W, TOP_BAR_H, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont(font_bold, 8.5)
    canvas.drawString(
        MARGIN_L,
        PAGE_H - 0.38 * cm,
        "Governo de Mato Grosso  |  Secretaria de Estado de Saúde  |  CIEVS",
    )
    canvas.setFont(font, 8.5)
    canvas.drawRightString(PAGE_W - MARGIN_R, PAGE_H - 0.38 * cm, "saude.mt.gov.br")

    # Cabeçalho com logos — SES/Gov legível, ARARAS levemente menor, CIEVS +~10%
    header_bottom = PAGE_H - TOP_BAR_H - HEADER_BODY_H
    canvas.setFillColor(colors.white)
    canvas.rect(0, header_bottom, PAGE_W, HEADER_BODY_H, fill=1, stroke=0)
    canvas.setFillColor(SES_ACCENT)
    canvas.rect(0, header_bottom - ACCENT_BAR_H, PAGE_W, ACCENT_BAR_H, fill=1, stroke=0)

    logo_max_h = HEADER_BODY_H - 0.36 * cm
    logo_y = header_bottom + (HEADER_BODY_H - logo_max_h) / 2.0
    gap = 0.18 * cm
    usable = PAGE_W - MARGIN_L - MARGIN_R
    # Pesos ópticos: Gov/SES maior, ARARAS reduzido, CIEVS ampliado (~8–12%)
    w_gov = usable * 0.38
    w_araras = usable * 0.28
    w_cievs = usable * 0.34
    used = w_gov + w_araras + w_cievs + 2 * gap
    if used > usable:
        scale = usable / used
        w_gov *= scale
        w_araras *= scale
        w_cievs *= scale
        gap *= scale
    elif used < usable:
        extra = (usable - used) / 3.0
        w_gov += extra
        w_araras += extra
        w_cievs += extra

    x0 = MARGIN_L
    _draw_image_fit(canvas, _gov_logo(), x0, logo_y, w_gov, logo_max_h)
    _draw_image_fit(canvas, ARARAS_LOGO_PATH, x0 + w_gov + gap, logo_y, w_araras, logo_max_h)
    _draw_image_fit(
        canvas,
        CIEVS_MT_LOGO_PATH,
        x0 + w_gov + gap + w_araras + gap,
        logo_y,
        w_cievs,
        logo_max_h,
    )

    # Rodapé institucional — Calibri
    canvas.setFillColor(SES_ACCENT)
    canvas.rect(0, FOOTER_H, PAGE_W, 0.08 * cm, fill=1, stroke=0)
    canvas.setFillColor(SES_NAVY)
    canvas.rect(0, 0, PAGE_W, FOOTER_H, fill=1, stroke=0)

    _draw_image_fit(canvas, CIEVS_MT_LOGO_PATH, MARGIN_L, 0.22 * cm, 1.85 * cm, 0.95 * cm)
    canvas.setFillColor(colors.white)
    canvas.setFont(font_bold, 8.5)
    canvas.drawString(MARGIN_L + 2.05 * cm, FOOTER_H - 0.48 * cm, DEVELOPER_CREDIT)
    canvas.setFont(font, 8.0)
    canvas.drawString(
        MARGIN_L + 2.05 * cm,
        FOOTER_H - 0.82 * cm,
        f"{SYSTEM_NAME} — {SYSTEM_TAGLINE}",
    )
    canvas.setFillColor(colors.HexColor("#B8C4D9"))
    canvas.setFont(font, 7.5)
    canvas.drawString(
        MARGIN_L + 2.05 * cm,
        FOOTER_H - 1.12 * cm,
        "Ferramenta de apoio à gestão. Validar no painel e no território antes da comunicação oficial.",
    )
    canvas.setFillColor(colors.white)
    canvas.setFont(font, 8.5)
    canvas.drawRightString(
        PAGE_W - MARGIN_R,
        FOOTER_H - 0.70 * cm,
        f"Página {canvas.getPageNumber()}",
    )

    canvas.restoreState()


def page_callbacks(*, doc_title: str = "") -> tuple[Callable, Callable]:
    """Retorna (onFirstPage, onLaterPages) para SimpleDocTemplate.build."""

    def _draw(canvas: Canvas, doc) -> None:
        draw_institutional_page(canvas, doc, doc_title="")

    return _draw, _draw
