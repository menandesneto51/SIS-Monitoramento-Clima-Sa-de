from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from sisclima.reporting.institutional_pdf import (
    CONTENT_BOTTOM_MARGIN,
    CONTENT_TOP_MARGIN,
    page_callbacks,
    register_institutional_fonts,
)

DEFAULT_SRC = ROOT / "docs" / "apresentacoes" / "Boletim_ElNino_SE_34-2026.md"
DEFAULT_OUT = ROOT / "docs" / "apresentacoes" / "Boletim_ElNino_SE_34-2026_apresentavel.pdf"

SES_BLUE = colors.HexColor("#1351B4")
SES_DEEP = colors.HexColor("#1D357F")
SES_HEADER_BG = colors.HexColor("#E8EEF9")
SES_ROW_ALT = colors.HexColor("#F7F9FC")
SES_GRID = colors.HexColor("#C8D2E6")

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

# Títulos que devem permanecer junto ao conteúdo seguinte (mapa/tabela)
_KEEP_WITH_NEXT_TITLES = {
    "1. resumo executivo",
    "mapa 1",
    "mapa 2",
    "mapa 3",
    "10. impactos potenciais à saúde",
    "10. impactos potenciais a saude",
    "11c. povos indígenas e comunidades tradicionais em áreas prioritárias",
    "11c. povos indigenas e comunidades tradicionais em areas prioritarias",
    "cenário: seca / estiagem",
    "cenario: seca / estiagem",
    "cenário: seca/estiagem",
    "cenario: seca/estiagem",
    "cenário: chuva intensa",
    "cenario: chuva intensa",
    "determinantes do agravamento projetado",
    "13. orientações operacionais por cenário climático",
    "13. orientacoes operacionais por cenario climatico",
    "17. glossario",
    "18. referencias",
    "populações prioritárias",
    "matriz clima × saúde × estoque × ação",
    "matriz clima x saude x estoque x acao",
    "registros selecionados de autonomia crítica",
    "registros selecionados de autonomia critica",
    "última situação registrada",
    "ultima situacao registrada",
}


def _register_calibri() -> None:
    global FONT, FONT_BOLD
    FONT, FONT_BOLD = register_institutional_fonts()
    # Garante nomes Calibri se disponíveis
    fonts_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    if (fonts_dir / "calibri.ttf").exists():
        if "Calibri" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Calibri", str(fonts_dir / "calibri.ttf")))
        FONT = "Calibri"
    if (fonts_dir / "calibrib.ttf").exists():
        if "Calibri-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("Calibri-Bold", str(fonts_dir / "calibrib.ttf")))
        FONT_BOLD = "Calibri-Bold"


def _soft_break_urls(text: str) -> str:
    """Insere <br/> preferencialmente após / ? & - _ em URLs (não quebra https://)."""

    def _fix(m: re.Match) -> str:
        url = m.group(0)
        # preserva esquema
        if "://" in url:
            scheme, rest = url.split("://", 1)
            parts = re.split(r"([/?&\-_])", rest)
            out = [scheme, "://"]
            buf = ""
            for p in parts:
                buf += p
                if p in {"/", "?", "&", "-", "_"} and len(buf) > 12:
                    out.append(buf)
                    out.append("<br/>")
                    buf = ""
            if buf:
                out.append(buf)
            return "".join(out)
        return url

    return re.sub(r"https?://[^\s<>\"]+", _fix, text)


def _md_inline_to_rl(text: str) -> str:
    """Converte **negrito** e *itálico* Markdown em tags ReportLab; remove asteriscos visíveis."""
    raw = text.strip()
    raw = raw.replace("`", "")
    raw = raw.replace("####", "")
    raw = raw.replace("&gt;", ">")
    raw = raw.replace("&lt;", "<")
    raw = raw.replace("seca_baixa", "Seca – nível baixo")
    raw = raw.replace("inundacao_alta", "Risco elevado de inundação")
    raw = raw.replace("pendente_sql_dw", "Integração de dados ainda não disponível")
    raw = (
        raw.replace("↑", "^")
        .replace("↓", "v")
        .replace("●", "*")
        .replace("○", "o")
    )
    # Preserva seta tipográfica → (Calibri); normaliza ASCII residual
    raw = raw.replace("->", "→")

    # Negrito primeiro
    parts: list[str] = []
    i = 0
    while i < len(raw):
        if raw.startswith("**", i):
            j = raw.find("**", i + 2)
            if j != -1:
                parts.append("<b>" + escape(raw[i + 2 : j]) + "</b>")
                i = j + 2
                continue
        if raw[i] == "*" and (i + 1 >= len(raw) or raw[i + 1] != "*"):
            j = raw.find("*", i + 1)
            if j != -1 and (j + 1 >= len(raw) or raw[j + 1] != "*"):
                parts.append("<i>" + escape(raw[i + 1 : j]) + "</i>")
                i = j + 1
                continue
        # texto comum até próximo marcador
        nxt = len(raw)
        for marker in ("**", "*"):
            k = raw.find(marker, i)
            if k != -1:
                nxt = min(nxt, k)
        chunk = raw[i:nxt]
        chunk = escape(chunk)
        chunk = _soft_break_urls(chunk)
        parts.append(chunk)
        i = nxt
    return "".join(parts).replace("\n", "<br/>")


def _clean_inline(text: str) -> str:
    """Texto plano sem Markdown (para captions/headers simples)."""
    out = text.strip()
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"\*([^*]+)\*", r"\1", out)
    out = out.replace("`", "")
    out = out.replace("####", "")
    out = out.replace("&gt;", ">")
    out = out.replace("&lt;", "<")
    return out


_CELL_SEQ = 0


def _cell_style(font: str, size: float, leading: float, color=None) -> ParagraphStyle:
    global _CELL_SEQ
    _CELL_SEQ += 1
    return ParagraphStyle(
        f"boletim_cell_{_CELL_SEQ}",
        fontName=font,
        fontSize=size,
        leading=leading,
        textColor=color or colors.HexColor("#1A1A1A"),
        alignment=0,
        wordWrap="LTR",
        splitLongWords=0,
        spaceBefore=0,
        spaceAfter=0,
    )


def _col_widths(headers: list[str], usable: float) -> list[float]:
    weights = []
    for h in headers:
        hl = h.lower()
        if any(
            k in hl
            for k in (
                "interpreta",
                "evidência",
                "ação",
                "definição",
                "orientação",
                "leitura",
                "referência",
                "área",
                "articulação",
                "exposição",
                "tendência",
                "cobertura",
            )
        ):
            weights.append(3.0)
        elif any(k in hl for k in ("município", "regional", "indicador", "território", "fenômeno", "dimensão", "observado", "comunidade", "situação")):
            weights.append(1.55)
        elif any(k in hl for k in ("n.º", "nº", "aldeias")):
            weights.append(0.9)
        elif any(k in hl for k in ("unidade", "atual", "~7", "tmáx", "ur", "pm", "focos")):
            weights.append(0.75)
        elif any(k in hl for k in ("severidade", "início", "fim", "validade")):
            weights.append(1.15)
        else:
            weights.append(1.0)
    s = sum(weights) or 1.0
    widths = [usable * w / s for w in weights]
    for i, h in enumerate(headers):
        hl = h.lower()
        if "tendência" in hl:
            widths[i] = max(widths[i], 2.2 * cm)
        elif "situação" in hl:
            widths[i] = max(widths[i], 1.9 * cm)
        elif "cobertura" in hl:
            widths[i] = max(widths[i], 2.0 * cm)
        elif "unidade" in hl:
            widths[i] = max(widths[i], 1.5 * cm)
        elif "município" in hl:
            widths[i] = max(widths[i], 2.2 * cm)
    total = sum(widths)
    if total > usable:
        widths = [w * usable / total for w in widths]
    return widths


def _para_cell(text: str, style: ParagraphStyle) -> Paragraph:
    safe = _md_inline_to_rl(str(text or ""))
    safe = safe.replace("; ", ";<br/>").replace(" · ", "<br/>· ")
    return Paragraph(safe, style)


def _detect_glued_headers(headers: list[str]) -> list[str]:
    """Detecta cabecalhos colados do tipo Territorio/comunidadeMunicipio."""
    issues = []
    for h in headers:
        if re.search(r"Territ[oó]rio/comunidadeMunic", h, re.I):
            issues.append(f"celula_colada:{h}")
        if " " not in h and re.search(r"[a-záéíóúãõç]{4,}[A-ZÁÉÍÓÚÃÕÇ]", h):
            issues.append(f"celula_colada:{h}")
    return issues


def _table_to_flowable(rows: list[list[str]]):
    """Tabela Calibri 10 pt — sem hifenização; padding horizontal ampliado."""
    ncols = max(len(r) for r in rows)
    norm = [r + [""] * (ncols - len(r)) for r in rows]
    headers = [_clean_inline(c) for c in norm[0]]
    glued = _detect_glued_headers(headers)
    if glued:
        print("QA PDF: REPROVADO —", "; ".join(glued))

    usable_width = A4[0] - (2.0 * cm) - (2.0 * cm)
    col_widths = _col_widths(headers, usable_width)

    n_rows = len(norm)
    n_cols = ncols
    # Tabelas: Calibri 10 pt (mínimo; nunca abaixo)
    size = 10
    leading = size + 2.5

    head_style = _cell_style(FONT_BOLD, size, leading, SES_DEEP)
    body_style = _cell_style(FONT, size, leading)

    data = []
    for i, r in enumerate(norm):
        st = head_style if i == 0 else body_style
        data.append([_para_cell(c, st) for c in r])

    tbl = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SES_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), SES_DEEP),
                ("GRID", (0, 0), (-1, -1), 0.35, SES_GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SES_ROW_ALT]),
            ]
        )
    )
    if n_rows <= 10:
        return KeepTogether([tbl])
    return tbl


def _is_table_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|")


def _parse_table(lines: list[str], i: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    j = i
    while j < len(lines) and _is_table_line(lines[j]):
        row = [c.strip() for c in lines[j].strip()[1:-1].split("|")]
        rows.append(row)
        j += 1

    if len(rows) >= 2 and all(set(c) <= {"-", ":"} for c in rows[1]):
        rows.pop(1)
    return rows, j


def _image_flowable(src: Path, base: Path, caption: str = "") -> list:
    path = src if src.is_absolute() else (base / src)
    if not path.exists():
        return [Paragraph(f"[Figura indisponível: {path.name}]", ParagraphStyle("cap", fontName=FONT, fontSize=9))]
    usable_width = A4[0] - (2.0 * cm) - (2.0 * cm)
    img = Image(str(path))
    iw, ih = img.imageWidth, img.imageHeight
    if iw > usable_width:
        scale = usable_width / iw
        img.drawWidth = usable_width
        img.drawHeight = ih * scale
    flow = [img, Spacer(1, 0.15 * cm)]
    if caption and caption.lower() not in {"mapa 1", "mapa 2", "mapa 3", "figura 1", "figura 2"}:
        cap_style = ParagraphStyle("cap", fontName=FONT, fontSize=9, leading=11, textColor=colors.HexColor("#4A5568"))
        flow.append(Paragraph(_md_inline_to_rl(caption), cap_style))
    flow.append(Spacer(1, 0.25 * cm))
    return flow


def _norm_title(text: str) -> str:
    t = _clean_inline(text).lower()
    t = t.replace("×", "x").replace("–", "-").replace("—", "-")
    # remove acentos simples para match
    repl = str.maketrans("áàâãéêíóôõúç", "aaaaeeiooouc")
    return t.translate(repl).strip()


def _should_keep(title: str) -> bool:
    nt = _norm_title(title)
    for key in _KEEP_WITH_NEXT_TITLES:
        nk = _norm_title(key)
        if nk in nt or nt.startswith(nk) or nt in nk:
            return True
    if nt.startswith("mapa "):
        return True
    if nt.startswith("cenario:") or "cenario:" in nt:
        return True
    if "orientacoes operacionais" in nt:
        return True
    return False


def _qa_visible_markdown(pdf_text: str) -> list[str]:
    issues = []
    if re.search(r"\*[^*]+\*", pdf_text):
        issues.append("markdown_asteriscos_visiveis")
    if re.search(r"http\s*\n\s*s://", pdf_text) or re.search(r"http\s+s://", pdf_text):
        issues.append("url_quebrada_esquema")
    if re.search(r"\.sht\s*\n\s*ml", pdf_text, re.I):
        issues.append("url_quebrada_extensao")
    return issues


def build_pdf(src: Path = DEFAULT_SRC, out: Path = DEFAULT_OUT) -> Path:
    _register_calibri()
    text = src.read_text(encoding="utf-8")
    lines = text.splitlines()
    base_dir = src.parent

    doc_title = ""
    for line in lines:
        if line.startswith("# "):
            doc_title = _clean_inline(line[2:])
            break

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        fontName=FONT_BOLD,
        fontSize=18,
        leading=22,
        textColor=SES_BLUE,
        spaceAfter=8,
        keepWithNext=True,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName=FONT_BOLD,
        fontSize=14,
        leading=17,
        textColor=SES_DEEP,
        spaceBefore=8,
        spaceAfter=6,
        keepWithNext=True,
    )
    h3 = ParagraphStyle(
        "h3",
        parent=styles["Heading3"],
        fontName=FONT_BOLD,
        fontSize=12.5,
        leading=15,
        textColor=SES_BLUE,
        spaceBefore=6,
        spaceAfter=4,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontName=FONT,
        fontSize=11,
        leading=12.65,  # ~1.15
        alignment=4,  # TA_JUSTIFY
        spaceAfter=6,
        spaceBefore=0,
        splitLongWords=0,
    )
    bullet = ParagraphStyle("bullet", parent=body, leftIndent=12, bulletIndent=0, alignment=0)
    quote = ParagraphStyle(
        "quote",
        parent=body,
        leftIndent=14,
        textColor=colors.HexColor("#4A5568"),
        fontSize=10,
        leading=12,
        alignment=0,
    )
    note = ParagraphStyle(
        "note",
        parent=body,
        fontSize=9.5,
        leading=11.5,
        textColor=colors.HexColor("#4A5568"),
    )
    ref_style = ParagraphStyle(
        "ref",
        parent=body,
        fontSize=10,
        leading=11.5,  # entrelinha simples (~Calibri 10)
        spaceBefore=0,
        spaceAfter=2,
        splitLongWords=0,
    )

    story: list = []
    pending_keep: list | None = None

    def _flush_keep():
        nonlocal pending_keep
        if pending_keep:
            story.append(KeepTogether(pending_keep))
            pending_keep = None

    def _emit(flowables, *, force_keep: bool = False):
        nonlocal pending_keep
        if not isinstance(flowables, list):
            flowables = [flowables]
        if pending_keep is not None:
            pending_keep.extend(flowables)
            # fecha o grupo após conteúdo substancial
            if force_keep or any(not isinstance(f, Spacer) for f in flowables):
                _flush_keep()
            return
        story.extend(flowables)

    i = 0
    img_re = re.compile(r"^!\[(.*?)\]\((.*?)\)\s*$")
    while i < len(lines):
        raw = lines[i].rstrip()
        line = raw.strip()
        if not line:
            _emit(Spacer(1, 0.12 * cm))
            i += 1
            continue

        if line in {"---", "***", "___"}:
            _flush_keep()
            i += 1
            continue
        if line.startswith("####"):
            title = _clean_inline(line.lstrip("#").strip())
            p = Paragraph(_md_inline_to_rl(title), h3)
            if _should_keep(title):
                pending_keep = [p]
            else:
                _emit(p)
            i += 1
            continue

        if _is_table_line(raw):
            rows, i = _parse_table(lines, i)
            if rows:
                _emit(_table_to_flowable(rows), force_keep=True)
                _emit(Spacer(1, 0.25 * cm))
            continue

        m_img = img_re.match(line)
        if m_img:
            caption, img_src = m_img.group(1), m_img.group(2)
            _emit(_image_flowable(Path(img_src), base_dir, caption), force_keep=True)
            i += 1
            continue

        if line.startswith("# "):
            _flush_keep()
            _emit(Paragraph(_md_inline_to_rl(line[2:]), h1))
        elif line.startswith("## "):
            title = line[3:]
            p = Paragraph(_md_inline_to_rl(title), h2)
            if _should_keep(title):
                pending_keep = [p]
            else:
                _flush_keep()
                _emit(p)
        elif line.startswith("### "):
            title = line[4:]
            p = Paragraph(_md_inline_to_rl(title), h3)
            if _should_keep(title):
                pending_keep = [p]
            else:
                _flush_keep()
                _emit(p)
        elif line.startswith("- "):
            _emit(Paragraph(_md_inline_to_rl(line[2:]), bullet, bulletText="•"), force_keep=True)
        elif re.match(r"^\d+\.\s+", line):
            text_item = re.sub(r"^\d+\.\s+", "", line)
            _emit(Paragraph(_md_inline_to_rl(text_item), bullet), force_keep=True)
        elif line.startswith("> "):
            _emit(Paragraph(_md_inline_to_rl(line[2:]), quote), force_keep=True)
        elif line.startswith("_") and line.endswith("_") and not line.startswith("__"):
            _emit(Paragraph(_md_inline_to_rl(line.strip("_")), note), force_keep=True)
        elif line.startswith("http") or re.match(r"^\[\d+\]", line) or "Disponível em:" in line:
            _emit(Paragraph(_md_inline_to_rl(line), ref_style), force_keep=True)
        elif re.match(r"^\*\*Mapa\s+\d+", line) or re.match(r"^Mapa\s+\d+", _clean_inline(line)):
            title = _clean_inline(line)
            p = Paragraph(_md_inline_to_rl(line), h3 if line.startswith("###") else body)
            # títulos de mapa/figura devem ficar com a imagem seguinte
            pending_keep = [Paragraph(_md_inline_to_rl(line), body)]
        else:
            _emit(Paragraph(_md_inline_to_rl(line), body), force_keep=True)
        i += 1

    _flush_keep()

    # QA Markdown residual no MD fonte
    md_star = re.findall(r"(?<!\*)\*(?!\*)([^*\n]+)\*(?!\*)", text)
    # asteriscos restantes após conversão esperada no PDF — checado pós-render se possível
    if any("Estado" in m or "Regionais" in m or "Referências" in m for m in md_star):
        print("QA: trechos com *itálico* Markdown serão renderizados como itálico real.")

    out.parent.mkdir(parents=True, exist_ok=True)
    on_first, on_later = page_callbacks(doc_title="")
    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=CONTENT_TOP_MARGIN,
        bottomMargin=CONTENT_BOTTOM_MARGIN,
        title=doc_title or "Boletim El Niño",
        author="CIEVS · SES-MT",
    )
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)

    # QA pós-PDF: asteriscos visíveis / URLs
    try:
        import fitz

        pdf = fitz.open(str(out))
        full = "\n".join(page.get_text() for page in pdf)
        for issue in _qa_visible_markdown(full):
            print("QA PDF: REPROVADO —", issue)
        # colisões tipo Território/comunidadeMunicípio
        if re.search(r"Territ[oó]rio/comunidadeMunic[ií]pio", full):
            print("QA PDF: REPROVADO — cabecalho_colado_territorio")
    except Exception as exc:  # noqa: BLE001
        print("QA PDF: inspeção de texto indisponível:", exc)

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera PDF apresentável do boletim El Niño (padrão SES-MT).")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="Markdown de origem")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="PDF de saída")
    parser.add_argument("--render-pages", action="store_true", help="Exporta PNG de cada página para inspeção visual")
    args = parser.parse_args()
    path = build_pdf(args.src, args.out)
    print(path)
    if args.render_pages:
        out_dir = path.with_suffix("").as_posix() + "_pages"
        n = _render_pages(path, Path(out_dir))
        print(f"Páginas renderizadas: {n} em {out_dir}")
    return 0


def _render_pages(pdf_path: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        import fitz
    except ImportError:
        print("PyMuPDF (fitz) indisponível — instale para inspeção visual.")
        return 0
    doc = fitz.open(str(pdf_path))
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(dpi=120)
        pix.save(str(dest / f"pagina_{i:02d}.png"))
    return len(doc)


if __name__ == "__main__":
    raise SystemExit(main())
