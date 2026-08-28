# -*- coding: utf-8 -*-
"""PDF institucional da coleta dos indicadores automáticos do Plano El Niño."""
from __future__ import annotations

import xml.sax.saxutils as sax
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sisclima.core.config import ROOT
from sisclima.reporting.institutional_pdf import (
    CONTENT_BOTTOM_MARGIN,
    CONTENT_TOP_MARGIN,
    SES_ACCENT,
    SES_NAVY,
    page_callbacks,
    register_institutional_fonts,
)

DEFAULT_OUT = ROOT / "docs" / "apresentacoes" / "Indicadores_automaticos_Plano_El_Nino.pdf"
DEFAULT_OUT_PLANO = ROOT / "docs" / "apresentacoes" / "Indicadores_Plano_El_Nino.pdf"
DEFAULT_OUT_COBRANCA = ROOT / "docs" / "apresentacoes" / "Cobranca_indicadores_Plano_El_Nino.pdf"

_SIT = {
    "coletado": "Coletado",
    "aguardando_fonte": "Aguardando fonte",
    "nao_informado": "Não informado pela área",
}

_CLASSE = {
    "area": "Informar na Sala",
    "fonte": "Integrar fonte",
    "carga": "Atualizar carga",
}


def _esc(texto: Any) -> str:
    return sax.escape(str(texto or "").strip())


def _styles() -> dict[str, ParagraphStyle]:
    font, font_bold = register_institutional_fonts()
    return {
        "title": ParagraphStyle(
            "ind_title",
            fontName=font_bold,
            fontSize=14,
            leading=18,
            textColor=SES_NAVY,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "ind_body",
            fontName=font,
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#1f2937"),
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "ind_small",
            fontName=font,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#4b5563"),
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        "cell": ParagraphStyle(
            "ind_cell",
            fontName=font,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#111827"),
        ),
        "cell_b": ParagraphStyle(
            "ind_cell_b",
            fontName=font_bold,
            fontSize=8,
            leading=10,
            textColor=colors.white,
        ),
    }


def coletar_linhas_automaticos() -> list[dict[str, Any]]:
    from sisclima.plano.conectores import coletar_automaticos
    from sisclima.plano.indicadores import linhas_painel_indicadores, quadro_indicadores

    quadro = quadro_indicadores(so_indice=False)
    leituras = coletar_automaticos()
    linhas = linhas_painel_indicadores(quadro=quadro, leituras_auto=leituras)
    return [r for r in linhas if r.get("modo") == "automatico"]


def pdf_bytes_indicadores_automaticos(
    linhas: list[dict[str, Any]] | None = None,
    *,
    coletado_em: str = "",
) -> bytes:
    rows = list(linhas) if linhas is not None else coletar_linhas_automaticos()
    quando = coletado_em or datetime.now().strftime("%d/%m/%Y %H:%M")
    styles = _styles()
    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("situacao") == "coletado")
    n_wait = sum(1 for r in rows if r.get("situacao") == "aguardando_fonte")
    aguardando = [r for r in rows if r.get("situacao") == "aguardando_fonte"]
    estoque = [r for r in rows if r.get("nota")]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title="Indicadores automáticos do Plano El Niño — ARARAS MT",
        author="CIEVS · SES-MT",
    )
    story: list[Any] = [
        Paragraph("Indicadores automáticos do Plano El Niño", styles["title"]),
        Paragraph(
            f"ARARAS MT · Sala de Situação · coleta { _esc(quando) } · "
            f"{n_ok} de {n} com leitura · {n_wait} aguardando fonte.",
            styles["small"],
        ),
        Paragraph(
            "Este relatório cobre apenas os indicadores em modo automático. "
            "Sem dado da fonte, o ARARAS não inventa numerador. "
            "Denominador estadual = 142 municípios (código IBGE 510000 excluído). "
            "Ausência de registro não é convertida em zero.",
            styles["body"],
        ),
    ]
    if aguardando:
        blocos: dict[str, list[str]] = {}
        for r in aguardando:
            chave = str(r.get("bloco_pendente") or "sem bloco")
            blocos.setdefault(chave, []).append(str(r.get("id") or ""))
        partes = "; ".join(f"{k} ({', '.join(v)})" for k, v in sorted(blocos.items()))
        story.append(
            Paragraph(
                f"<b>Aguardando fonte nesta rodada:</b> {_esc(partes)}. "
                "VIGIÁGUA/SISAGUA, entomologia (COVSAM) e denúncias (COVSAN) não têm conector contínuo.",
                styles["body"],
            )
        )
    if estoque:
        ids = ", ".join(str(r.get("id") or "") for r in estoque)
        story.append(
            Paragraph(
                f"<b>Estoque com leitura, carga possivelmente defasada:</b> {_esc(ids)}. "
                "Não tratar como ruptura atual até atualizar a carga oficial.",
                styles["body"],
            )
        )

    font, font_bold = register_institutional_fonts()
    header = [
        Paragraph("Código", styles["cell_b"]),
        Paragraph("Indicador", styles["cell_b"]),
        Paragraph("Área", styles["cell_b"]),
        Paragraph("Situação", styles["cell_b"]),
        Paragraph("Leitura", styles["cell_b"]),
        Paragraph("Fonte / motivo", styles["cell_b"]),
    ]
    data = [header]
    for r in rows:
        data.append(
            [
                Paragraph(_esc(r.get("id")), styles["cell"]),
                Paragraph(_esc((r.get("nome") or "")[:90]), styles["cell"]),
                Paragraph(_esc((r.get("area") or "")[:42]), styles["cell"]),
                Paragraph(_esc(_SIT.get(str(r.get("situacao") or ""), r.get("situacao"))), styles["cell"]),
                Paragraph(_esc(r.get("leitura") or "—"), styles["cell"]),
                Paragraph(_esc((r.get("fonte") or "")[:80]), styles["cell"]),
            ]
        )
    table = Table(data, colWidths=[1.8 * cm, 4.8 * cm, 2.6 * cm, 2.4 * cm, 1.8 * cm, 3.4 * cm], repeatRows=1)
    style_cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, SES_ACCENT),
    ]
    for i, r in enumerate(rows, start=1):
        if r.get("situacao") == "aguardando_fonte":
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEF3C7")))
        elif i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F4F7FB")))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        Paragraph(
            "Fonte: sisclima.plano.conectores · catálogo do Plano El Niño 2026. "
            "Uso interno da Sala de Situação. Validar no painel antes de comunicação oficial.",
            styles["small"],
        )
    )
    on_first, on_later = page_callbacks()
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return buf.getvalue()


def gerar_pdf_indicadores_automaticos(
    dest: Path | None = None,
    *,
    linhas: list[dict[str, Any]] | None = None,
    coletado_em: str = "",
) -> Path:
    out = dest or DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes_indicadores_automaticos(linhas, coletado_em=coletado_em))
    return out


def coletar_linhas_catalogo() -> list[dict[str, Any]]:
    from sisclima.plano.conectores import coletar_automaticos
    from sisclima.plano.indicadores import linhas_painel_indicadores, quadro_indicadores

    quadro = quadro_indicadores(so_indice=False)
    leituras = coletar_automaticos()
    return linhas_painel_indicadores(quadro=quadro, leituras_auto=leituras)


def pdf_bytes_indicadores_plano(
    linhas: list[dict[str, Any]] | None = None,
    *,
    coletado_em: str = "",
) -> bytes:
    from sisclima.plano.sugestoes import ONDA_1_DOCUMENTAIS, SEM_NUMERADOR, enriquecer_linhas

    rows = enriquecer_linhas(list(linhas) if linhas is not None else coletar_linhas_catalogo())
    quando = coletado_em or datetime.now().strftime("%d/%m/%Y %H:%M")
    styles = _styles()
    n = len(rows)
    n_ok = sum(1 for r in rows if r.get("situacao") == "coletado")
    n_wait = sum(1 for r in rows if r.get("situacao") == "aguardando_fonte")
    n_area = sum(1 for r in rows if r.get("situacao") == "nao_informado")
    n_sug = sum(1 for r in rows if r.get("sugestao"))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title="Indicadores do Plano El Niño — ARARAS MT",
        author="CIEVS · SES-MT",
    )
    story: list[Any] = [
        Paragraph("Indicadores do Plano El Niño (catálogo completo)", styles["title"]),
        Paragraph(
            f"ARARAS MT · Sala de Situação · coleta {_esc(quando)} · "
            f"{n} indicadores · {n_ok} coletados · {n_wait} aguardando fonte · "
            f"{n_area} não informados pela área · {n_sug} com valor sugerido (não oficial).",
            styles["small"],
        ),
        Paragraph(
            "Sugestão é overlay: a área confirma na Sala. O ARARAS não grava numerador sugerido. "
            "Documentais (onda 1): Sim + SEI sobe o operacional. Inspeção Visa (onda 4): não zerar. "
            "SISAGUA, entomologia e denúncias ficam sem número até a fonte. "
            "Denominador estadual = 142 (IBGE 510000 excluído).",
            styles["body"],
        ),
        Paragraph(
            "Onda 1 (documentais): "
            + ", ".join(ONDA_1_DOCUMENTAIS)
            + ". Sem numerador: "
            + ", ".join(sorted(SEM_NUMERADOR))
            + ".",
            styles["small"],
        ),
    ]
    story.extend(_story_clima_or(styles))
    font, font_bold = register_institutional_fonts()
    header = [
        Paragraph("Código", styles["cell_b"]),
        Paragraph("Indicador", styles["cell_b"]),
        Paragraph("Modo", styles["cell_b"]),
        Paragraph("Situação", styles["cell_b"]),
        Paragraph("Leitura", styles["cell_b"]),
        Paragraph("Sugerido", styles["cell_b"]),
        Paragraph("Onda", styles["cell_b"]),
    ]
    data = [header]
    for r in rows:
        data.append(
            [
                Paragraph(_esc(r.get("id")), styles["cell"]),
                Paragraph(_esc((r.get("nome") or "")[:70]), styles["cell"]),
                Paragraph(_esc(r.get("modo")), styles["cell"]),
                Paragraph(_esc(_SIT.get(str(r.get("situacao") or ""), r.get("situacao"))), styles["cell"]),
                Paragraph(_esc(r.get("leitura") or "—"), styles["cell"]),
                Paragraph(_esc(r.get("sugestao") or "—"), styles["cell"]),
                Paragraph(_esc(r.get("onda") or "—"), styles["cell"]),
            ]
        )
    table = Table(
        data,
        colWidths=[1.8 * cm, 5.4 * cm, 2.2 * cm, 2.6 * cm, 1.8 * cm, 1.8 * cm, 1.4 * cm],
        repeatRows=1,
    )
    style_cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, SES_ACCENT),
    ]
    for i, r in enumerate(rows, start=1):
        if r.get("situacao") == "aguardando_fonte":
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEF3C7")))
        elif r.get("sugestao") and r.get("situacao") == "nao_informado":
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#DBEAFE")))
        elif i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F4F7FB")))
    table.setStyle(TableStyle(style_cmds))
    story.append(table)
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        Paragraph(
            "Fonte: sisclima.plano.sugestoes · conectores · catálogo 2026. "
            "Uso interno da Sala. Índice oficial só após validação CIEVS.",
            styles["small"],
        )
    )
    on_first, on_later = page_callbacks()
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return buf.getvalue()


def gerar_pdf_indicadores_plano(
    dest: Path | None = None,
    *,
    linhas: list[dict[str, Any]] | None = None,
    coletado_em: str = "",
) -> Path:
    out = dest or DEFAULT_OUT_PLANO
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes_indicadores_plano(linhas, coletado_em=coletado_em))
    return out


def _png_linha(xs, ys, titulo: str, ylabel: str) -> Path | None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    if not xs or not ys:
        return None
    fig, ax = plt.subplots(figsize=(8.2, 2.6), dpi=110)
    ax.plot(xs, ys, color="#1351B4", linewidth=1.6)
    ax.set_title(titulo, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=8)
    ax.tick_params(labelsize=7)
    fig.autofmt_xdate()
    fig.tight_layout()
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "araras_sala_clima.png"
    try:
        fig.savefig(tmp, bbox_inches="tight")
    finally:
        plt.close(fig)
    return tmp if tmp.is_file() else None


def _story_clima_or(styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Linha do tempo climática, sazonalidade e OR — pedido da Sala."""
    from sisclima.plano.analise_clima_sala import painel_sala_clima

    clima = painel_sala_clima()
    story: list[Any] = [Paragraph("Clima no tempo, sazonalidade e grupos mais afetados", styles["title"])]
    if not clima.get("disponivel"):
        story.append(
            Paragraph(
                "Sem série climática ou OR nesta rodada. O ARARAS não inventa curva nem odds ratio.",
                styles["small"],
            )
        )
        return story
    story.append(
        Paragraph(
            "Linha do tempo: média estadual diária (Open-Meteo/biometeo). "
            "Sazonalidade: índice mensal de Tmáx (1 = média histórica). "
            "OR ecológico (município ou janela de 28 dias) — não é causalidade individual.",
            styles["body"],
        )
    )
    serie = clima.get("serie_clima")
    if serie is not None and not serie.empty and "tmax" in serie.columns and "data" in serie.columns:
        png = _png_linha(list(serie["data"]), list(pd.to_numeric(serie["tmax"], errors="coerce")), "Tmáx estadual (°C)", "°C")
        if png is not None:
            story.append(Image(str(png), width=16.5 * cm, height=5.0 * cm))
            story.append(Spacer(1, 0.1 * cm))
        story.append(
            Paragraph(
                f"{int(clima.get('n_dias_clima') or 0)} dias na série. "
                + (
                    f"Pico sazonal histórico: {_esc((clima.get('pico_sazonal') or {}).get('rotulo'))} "
                    f"(índice {(clima.get('pico_sazonal') or {}).get('indice', 0):.2f}). "
                    if clima.get("pico_sazonal")
                    else ""
                )
                + (
                    f"Mês corrente: índice {float(clima.get('indice_mes_atual')):.2f} (>1 = acima da média)."
                    if clima.get("indice_mes_atual") is not None
                    else ""
                ),
                styles["small"],
            )
        )
    saz = clima.get("sazonalidade")
    if saz is not None and not saz.empty and "indice_sazonal" in saz.columns:
        rotulo = "mes_rotulo" if "mes_rotulo" in saz.columns else "mes"
        linhas_saz = [[Paragraph("Mês", styles["cell_b"]), Paragraph("Índice sazonal Tmáx", styles["cell_b"])]]
        for _, r in saz.iterrows():
            if pd.isna(r.get("indice_sazonal")):
                continue
            linhas_saz.append(
                [
                    Paragraph(_esc(r.get(rotulo)), styles["cell"]),
                    Paragraph(f"{float(r.get('indice_sazonal') or 0):.2f}".replace(".", ","), styles["cell"]),
                ]
            )
        tab_saz = Table(linhas_saz, colWidths=[4 * cm, 4 * cm], repeatRows=1)
        tab_saz.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(Paragraph("Sazonalidade (índice mensal)", styles["small"]))
        story.append(tab_saz)
        story.append(Spacer(1, 0.15 * cm))
    pares = clima.get("or_pares")
    grupos = clima.get("or_grupos")
    or_t = clima.get("or_timeline")
    if pares is not None and not pares.empty:
        story.append(Paragraph("Odds ratio — pares exposição → desfecho (recorte municipal atual)", styles["small"]))
        head = [
            Paragraph("Exposição", styles["cell_b"]),
            Paragraph("Desfecho", styles["cell_b"]),
            Paragraph("OR", styles["cell_b"]),
            Paragraph("IC95%", styles["cell_b"]),
            Paragraph("p", styles["cell_b"]),
        ]
        data_or = [head]
        for _, r in pares.head(8).iterrows():
            lo = r.get("ic95_inferior")
            hi = r.get("ic95_superior")
            ic = "—"
            if lo is not None and hi is not None and pd.notna(lo) and pd.notna(hi):
                ic = f"{float(lo):.2f}–{float(hi):.2f}".replace(".", ",")
            data_or.append(
                [
                    Paragraph(_esc(r.get("exposicao")), styles["cell"]),
                    Paragraph(_esc(r.get("desfecho")), styles["cell"]),
                    Paragraph(f"{float(r.get('or') or 0):.2f}".replace(".", ","), styles["cell"]),
                    Paragraph(ic, styles["cell"]),
                    Paragraph(
                        "—" if pd.isna(r.get("p_value")) else f"{float(r.get('p_value')):.3f}".replace(".", ","),
                        styles["cell"],
                    ),
                ]
            )
        tab_or = Table(data_or, colWidths=[3.4 * cm, 3.6 * cm, 1.8 * cm, 3.2 * cm, 2.0 * cm], repeatRows=1)
        tab_or.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(tab_or)
        story.append(Spacer(1, 0.12 * cm))
    if grupos is not None and not grupos.empty:
        story.append(Paragraph("Odds ratio por regional (grupos com N≥12 municípios)", styles["small"]))
        head_g = [
            Paragraph("Grupo", styles["cell_b"]),
            Paragraph("Exposição", styles["cell_b"]),
            Paragraph("Desfecho", styles["cell_b"]),
            Paragraph("OR", styles["cell_b"]),
            Paragraph("N", styles["cell_b"]),
        ]
        data_g = [head_g]
        for _, r in grupos.head(8).iterrows():
            data_g.append(
                [
                    Paragraph(_esc(str(r.get("grupo"))[:28]), styles["cell"]),
                    Paragraph(_esc(r.get("exposicao")), styles["cell"]),
                    Paragraph(_esc(r.get("desfecho")), styles["cell"]),
                    Paragraph(f"{float(r.get('or') or 0):.2f}".replace(".", ","), styles["cell"]),
                    Paragraph(str(int(r.get("n_municipios") or 0)), styles["cell"]),
                ]
            )
        tab_g = Table(data_g, colWidths=[3.8 * cm, 3.2 * cm, 3.4 * cm, 1.8 * cm, 1.6 * cm], repeatRows=1)
        tab_g.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(tab_g)
        story.append(Spacer(1, 0.12 * cm))
    if or_t is not None and not or_t.empty and "or" in or_t.columns and "data" in or_t.columns:
        png_or = _png_linha(
            list(pd.to_datetime(or_t["data"], errors="coerce")),
            list(pd.to_numeric(or_t["or"], errors="coerce")),
            "OR no tempo (janela 28 dias)",
            "OR",
        )
        if png_or is not None:
            story.append(Image(str(png_or), width=16.5 * cm, height=4.6 * cm))
            story.append(Paragraph("OR > 1: desfecho alto mais frequente na alta exposição, naquela janela.", styles["small"]))
    story.append(Spacer(1, 0.25 * cm))
    return story


def _story_risco_pressao(styles: dict[str, ParagraphStyle]) -> list[Any]:
    """Mapa de risco + registro de pressão assistencial, se o resumo existir."""
    from sisclima.core.db import read_table
    from sisclima.engines.boletim_el_nino.maps import export_mapa_risco
    from sisclima.reporting.quadro_risco_pressao import quadro_risco_pressao

    resumo = read_table("resumo_municipal_atual")
    quadro = quadro_risco_pressao(resumo)
    story: list[Any] = [
        Paragraph("Risco operacional e pressão assistencial", styles["title"]),
    ]
    if not quadro.get("disponivel"):
        story.append(
            Paragraph(
                _esc(quadro.get("motivo") or "Registro estadual indisponível nesta rodada."),
                styles["small"],
            )
        )
        return story

    story.append(
        Paragraph(
            f"{quadro.get('n_municipios') or 0} municípios no resumo. "
            f"Risco: {_esc(quadro.get('dist_nivel_txt'))}. "
            f"Ocupação de leitos: média {_esc(quadro.get('ocupacao_media_txt'))}% "
            f"(máx {_esc(quadro.get('ocupacao_max_txt'))}%). "
            f"Pressão por calor (0–15): média {_esc(quadro.get('calor_media_txt'))} · "
            f"máx {_esc(quadro.get('calor_max_txt'))}. "
            + (
                f"Índice de pressão 0–100: média {_esc(quadro.get('pressao_media_txt'))} · "
                f"máx {_esc(quadro.get('pressao_max_txt'))} · semáforo G/A/V {_esc(quadro.get('semaforo_txt'))}. "
                if quadro.get("pressao_n")
                else "Índice 0–100 (IndicaSUS/SISREG/SINAN/SIM) não está nesta rodada — sem inventar zero. "
            )
            + "O mapa usa a classificação operacional (verde→roxa); a tabela registra ocupação e pressão.",
            styles["body"],
        )
    )
    mapa = export_mapa_risco(resumo) if resumo is not None and not resumo.empty else {"disponivel": False}
    path = Path(str(mapa.get("path") or ""))
    if mapa.get("disponivel") and path.is_file():
        story.append(Image(str(path), width=16.8 * cm, height=11.4 * cm))
        story.append(Spacer(1, 0.15 * cm))
    elif mapa.get("motivo"):
        story.append(Paragraph(f"Mapa: {_esc(mapa.get('motivo'))}.", styles["small"]))

    header = [
        Paragraph("Município", styles["cell_b"]),
        Paragraph("Risco", styles["cell_b"]),
        Paragraph("Ocupação", styles["cell_b"]),
        Paragraph("Pressão calor", styles["cell_b"]),
        Paragraph("Pressão 0–100", styles["cell_b"]),
        Paragraph("Regional", styles["cell_b"]),
    ]
    data = [header]
    for r in quadro.get("registros") or []:
        pressao = r.get("indice_pressao_saude")
        ocup = r.get("ocupacao_leitos_pct")
        calor = r.get("pressao_calor_pct")
        data.append(
            [
                Paragraph(_esc(r.get("municipio")), styles["cell"]),
                Paragraph(_esc(r.get("nivel")), styles["cell"]),
                Paragraph("—" if ocup is None else f"{ocup:.1f}%".replace(".", ","), styles["cell"]),
                Paragraph("—" if calor is None else f"{calor:.1f}/15".replace(".", ","), styles["cell"]),
                Paragraph("—" if pressao is None else f"{pressao:.1f}".replace(".", ","), styles["cell"]),
                Paragraph(_esc((r.get("regional") or "")[:28]), styles["cell"]),
            ]
        )
    table = Table(data, colWidths=[3.6 * cm, 2.0 * cm, 2.3 * cm, 2.6 * cm, 2.5 * cm, 3.8 * cm], repeatRows=1)
    font, font_bold = register_institutional_fonts()
    cmds: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, SES_ACCENT),
    ]
    nivel_bg = {
        "roxa": "#EDE9FE",
        "vermelha": "#FEE2E2",
        "laranja": "#FFEDD5",
        "amarela": "#FEF3C7",
    }
    for i, r in enumerate(quadro.get("registros") or [], start=1):
        bg = nivel_bg.get(str(r.get("nivel") or ""), "#F4F7FB" if i % 2 == 0 else None)
        if bg:
            cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(bg)))
    table.setStyle(TableStyle(cmds))
    story.append(Paragraph("Registro — 10 municípios de maior risco/pressão", styles["small"]))
    story.append(table)
    story.append(Spacer(1, 0.3 * cm))
    return story


def pdf_bytes_cobranca(
    relatorio: dict[str, Any] | None = None,
    *,
    coletado_em: str = "",
) -> bytes:
    from sisclima.plano.cobranca import relatorio_cobranca

    rel = relatorio if relatorio is not None else relatorio_cobranca(coletado_em=coletado_em)
    quando = coletado_em or str(rel.get("coletado_em") or datetime.now().strftime("%d/%m/%Y %H:%M"))
    styles = _styles()
    n = int(rel.get("n_pendencias") or 0)
    n_area = int(rel.get("n_cobrar_area") or 0)
    n_fonte = int(rel.get("n_aguardar_fonte") or 0)
    n_carga = int(rel.get("n_carga_defasada") or 0)
    n_doc = int(rel.get("n_documentais") or 0)
    focais = rel.get("areas_sem_focal") or []
    areas = list(rel.get("areas") or [])
    itens = list(rel.get("itens") or [])

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title="Cobrança de indicadores do Plano El Niño — ARARAS MT",
        author="CIEVS · SES-MT",
    )
    story: list[Any] = [
        Paragraph("Cobrança de indicadores do Plano El Niño", styles["title"]),
        Paragraph(
            f"ARARAS MT · Sala de Situação · coleta {_esc(quando)} · "
            f"{n} pendências ({n_area} para a área informar · {n_fonte} aguardando fonte · "
            f"{n_carga} com carga defasada). {n_doc} documentais sem evidência SEI.",
            styles["small"],
        ),
        Paragraph(
            "Este ofício lista o que cada área precisa registrar na Sala. "
            "E-mail e WhatsApp só cobram; o índice só muda com numerador informado "
            "ou evidência validada pelo CIEVS. O ARARAS não inventa zero.",
            styles["body"],
        ),
    ]
    story.extend(_story_risco_pressao(styles))
    story.extend(_story_clima_or(styles))
    if focais:
        nomes = ", ".join(str(f.get("area") or f.get("area_id")) for f in focais)
        story.append(
            Paragraph(
                f"<b>Pontos focais ausentes no cadastro da Portaria 0590:</b> {_esc(nomes)}. "
                "IND-001 está em 9/11 até essas áreas terem e-mail no catálogo.",
                styles["body"],
            )
        )

    font, font_bold = register_institutional_fonts()
    header_area = [
        Paragraph("Área", styles["cell_b"]),
        Paragraph("Informar", styles["cell_b"]),
        Paragraph("Fonte", styles["cell_b"]),
        Paragraph("Carga", styles["cell_b"]),
        Paragraph("No índice", styles["cell_b"]),
        Paragraph("E-mails (Portaria 0590)", styles["cell_b"]),
    ]
    data_area = [header_area]
    for a in areas:
        emails = "; ".join(c.get("email") or "" for c in a.get("contatos") or []) or "sem e-mail no cadastro"
        data_area.append(
            [
                Paragraph(_esc(a.get("area")), styles["cell"]),
                Paragraph(str(a.get("n_area") or 0), styles["cell"]),
                Paragraph(str(a.get("n_fonte") or 0), styles["cell"]),
                Paragraph(str(a.get("n_carga") or 0), styles["cell"]),
                Paragraph(str(a.get("n_indice") or 0), styles["cell"]),
                Paragraph(_esc(emails), styles["cell"]),
            ]
        )
    table_area = Table(
        data_area,
        colWidths=[3.4 * cm, 1.6 * cm, 1.5 * cm, 1.5 * cm, 1.7 * cm, 7.1 * cm],
        repeatRows=1,
    )
    cmds_area: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, SES_ACCENT),
    ]
    for i, a in enumerate(areas, start=1):
        if int(a.get("n_area") or 0) >= 9:
            cmds_area.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEE2E2")))
        elif int(a.get("n_area") or 0) >= 3:
            cmds_area.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEF3C7")))
        elif i % 2 == 0:
            cmds_area.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F4F7FB")))
    table_area.setStyle(TableStyle(cmds_area))
    story.append(Paragraph("Pendências por área responsável", styles["title"]))
    story.append(table_area)
    story.append(Spacer(1, 0.3 * cm))

    header_item = [
        Paragraph("Código", styles["cell_b"]),
        Paragraph("Indicador", styles["cell_b"]),
        Paragraph("Área", styles["cell_b"]),
        Paragraph("Classe", styles["cell_b"]),
        Paragraph("Ação", styles["cell_b"]),
    ]
    data_item = [header_item]
    for r in itens:
        data_item.append(
            [
                Paragraph(_esc(r.get("id")), styles["cell"]),
                Paragraph(_esc((r.get("nome") or "")[:80]), styles["cell"]),
                Paragraph(_esc((r.get("area") or "")[:36]), styles["cell"]),
                Paragraph(_esc(_CLASSE.get(str(r.get("classe") or ""), r.get("classe"))), styles["cell"]),
                Paragraph(_esc((r.get("acao") or "")[:110]), styles["cell"]),
            ]
        )
    table_item = Table(
        data_item,
        colWidths=[1.8 * cm, 4.6 * cm, 2.8 * cm, 2.2 * cm, 5.4 * cm],
        repeatRows=1,
    )
    cmds_item: list[tuple] = [
        ("BACKGROUND", (0, 0), (-1, 0), SES_NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), font_bold),
        ("FONTNAME", (0, 1), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPPADDING", (0, 0), (-1, -1), 3),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d1d5db")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, SES_ACCENT),
    ]
    for i, r in enumerate(itens, start=1):
        classe = str(r.get("classe") or "")
        if classe == "area" and r.get("modo") == "documental":
            cmds_item.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#DBEAFE")))
        elif classe == "fonte":
            cmds_item.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FEF3C7")))
        elif classe == "carga":
            cmds_item.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F3E8FF")))
        elif i % 2 == 0:
            cmds_item.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F4F7FB")))
    table_item.setStyle(TableStyle(cmds_item))
    story.append(Paragraph("Lista de cobrança", styles["title"]))
    story.append(table_item)
    story.append(Spacer(1, 0.25 * cm))
    story.append(
        Paragraph(
            "Fonte: sisclima.plano.cobranca · catálogo do Plano El Niño 2026. "
            "Uso interno da Sala. Validar no painel antes de comunicação oficial. "
            f"Cópia CIEVS: {', '.join(rel.get('cc_cievs') or [])}.",
            styles["small"],
        )
    )
    on_first, on_later = page_callbacks()
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    return buf.getvalue()


def gerar_pdf_cobranca(
    dest: Path | None = None,
    *,
    relatorio: dict[str, Any] | None = None,
    coletado_em: str = "",
) -> Path:
    out = dest or DEFAULT_OUT_COBRANCA
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes_cobranca(relatorio, coletado_em=coletado_em))
    return out
