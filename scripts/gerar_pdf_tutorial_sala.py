# -*- coding: utf-8 -*-
"""Gera PDF do tutorial operacional da Sala (validação CIEVS)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.reporting.institutional_pdf import (  # noqa: E402
    CONTENT_BOTTOM_MARGIN,
    CONTENT_TOP_MARGIN,
    page_callbacks,
    register_institutional_fonts,
)

SRC = ROOT / "docs" / "institucional" / "TUTORIAL_SALA_PAINEL_EVENTOS_INDICADORES.md"
OUT = (
    ROOT
    / "docs"
    / "institucional"
    / "Tutorial_ARARAS_MT_Sala_Painel_Eventos_Indicadores.pdf"
)

SES_BLUE = colors.HexColor("#1351B4")
SES_DEEP = colors.HexColor("#1D357F")
SES_HEADER_BG = colors.HexColor("#E8EEF9")
SES_ROW_ALT = colors.HexColor("#F7F9FC")
SES_GRID = colors.HexColor("#C8D2E6")


def _esc(text: str) -> str:
    return (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _inline(md: str) -> str:
    s = _esc(md)
    s = re.sub(r"`([^`]+)`", r"<font face='Courier' size='9'>\1</font>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    return s


def _styles():
    font, font_bold = register_institutional_fonts()
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "t_title",
            parent=base["Title"],
            fontName=font_bold,
            fontSize=16,
            leading=20,
            textColor=SES_DEEP,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "t_h1",
            parent=base["Heading1"],
            fontName=font_bold,
            fontSize=13,
            leading=17,
            textColor=SES_DEEP,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "t_h2",
            parent=base["Heading2"],
            fontName=font_bold,
            fontSize=11.5,
            leading=15,
            textColor=SES_BLUE,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "t_h3",
            parent=base["Heading3"],
            fontName=font_bold,
            fontSize=10.5,
            leading=13,
            textColor=SES_DEEP,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "t_body",
            parent=base["Normal"],
            fontName=font,
            fontSize=9.5,
            leading=13,
            alignment=TA_JUSTIFY,
            spaceAfter=4,
        ),
        "meta": ParagraphStyle(
            "t_meta",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "t_code",
            parent=base["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            backColor=colors.HexColor("#F1F5F9"),
            leftIndent=4,
            rightIndent=4,
            spaceBefore=4,
            spaceAfter=6,
        ),
        "li": ParagraphStyle(
            "t_li",
            parent=base["Normal"],
            fontName=font,
            fontSize=9.5,
            leading=12.5,
            leftIndent=2,
        ),
        "th": ParagraphStyle(
            "t_th",
            parent=base["Normal"],
            fontName=font_bold,
            fontSize=8.5,
            leading=11,
            textColor=colors.white,
        ),
        "td": ParagraphStyle(
            "t_td",
            parent=base["Normal"],
            fontName=font,
            fontSize=8.2,
            leading=10.5,
        ),
        "footer_note": ParagraphStyle(
            "t_fn",
            parent=base["Normal"],
            fontName=font,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#64748B"),
            alignment=TA_CENTER,
            spaceBefore=12,
        ),
    }
    return styles


def _parse_table(lines: list[str], styles) -> Table | None:
    rows_raw = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.match(r"^:?-+:?$", c or "") for c in cells):
            continue
        rows_raw.append(cells)
    if len(rows_raw) < 2:
        return None
    ncols = max(len(r) for r in rows_raw)
    data = []
    for i, row in enumerate(rows_raw):
        padded = row + [""] * (ncols - len(row))
        sty = styles["th"] if i == 0 else styles["td"]
        data.append([Paragraph(_inline(c), sty) for c in padded])
    col_w = (A4[0] - 4.0 * cm) / ncols
    tbl = Table(data, colWidths=[col_w] * ncols, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_DEEP),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, SES_GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, r), (-1, r), SES_ROW_ALT))
        else:
            style_cmds.append(("BACKGROUND", (0, r), (-1, r), colors.white))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def build_pdf(src: Path = SRC, out: Path = OUT) -> Path:
    styles = _styles()
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()
    story = []
    i = 0
    title_done = False
    while i < len(lines):
        line = lines[i]
        raw = line.rstrip()
        if not raw.strip():
            i += 1
            continue
        if raw.strip() == "---":
            i += 1
            continue
        if raw.startswith("# ") and not title_done:
            story.append(Paragraph(_inline(raw[2:].strip()), styles["title"]))
            story.append(
                Paragraph(
                    "Documento para validação CIEVS · ARARAS MT · SES-MT · v1.1",
                    styles["meta"],
                )
            )
            title_done = True
            i += 1
            continue
        if raw.startswith("## "):
            story.append(Paragraph(_inline(raw[3:].strip()), styles["h1"]))
            i += 1
            continue
        if raw.startswith("### "):
            story.append(Paragraph(_inline(raw[4:].strip()), styles["h2"]))
            i += 1
            continue
        if raw.startswith("#### "):
            story.append(Paragraph(_inline(raw[5:].strip()), styles["h3"]))
            i += 1
            continue
        if re.match(r"^[-*] \[[ xX]\] ", raw.strip()) or re.match(r"^[-*] ", raw.strip()) or re.match(r"^\d+\.\s", raw.strip()):
            items = []
            while i < len(lines) and (
                re.match(r"^[-*] ", lines[i].strip())
                or re.match(r"^\d+\.\s", lines[i].strip())
                or (lines[i].startswith("   ") and lines[i].strip().startswith("-"))
            ):
                t = lines[i].strip()
                t = re.sub(r"^[-*]\s+\[[ xX]\]\s+", "☐ ", t)
                t = re.sub(r"^[-*]\s+", "", t)
                t = re.sub(r"^\d+\.\s+", "", t)
                items.append(ListItem(Paragraph(_inline(t), styles["li"]), leftIndent=8, bulletColor=SES_BLUE))
                i += 1
            story.append(
                ListFlowable(
                    items,
                    bulletType="bullet",
                    start="•",
                    leftIndent=14,
                    bulletFontSize=8,
                    spaceBefore=2,
                    spaceAfter=4,
                )
            )
            continue
        if raw.strip().startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i].replace("─", "-").replace("→", "->").replace("↓", "v"))
                i += 1
            i += 1
            # Evita lixo visual de caixas ASCII no PDF
            cleaned = "\n".join(block).strip()
            if cleaned and not re.search(r"[|]{3,}|I{8,}", cleaned):
                story.append(Preformatted(cleaned, styles["code"]))
            continue
        if raw.strip().startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            tbl = _parse_table(block, styles)
            if tbl:
                story.append(Spacer(1, 4))
                story.append(tbl)
                story.append(Spacer(1, 6))
            continue
        # parágrafo (pode juntar linhas)
        para = [raw]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if (
                not nxt.strip()
                or nxt.startswith("#")
                or nxt.strip().startswith("|")
                or nxt.strip().startswith("```")
                or nxt.strip() == "---"
                or re.match(r"^[-*] ", nxt.strip())
                or re.match(r"^\d+\.\s", nxt.strip())
            ):
                break
            para.append(nxt.strip())
            i += 1
        story.append(Paragraph(_inline(" ".join(para)), styles["body"]))

    story.append(
        Paragraph(
            "ARARAS MT · CIEVS-MT / SES-MT · Rede CIEVS · Vigidesastres — documento orientativo para validação.",
            styles["footer_note"],
        )
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title="Tutorial ARARAS MT — Sala, Painel e Indicadores",
        author="CIEVS-MT / SES-MT",
    )
    on_first, on_later = page_callbacks(
        doc_title="Tutorial operacional — Sala de Situação · Painel · Eventos · Indicadores",
    )
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return out


if __name__ == "__main__":
    path = build_pdf()
    print(path)
    print(f"size_kb={path.stat().st_size // 1024}")
