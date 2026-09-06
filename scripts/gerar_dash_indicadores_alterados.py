# -*- coding: utf-8 -*-
"""Gera PDF-dash: indicadores alterados × mantidos."""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "apresentacoes" / "indicadores_alterados_vs_mantidos.json"
OUT = ROOT / "docs" / "apresentacoes" / "Dash_Indicadores_Alterados_vs_Mantidos.pdf"


def main() -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=landscape(A4),
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "t", parent=styles["Heading1"], fontSize=16, spaceAfter=6, textColor=colors.HexColor("#0B1F33")
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontSize=12,
        spaceBefore=8,
        spaceAfter=4,
        textColor=colors.HexColor("#0B1F33"),
    )
    body = ParagraphStyle("b", parent=styles["Normal"], fontSize=8, leading=10)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=7.5, leading=9)
    cell = ParagraphStyle("c", parent=styles["Normal"], fontSize=7, leading=8.5, alignment=TA_LEFT)

    story: list = []
    story.append(Paragraph("ARARAS MT — Painel de indicadores do Plano El Niño", title))
    story.append(
        Paragraph(
            "Atualização após Matriz Plano de Ação Revisada · 88 indicadores mantidos no sistema",
            body,
        )
    )
    story.append(Spacer(1, 8))
    r = data["resumo"]
    resumo = [
        [
            Paragraph(f"<b>Total</b><br/>{r['total']}", cell),
            Paragraph(f"<b>Alterados</b><br/>{r['alterados']} (texto revisado)", cell),
            Paragraph(f"<b>Mantidos</b><br/>{r['mantidos']} (legado ARARA)", cell),
            Paragraph(f"<b>Ações</b><br/>{r['acoes']} na planilha revisada", cell),
        ]
    ]
    t = Table(resumo, colWidths=[6.5 * cm, 7 * cm, 7 * cm, 6.5 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#E8EEF5")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#DCEFE4")),
                ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#F3E8D8")),
                ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#E8EEF5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9AA8B5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA8B5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t)
    story.append(Spacer(1, 6))
    story.append(
        Paragraph(
            f"Fonte: {r.get('fonte')} · Atualizado em: {r.get('atualizado_em')} · "
            "IDs oficiais IND-001..088 preservados",
            small,
        )
    )

    def add_table(titulo: str, rows: list[list[str]], header_hex: str, headers: list[str]) -> None:
        story.append(Paragraph(titulo, h2))
        table_data = [[Paragraph(f"<b>{h}</b>", cell) for h in headers]]
        for row in rows:
            table_data.append([Paragraph(str(x), cell) for x in row])
        if len(headers) == 3:
            colw = [2.2 * cm, 2.4 * cm, 22.4 * cm]
        else:
            colw = [2.2 * cm, 2.4 * cm, 3.8 * cm, 18.6 * cm]
        tbl = Table(table_data, colWidths=colw, repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_hex)),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0B1F33")),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA8B5")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C5CED6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        story.append(tbl)

    alt_rows = [[a["id"], a["codigo_fonte"], a["nome"]] for a in data["alterados"]]
    mant_rows = [
        [m["id"], m["codigo_fonte"], m.get("origem_carga", ""), m["nome"]] for m in data["mantidos"]
    ]
    add_table(
        f"Indicadores ALTERADOS ({len(alt_rows)}) — nome atualizado pela planilha revisada",
        alt_rows,
        "#DCEFE4",
        ["ID", "Código", "Nome atual"],
    )
    story.append(PageBreak())
    add_table(
        f"Indicadores MANTIDOS ({len(mant_rows)}) — texto legado preservado (conectores/escalonamento)",
        mant_rows,
        "#F3E8D8",
        ["ID", "Código", "Origem", "Nome"],
    )
    doc.build(story)
    print(f"OK {OUT} bytes={OUT.stat().st_size}")


if __name__ == "__main__":
    main()
