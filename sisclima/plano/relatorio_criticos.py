# -*- coding: utf-8 -*-
"""Relatório e apresentação dos indicadores críticos do Plano El Niño."""
from __future__ import annotations

import xml.sax.saxutils as sax
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sisclima.core.config import ROOT
from sisclima.plano.criticos import quadro_criticos
from sisclima.reporting.institutional_pdf import (
    CONTENT_BOTTOM_MARGIN,
    CONTENT_TOP_MARGIN,
    SES_ACCENT,
    SES_NAVY,
    page_callbacks,
    register_institutional_fonts,
)

DEFAULT_RELATORIO = ROOT / "docs" / "apresentacoes" / "Relatorio_indicadores_criticos_Plano_El_Nino.pdf"
DEFAULT_APRESENTACAO = ROOT / "docs" / "apresentacoes" / "Apresentacao_indicadores_criticos_Plano_El_Nino.pdf"

NAVY = SES_NAVY
ACCENT = SES_ACCENT
AMBER = colors.HexColor("#FEF3C7")
ROW = colors.HexColor("#F4F7FB")
GRID = colors.HexColor("#d1d5db")


def _esc(texto: Any) -> str:
    return sax.escape(str(texto or "").strip())


def _styles() -> dict[str, ParagraphStyle]:
    font, font_bold = register_institutional_fonts()
    return {
        "title": ParagraphStyle("cr_title", fontName=font_bold, fontSize=14, leading=18, textColor=NAVY, spaceAfter=6),
        "h2": ParagraphStyle("cr_h2", fontName=font_bold, fontSize=12, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle(
            "cr_body", fontName=font, fontSize=10.5, leading=14, textColor=colors.HexColor("#1f2937"),
            alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "small": ParagraphStyle("cr_small", fontName=font, fontSize=9, leading=12, textColor=colors.HexColor("#4b5563"), spaceAfter=4),
        "cell": ParagraphStyle("cr_cell", fontName=font, fontSize=7.5, leading=10, textColor=colors.HexColor("#111827")),
        "cell_b": ParagraphStyle("cr_cell_b", fontName=font_bold, fontSize=7.5, leading=10, textColor=colors.white),
        "slide_title": ParagraphStyle(
            "cr_slide", fontName=font_bold, fontSize=16, leading=20, textColor=NAVY, alignment=TA_LEFT, spaceAfter=8,
        ),
        "slide_body": ParagraphStyle(
            "cr_sbody", fontName=font, fontSize=12, leading=16, textColor=colors.HexColor("#1f2937"),
            alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "kpi": ParagraphStyle(
            "cr_kpi", fontName=font_bold, fontSize=18, leading=22, textColor=NAVY, alignment=TA_CENTER, spaceAfter=2,
        ),
        "kpi_l": ParagraphStyle(
            "cr_kpil", fontName=font, fontSize=8.5, leading=11, textColor=colors.HexColor("#4b5563"), alignment=TA_CENTER,
        ),
        "bullet": ParagraphStyle("cr_bullet", fontName=font, fontSize=12, leading=16, leftIndent=8, spaceAfter=4),
    }


def _tabela(rows: list[dict[str, Any]], styles: dict, *, com_leitura: bool = True) -> Table:
    font, font_bold = register_institutional_fonts()
    header = [
        Paragraph("ID", styles["cell_b"]),
        Paragraph("Indicador ajustado", styles["cell_b"]),
        Paragraph("Área", styles["cell_b"]),
        Paragraph("Papel", styles["cell_b"]),
        Paragraph("S/C", styles["cell_b"]),
    ]
    widths = [1.7 * cm, 6.2 * cm, 3.0 * cm, 1.8 * cm, 1.5 * cm]
    if com_leitura:
        header.append(Paragraph("Leitura", styles["cell_b"]))
        header.append(Paragraph("Por que é crítico", styles["cell_b"]))
        widths = [1.55 * cm, 4.4 * cm, 2.3 * cm, 1.6 * cm, 1.3 * cm, 1.4 * cm, 4.15 * cm]
    else:
        header.append(Paragraph("Por que é crítico", styles["cell_b"]))
        widths = [1.6 * cm, 5.2 * cm, 2.5 * cm, 1.7 * cm, 1.4 * cm, 4.4 * cm]
    data = [header]
    for r in rows:
        linha = [
            Paragraph(_esc(r.get("id")), styles["cell"]),
            Paragraph(_esc((r.get("nome") or "")[:110]), styles["cell"]),
            Paragraph(_esc((r.get("area") or "")[:36]), styles["cell"]),
            Paragraph(_esc(r.get("papel_rotulo") or "—"), styles["cell"]),
            Paragraph(_esc(f"{r.get('perfil_s') or '—'} / {r.get('padrao_c') or '—'}"), styles["cell"]),
        ]
        if com_leitura:
            linha.append(Paragraph(_esc(r.get("leitura") or "—"), styles["cell"]))
        linha.append(Paragraph(_esc((r.get("motivo") or "")[:220]), styles["cell"]))
        data.append(linha)
    table = Table(data, colWidths=widths, repeatRows=1)
    cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, GRID),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, ACCENT),
    ]
    for i, r in enumerate(rows, start=1):
        if r.get("pacote") in {"limiar", "sem_fonte"} or r.get("classe") == "B":
            cmds.append(("BACKGROUND", (0, i), (-1, i), AMBER))
        elif i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), ROW))
    table.setStyle(TableStyle(cmds))
    return table


def _kpis(quadro: dict[str, Any], styles: dict) -> Table:
    items = [
        (str(quadro["n_limiar"]), "Limiares a homologar"),
        (str(quadro["n_sem_fonte"]), "Sem conector (N/A)"),
        (str(quadro["n_classe_b"]), "Classe B"),
        (str(quadro["n_gatilho"]), "Gatilhos"),
        (str(quadro["n_prontidao"]), "Gates de prontidão"),
    ]
    cells = []
    labels = []
    for n, lab in items:
        cells.append(Paragraph(n, styles["kpi"]))
        labels.append(Paragraph(lab, styles["kpi_l"]))
    tbl = Table([cells, labels], colWidths=[3.36 * cm] * 5)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#E8EEF9")),
                ("BOX", (0, 0), (-1, -1), 0.4, ACCENT),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, GRID),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return tbl


def pdf_bytes_relatorio_criticos(*, coletado_em: str = "") -> bytes:
    quadro = quadro_criticos()
    quando = coletado_em or datetime.now().strftime("%d/%m/%Y %H:%M")
    styles = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title="Indicadores críticos do Plano El Niño — ARARAS MT",
        author="CIEVS · SES-MT",
    )
    story: list[Any] = [
        Paragraph("Indicadores mais críticos do Plano El Niño", styles["title"]),
        Paragraph(
            f"ARARAS MT · Sala de Situação Saúde e Clima · { _esc(quando) } · "
            "adequação dos 88 indicadores (28/08/2026).",
            styles["small"],
        ),
        Paragraph(
            "Este recorte não substitui os 88 IDs. Destaca o que impede operação automática, "
            "o que escala a resposta e o que ainda não é calculável. "
            "Sem dado válido o ARARAS não inventa numerador. Denominador 0 gera N/A, nunca 100%. "
            "Gatilho de risco não entra no Índice de Implementação.",
            styles["body"],
        ),
        _kpis(quadro, styles),
        Spacer(1, 0.2 * cm),
        Paragraph(quadro["nota"], styles["small"]),
        Paragraph("1. Limiares e baselines — deliberação 6", styles["h2"]),
        Paragraph(
            "Prioridade técnica antes do go-live: ARARA-013, 016, 021, 062–067 e 075–077. "
            "Sem limiar versionado, o gatilho não dispara regra automática. "
            "IND-062 permanece agrupador; 062A (triatomíneos) e 062B (peçonhentos) não misturam fenômenos.",
            styles["body"],
        ),
        _tabela(quadro["limiares"], styles),
        Paragraph("2. Não calculáveis nesta rodada (sem fonte contínua)", styles["h2"]),
        Paragraph(
            "Cinza no painel: falta de SISAGUA/VIGIÁGUA, entomologia COVSAM ou denúncias COVSAN. "
            "Isso é pendência de qualidade de dado — não é atraso de execução nem risco epidemiológico inventado.",
            styles["body"],
        ),
        _tabela(quadro["sem_fonte"], styles),
        Paragraph("3. Classe B — ainda falta parametrizar", styles["h2"]),
        Paragraph(
            "Usáveis só depois de universo-alvo, SLA ou limiar homologado pelo CIEVS/área. "
            "Não preencher o vazio com zero.",
            styles["body"],
        ),
        _tabela(quadro["classe_b"], styles),
        Paragraph("4. Gatilhos de risco (16)", styles["h2"]),
        Paragraph(
            "Detectam agravamento e abrem verificação/PAI a partir do Amarelo. "
            "Não contam como meta cumprida nem como falha de execução. "
            "O estágio de resposta continua decisão do Comando, separado do nível de risco.",
            styles["body"],
        ),
        _tabela(quadro["gatilhos"], styles, com_leitura=False),
        Paragraph("5. Gates de prontidão", styles["h2"]),
        Paragraph(
            "Documentos, protocolos, planos e simulado devem estar 100% no Verde/Amarelo. "
            "Em Laranja/Vermelho/Roxo a Sala mede acionamento e validade, não nova produção documental.",
            styles["body"],
        ),
        _tabela(quadro["prontidao"], styles, com_leitura=False),
        Paragraph("6. Encaminhamento para a Sala", styles["h2"]),
        Paragraph(
            "1) Homologar limiares do pacote 1 com as áreas donas da regra.<br/>"
            "2) Integrar ou pactuar fonte para VIGIÁGUA, COVSAM e COVSAN (pacote 2).<br/>"
            "3) Fechar parâmetros de Classe B (universo e SLA).<br/>"
            "4) Tratar gates de prontidão como pré-requisito do Amarelo, não como KPI de crise.<br/>"
            "5) A partir do Amarelo, gatilho validado, SLA estourado ou interrupção essencial abre tarefa no PAI.",
            styles["body"],
        ),
        Paragraph(
            "Fonte: proposta de adequação 28/08/2026 · catálogo ARARA-001 a ARARA-088 · "
            "conectores do ARARAS. Uso interno da Sala. Validar no território antes de comunicação oficial.",
            styles["small"],
        ),
    ]
    on_first, on_later = page_callbacks()
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return buf.getvalue()


def pdf_bytes_apresentacao_criticos(*, coletado_em: str = "") -> bytes:
    quadro = quadro_criticos()
    quando = coletado_em or datetime.now().strftime("%d/%m/%Y")
    styles = _styles()
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title="Apresentação — indicadores críticos · Sala de Situação",
        author="CIEVS · SES-MT",
    )
    limiar_ids = ", ".join(r["codigo_fonte"] for r in quadro["limiares"])
    story: list[Any] = [
        Paragraph("Indicadores mais críticos", styles["slide_title"]),
        Paragraph("Sala de Situação Saúde e Clima · El Niño 2026–2027 · ARARAS MT", styles["small"]),
        Paragraph(f"CIEVS/SES-MT · { _esc(quando) } · 88 IDs preservados · 85 ativos · 3 aliases.", styles["small"]),
        _kpis(quadro, styles),
        Spacer(1, 0.25 * cm),
        Paragraph(
            "Risco, estágio de resposta, desempenho e completude são campos diferentes. "
            "Sem dado ≠ zero. Gatilho ≠ falha de execução.",
            styles["slide_body"],
        ),
        PageBreak(),
        Paragraph("O que a Sala precisa decidir hoje", styles["slide_title"]),
        Paragraph("1. Homologar limiares/baselines dos gatilhos listados na deliberação 6.", styles["bullet"]),
        Paragraph("2. Não operar automaticamente o que ainda é Classe B ou está sem fonte.", styles["bullet"]),
        Paragraph("3. Fechar gates de prontidão antes de subir para Amarelo.", styles["bullet"]),
        Paragraph("4. A partir do Amarelo, gatilho validado abre PAI — não reduz o índice do Plano.", styles["bullet"]),
        Paragraph("5. Manter ARARA-068, 073 e 074 como aliases, sem peso próprio.", styles["bullet"]),
        Spacer(1, 0.3 * cm),
        Paragraph(
            "O recorte crítico acelera a deliberação. A modelagem dos 88 não reabre: "
            "só entram em homologação os parâmetros (limiar, universo-alvo, SLA).",
            styles["slide_body"],
        ),
        PageBreak(),
        Paragraph("Pacote 1 — limiares a homologar", styles["slide_title"]),
        Paragraph(
            f"{quadro['n_limiar']} indicadores. Sem versão de corte, o ARARAS não dispara gatilho automático. "
            f"IDs: {_esc(limiar_ids)}.",
            styles["slide_body"],
        ),
        _tabela(quadro["limiares"], styles, com_leitura=False),
        PageBreak(),
        Paragraph("Pacote 2 — não calculável (sem fonte)", styles["slide_title"]),
        Paragraph(
            "Oito indicadores automáticos sem conector contínuo. O painel fica cinza. "
            "Não é vermelho de desempenho e não é ausência de risco no território.",
            styles["slide_body"],
        ),
        _tabela(quadro["sem_fonte"], styles, com_leitura=True),
        PageBreak(),
        Paragraph("Pacote 3 — Classe B", styles["slide_title"]),
        Paragraph(
            "Falta universo-alvo, SLA ou limiar homologado. "
            "075–077 (ovitrampa, IDO, IIP/Breteau) concentram entomologia + Classe B + sem fonte.",
            styles["slide_body"],
        ),
        _tabela(quadro["classe_b"], styles, com_leitura=False),
        PageBreak(),
        Paragraph("Pacote 4 — 16 gatilhos", styles["slide_title"]),
        Paragraph(
            "Abrem verificação territorial. Não entram no % de implementação. "
            "Persistência e população exposta sugerem escalonamento local — não elevam o Estado sozinhos.",
            styles["slide_body"],
        ),
        _tabela(quadro["gatilhos"][:12], styles, com_leitura=False),
        PageBreak(),
        Paragraph("Pacote 5 — prontidão e estoque", styles["slide_title"]),
        Paragraph(
            f"{quadro['n_prontidao']} gates documentais/simulados. "
            "Estoque (IND-024, 025, 058, 059): pode haver leitura, mas a carga pode estar defasada — "
            "não tratar como ruptura atual.",
            styles["slide_body"],
        ),
        Paragraph("Gates (amostra)", styles["h2"]),
        _tabela(quadro["prontidao"][:8], styles, com_leitura=False),
        PageBreak(),
        Paragraph("Encaminhamento", styles["slide_title"]),
        Paragraph(
            "<b>Hoje:</b> validar a arquitetura (quatro estados, S1–S12, C1–C8, aliases, PAI no Amarelo).",
            styles["slide_body"],
        ),
        Paragraph(
            "<b>Áreas técnicas:</b> devolver só parâmetros — limiar, baseline, universo-alvo e SLA. "
            "Prioridade: fumaça/PM2,5 (013), sentinela (016), pressão assistencial (021), "
            "entomologia/zoonoses (062–067, 075–077).",
            styles["slide_body"],
        ),
        Paragraph(
            "<b>CIEVS:</b> não ligar regra automática enquanto o limiar não tiver versão, vigência e responsável.",
            styles["slide_body"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph(
            "Documento de apoio à Sala. Validar no painel e no território antes de comunicação oficial.",
            styles["small"],
        ),
    ]
    on_first, on_later = page_callbacks()
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return buf.getvalue()


def gerar_pdf_relatorio_criticos(dest: Path | None = None) -> Path:
    out = dest or DEFAULT_RELATORIO
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes_relatorio_criticos())
    return out


def gerar_pdf_apresentacao_criticos(dest: Path | None = None) -> Path:
    out = dest or DEFAULT_APRESENTACAO
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes_apresentacao_criticos())
    return out
