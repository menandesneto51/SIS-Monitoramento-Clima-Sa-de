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
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from sisclima.reporting.institutional_pdf import (
    CONTENT_BOTTOM_MARGIN,
    CONTENT_TOP_MARGIN,
    page_callbacks,
    register_institutional_fonts,
)

DEFAULT_SRC = ROOT / "docs" / "apresentacoes" / "Boletim_ElNino_SE_34-2026.md"
DEFAULT_OUT = ROOT / "docs" / "apresentacoes" / "Boletim_ElNino_SE_34-2026_apresentavel.pdf"
# Nome institucional (Sala). O gerador também grava uma cópia com este padrão.
DEFAULT_OUT_SALA = (
    ROOT
    / "docs"
    / "apresentacoes"
    / "Boletim Informativo Sala de Situação MT El Niño SE 34-2026.pdf"
)

SES_BLUE = colors.HexColor("#1351B4")
SES_DEEP = colors.HexColor("#1D357F")
SES_HEADER_BG = colors.HexColor("#E8EEF9")
SES_ROW_ALT = colors.HexColor("#F7F9FC")
SES_GRID = colors.HexColor("#C8D2E6")

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


class TableNoOrphanStart(Table):
    """Recusa o primeiro fragmento se não couber cabeçalho + 3 linhas de dados."""

    MIN_DATA_ROWS = 3

    def split(self, availWidth, availHeight):
        self.wrap(availWidth, availHeight)
        rh = list(getattr(self, "_rowHeights", None) or [])
        if not rh:
            return Table.split(self, availWidth, availHeight)
        total_h = float(sum(rh))
        if total_h <= availHeight + 0.5:
            return []
        min_rows = 1 + min(self.MIN_DATA_ROWS, max(0, len(rh) - 1))
        need = float(sum(rh[:min_rows])) + 2
        if availHeight < need:
            return []
        parts = Table.split(self, availWidth, availHeight)
        if not parts:
            return []
        first = parts[0]
        n_first = 0
        if getattr(first, "_cellvalues", None):
            n_first = len(first._cellvalues)
        elif getattr(first, "_argW", None) is not None and hasattr(first, "_cellvalues"):
            n_first = len(first._cellvalues)
        else:
            try:
                n_first = len(first._cellvalues)  # type: ignore[attr-defined]
            except Exception:
                n_first = min_rows
        if n_first and n_first < min_rows and len(rh) > min_rows:
            return []
        return parts


class NoSplitParagraph(Paragraph):
    """Parágrafo inteiro: não parte frase entre páginas (equivalente a break-inside: avoid)."""

    def split(self, availWidth, availHeight):
        return []


class CaptionAndTable(Flowable):
    """Título + tabela: só inicia se couber título + cabeçalho + 3 linhas; senão vai inteira."""

    MIN_DATA_ROWS = 3

    def __init__(self, caption, table):
        super().__init__()
        self.caption = caption
        self.table = table
        self._ch = 0
        self._th = 0

    def wrap(self, availWidth, availHeight):
        _, self._ch = self.caption.wrap(availWidth, availHeight)
        _tw, self._th = self.table.wrap(availWidth, max(1.0, float(availHeight) - self._ch))
        self.width = availWidth
        self.height = self._ch + self._th
        return self.width, self.height

    def _min_first_height(self) -> float:
        rh = list(getattr(self.table, "_rowHeights", None) or [])
        if not rh:
            return self._ch + 40
        n = 1 + min(self.MIN_DATA_ROWS, max(0, len(rh) - 1))
        return self._ch + float(sum(rh[:n])) + 2

    def split(self, availWidth, availHeight):
        self.wrap(availWidth, availHeight)
        if float(availHeight) < self._min_first_height():
            return []
        if self.height <= float(availHeight) + 0.5:
            return []
        remain = float(availHeight) - self._ch
        parts = self.table.split(availWidth, remain)
        if not parts:
            return []
        return [CaptionAndTable(self.caption, parts[0]), *parts[1:]]

    def draw(self):
        self.caption.drawOn(self.canv, 0, self.height - self._ch)
        self.table.drawOn(self.canv, 0, 0)


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
    "como a classe projetada e calculada",
    "13. preparacao assistencial e farmaceutica",
    "13. preparacao assistencial e farmaceutica - estoques estrategicos",
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
                    out.append("\u200b")  # quebra visual após /, sem fragmentar o hyperlink
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
    raw = raw.replace("●", "•").replace("○", "◦")
    raw = raw.replace("^", "↑")
    raw = re.sub(r"(?<![A-Za-z])v(?=\s|\d)", "↓", raw)
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
                "limiar",
            )
        ):
            weights.append(3.0)
        elif any(k in hl for k in ("município", "regional", "indicador", "território", "fenômeno", "dimensão", "observado", "comunidade", "situação")):
            weights.append(1.55)
        elif any(k in hl for k in ("n.º", "nº", "aldeias")):
            weights.append(0.9)
        elif any(k in hl for k in ("p90 aps", "máx. aps", "max. aps", "máx. hospital", "max. hospital")):
            weights.append(1.2)
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
        elif any(k in hl for k in ("p90 aps", "máx. aps", "máx. hospital")):
            widths[i] = max(widths[i], 2.55 * cm)
    total = sum(widths)
    if total > usable:
        widths = [w * usable / total for w in widths]
    return widths


def _para_cell(text: str, style: ParagraphStyle, *, header: bool = False) -> Paragraph:
    safe = _md_inline_to_rl(str(text or ""))
    if not header:
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

    n_cols = ncols
    compact = any(
        k in " ".join(headers).lower()
        for k in ("componente", "limiares", "termo", "definição", "driver do modelo", "contexto concomitante")
    )
    gloss = any("termo" == h.strip().lower() for h in headers) or (
        "definição" in " ".join(headers).lower() and "termo" in " ".join(headers).lower()
    )
    size = 9.5 if compact or gloss else 10
    leading = size + 2.4

    head_style = _cell_style(FONT_BOLD, size, leading, SES_DEEP)
    body_style = _cell_style(FONT, size, leading)

    data = []
    for i, r in enumerate(norm):
        st = head_style if i == 0 else body_style
        data.append([_para_cell(c, st, header=(i == 0)) for c in r])

    pad_y = 3.5 if gloss else (2 if compact else 4)
    pad_x = 5 if compact or gloss else 7
    if compact:
        tbl = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
    else:
        tbl = TableNoOrphanStart(data, colWidths=col_widths, repeatRows=1, splitByRow=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SES_HEADER_BG),
                ("TEXTCOLOR", (0, 0), (-1, 0), SES_DEEP),
                ("GRID", (0, 0), (-1, -1), 0.35, SES_GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), pad_x),
                ("RIGHTPADDING", (0, 0), (-1, -1), pad_x),
                ("TOPPADDING", (0, 0), (-1, -1), pad_y),
                ("BOTTOMPADDING", (0, 0), (-1, -1), pad_y),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SES_ROW_ALT]),
            ]
        )
    )
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
    max_h = 13.6 * cm  # mapas ocupam a largura útil sem deixar faixa em branco
    img = Image(str(path))
    iw, ih = img.imageWidth, img.imageHeight
    scale = min(usable_width / iw if iw else 1, max_h / ih if ih else 1, 1.0)
    img.drawWidth = iw * scale
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
    """Blocos que nao podem orfaos: glossario, mapas, impactos, saude do trabalhador."""
    nt = _norm_title(title)
    if not nt:
        return False
    if "notas metodologicas" in nt:
        return False
    if "como a classe" in nt or nt == "glossario":
        return True
    if "leitura epidemiologica" in nt or "leitura regional" in nt:
        return True
    if nt.startswith("mapa "):
        return True
    if nt.startswith("10.") and "impactos" in nt:
        return True
    if "saude do trabalhador" in nt:
        return True
    if nt.startswith("4.") and "situacao atual" in nt:
        return True
    return False


def _qa_paginacao(pdf) -> list[str]:
    """Bloqueadores de paginacao V9."""
    issues: list[str] = []
    pages = [(page.get_text() or "") for page in pdf]
    n = len(pages)

    def _body_lines(t: str) -> list[str]:
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        skip = {
            "Desenvolvido pelo CIEVS · SES-MT",
            "ARARAS MT — Clima, ambiente e saúde em uma só visão.",
            "Ferramenta de apoio à gestão. Validar no painel e no território antes da comunicação oficial.",
            "saude.mt.gov.br",
        }
        out = []
        for ln in lines:
            if ln in skip or ln.startswith("Página ") or "Governo de Mato Grosso" in ln:
                continue
            out.append(ln)
        return out

    def _last_line(t: str) -> str:
        body = _body_lines(t)
        return body[-1] if body else ""

    def _first_line(t: str) -> str:
        body = _body_lines(t)
        return body[0] if body else ""

    gloss_p = [i for i, t in enumerate(pages) if re.search(r"\bGlossário\b", t)]
    tab9_p = [i for i, t in enumerate(pages) if "Tabela 9" in t]
    if gloss_p and tab9_p and gloss_p[0] != tab9_p[0]:
        issues.append(f"GLOSSARY_TITLE_ORPHAN p{gloss_p[0]+1}")
    conc_p = [i for i, t in enumerate(pages) if "17. Conclusão e tendência" in t]
    if conc_p and gloss_p and conc_p[0] < gloss_p[0]:
        issues.append(f"GLOSSARY_TITLE_ORPHAN conclusao_antes_do_glossario p{conc_p[0]+1}")

    for i in range(n - 1):
        last = _last_line(pages[i])
        first = _first_line(pages[i + 1])
        if last and first:
            if re.search(r"(somente rotas já|já)$", last, re.I) and re.match(r"^validadas", first, re.I):
                issues.append(f"PARAGRAPH_ORPHAN p{i+1}-{i+2}")
            elif last[-1:].isalpha() and last[-1].islower() and first[:1].islower() and len(last) > 50:
                issues.append(f"PARAGRAPH_ORPHAN p{i+1}-{i+2}")
            if re.match(
                r"^(Leitura epidemiológica|Glossário|10\. Impactos|11\.4 |12\. Orientações|Grupos ocupacionais|Saúde do Trabalhador)",
                last,
                re.I,
            ):
                issues.append(f"HEADING_WITHOUT_BODY p{i+1}")
                issues.append(f"HEADING_ORPHAN p{i+1}")
            if re.match(r"^Tabela\s+\d+", last, re.I) and re.match(
                r"^(Município|Componente|Termo|Regional|Driver)", first, re.I
            ):
                issues.append(f"TABLE_SINGLE_ROW_BEFORE_BREAK p{i+1}")
            if last.startswith("•") and first.startswith("•"):
                prev_bullets = [ln for ln in pages[i].splitlines() if ln.strip().startswith("•")]
                if len(prev_bullets) == 1:
                    issues.append(f"LIST_SINGLE_ITEM_CONTINUATION p{i+1}")
            if re.match(r"^Fonte:", first, re.I) and (
                re.search(r"Mapa\s+\d", last, re.I)
                or "certificadas em Mato Grosso" in last
            ):
                issues.append(f"MAP_SOURCE_SEPARATED_FROM_MAP p{i+1}-{i+2}")
            if re.match(r"^Fonte:", first, re.I) and "Tabela 7" in pages[i] and "Fonte:" not in pages[i]:
                issues.append(f"TABLE_SOURCE_SEPARATED Tabela7 p{i+1}-{i+2}")
            if re.search(
                r"(CIEVS-MT|Atenção à Saúde|Assistência Farmacêutica|24 a 48 horas|24–48|Vigidesastres|SEMA-MT)",
                last,
                re.I,
            ) and first.startswith("• Território"):
                issues.append(f"ACTION_BLOCK_SPLIT p{i+1}-{i+2}")
            if re.match(
                r"^(UNIEVS|Atenção à Saúde|Assistência Farmacêutica|Comunicação|Vigilância|Vigidesastres)",
                last,
                re.I,
            ) and first.startswith("•"):
                issues.append(f"ACTION_BLOCK_SPLIT p{i+1}-{i+2}")
            if re.search(r"tabela abaixo", last, re.I) and re.match(
                r"^(Município|Regional|Tabela\s+7)", first, re.I
            ):
                issues.append(f"TABLE_INTRO_ORPHAN p{i+1}-{i+2}")

    for i, t in enumerate(pages):
        if "Mapa 1" in t and "Classificação integrada" in t:
            if "Fonte:" not in t or "Atual." not in t:
                if i + 1 < n and re.match(r"^Fonte:", _first_line(pages[i + 1]), re.I):
                    issues.append(f"MAP_SOURCE_SEPARATED_FROM_MAP Mapa1 p{i+1}-{i+2}")
                elif "Fonte:" not in t:
                    issues.append(f"MAP_SOURCE_SEPARATED_FROM_MAP Mapa1 p{i+1}")
        if "Tabela 7" in t and "Fonte:" not in t:
            if i + 1 < n and "Fonte:" in pages[i + 1] and "Tabela 7" not in pages[i + 1]:
                issues.append(f"TABLE_SOURCE_SEPARATED Tabela7 p{i+1}-{i+2}")

    full = "\n".join(pages)
    if re.search(r"(?<![0-9.,])1 avisos\b", full, re.I):
        issues.append("SINGULAR_PLURAL_ERROR 1 avisos")
    if re.search(r"(?<![0-9.,])1 municípios\b", full, re.I):
        issues.append("SINGULAR_PLURAL_ERROR 1 municípios")
    if re.search(r"Baixa umidade presente", full, re.I) and re.search(
        r"Umidade relativa[^\n]{0,80}0 município", full, re.I
    ):
        issues.append("ZERO_VALUE_INTERPRETED_AS_PRESENCE umidade")

    t2 = [i for i, t in enumerate(pages) if "Tabela 2" in t]
    t3 = [i for i, t in enumerate(pages) if "Tabela 3" in t]
    if t2 and t3 and t2[0] != t3[0]:
        issues.append(f"TABLE_SINGLE_ROW_BEFORE_BREAK Tabela2/3 p{t2[0]+1}-{t3[0]+1}")

    compact = re.sub(r"\s+", " ", full)
    if "P90 APS (km)" not in compact and "P90 APS (km)" not in full:
        if not re.search(r"P90\s*APS\s*\(km\)", compact):
            issues.append("TABLE_UNIT_MISSING Tabela 7")
    if not re.search(r"Máx\.\s*APS\s*\(km\)", compact):
        issues.append("TABLE_UNIT_MISSING Tabela 7")
    if not re.search(r"Máx\.\s*hospital\s*\(km\)", compact):
        issues.append("TABLE_UNIT_MISSING Tabela 7")
    if "≥34 °C → 25" not in compact and "≥34 °C →25" in compact:
        issues.append("TABLE_UNIT_MISSING Tabela 8")
    if "ver tabela abaixo" in full.lower():
        issues.append("SECTION_SEQUENCE_ERROR hidro_tabela_inexistente")
    heads = re.findall(r"11\.([1-5]) ", full)
    if heads:
        seen: list[int] = []
        for x in heads:
            v = int(x)
            if v not in seen:
                seen.append(v)
        if seen != [1, 2, 3, 4, 5]:
            issues.append("SECTION_SEQUENCE_ERROR 11.x")
    return issues


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
        fontSize=16,
        leading=19,
        textColor=SES_BLUE,
        spaceAfter=4,
        keepWithNext=True,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName=FONT_BOLD,
        fontSize=14,
        leading=17,
        textColor=SES_DEEP,
        spaceBefore=6,
        spaceAfter=4,
        keepWithNext=True,
    )
    h3 = ParagraphStyle(
        "h3",
        parent=styles["Heading3"],
        fontName=FONT_BOLD,
        fontSize=12.5,
        leading=15,
        textColor=SES_BLUE,
        spaceBefore=4,
        spaceAfter=3,
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
    tbl_cap = ParagraphStyle(
        "tbl_cap",
        parent=body,
        fontName=FONT_BOLD,
        fontSize=11,
        leading=13,
        spaceAfter=3,
        spaceBefore=4,
        keepWithNext=True,
        alignment=0,
    )
    ref_style = ParagraphStyle(
        "ref",
        parent=body,
        fontSize=9.5,
        leading=10.0,  # ~1,05
        spaceBefore=0,
        spaceAfter=3,
        splitLongWords=0,
    )

    gloss_h = ParagraphStyle(
        "gloss_h",
        parent=h3,
        spaceBefore=2,
        spaceAfter=2,
        keepWithNext=True,
    )

    story: list = []
    pending_keep: list | None = None
    hold_flush = False
    close_on_fonte = False
    t2t3: list | None = None
    last_tbl_n: int | None = None

    def _flush_t2t3():
        nonlocal t2t3, last_tbl_n
        if t2t3:
            story.append(KeepTogether(t2t3))
            t2t3 = None
        last_tbl_n = None

    def _flush_keep():
        nonlocal pending_keep, hold_flush
        if pending_keep:
            dest = t2t3 if t2t3 is not None else story
            dest.append(KeepTogether(pending_keep))
            pending_keep = None
        hold_flush = False

    def _dest_append(items: list):
        if t2t3 is not None:
            t2t3.extend(items)
        else:
            story.extend(items)

    def _emit(flowables, *, force_keep: bool = False, huge: bool = False):
        nonlocal pending_keep
        if not isinstance(flowables, list):
            flowables = [flowables]
        if pending_keep is not None:
            if huge:
                _flush_keep()
                _dest_append(flowables)
                return
            pending_keep.extend(flowables)
            extra = [f for f in pending_keep[1:] if not isinstance(f, Spacer)]
            if force_keep or (len(extra) >= 2 and not hold_flush):
                _flush_keep()
            return
        _dest_append(flowables)

    i = 0
    img_re = re.compile(r"^!\[(.*?)\]\((.*?)\)\s*$")
    while i < len(lines):
        raw = lines[i].rstrip()
        line = raw.strip()
        if not line:
            if pending_keep is not None:
                pending_keep.append(Spacer(1, 0.08 * cm))
            elif t2t3 is not None:
                t2t3.append(Spacer(1, 0.08 * cm))
            else:
                last = story[-1] if story else None
                st = getattr(last, "style", None)
                if st is not None and getattr(st, "keepWithNext", False):
                    pass
                else:
                    story.append(Spacer(1, 0.12 * cm))
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
                tbl = _table_to_flowable(rows)
                if pending_keep is not None:
                    cap = pending_keep.pop() if pending_keep and isinstance(pending_keep[-1], Paragraph) else None
                    rest = list(pending_keep)
                    pending_keep = None
                    block = rest
                    block.append(CaptionAndTable(cap, tbl) if cap is not None else tbl)
                    if close_on_fonte:
                        pending_keep = block
                        hold_flush = True
                    elif len(block) > 1:
                        _dest_append([KeepTogether(block)])
                    else:
                        _dest_append(block)
                elif t2t3 is not None and t2t3 and isinstance(t2t3[-1], Paragraph):
                    cap = t2t3.pop()
                    t2t3.append(CaptionAndTable(cap, tbl))
                else:
                    _dest_append([tbl])
                if pending_keep is None:
                    _dest_append([Spacer(1, 0.10 * cm)])
            continue

        m_img = img_re.match(line)
        if m_img:
            caption, img_src = m_img.group(1), m_img.group(2)
            _emit(_image_flowable(Path(img_src), base_dir, caption), force_keep=True)
            i += 1
            continue

        if line.startswith("# "):
            _flush_keep()
            _flush_t2t3()
            _emit(Paragraph(_md_inline_to_rl(line[2:]), h1))
        elif line.startswith("## "):
            title = line[3:]
            _flush_keep()
            nt = _norm_title(title)
            if nt.startswith("17.") or "conclusao e tendencia" in nt:
                _flush_t2t3()
                story.append(PageBreak())
            elif not nt.startswith("10."):
                _flush_t2t3()
            p = Paragraph(_md_inline_to_rl(title), h2)
            if nt.startswith("11.") and "priorizacao territorial" in nt:
                pending_keep = [p]
                hold_flush = True
            elif nt.startswith("10.") and "impactos" in nt:
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif nt.startswith("4.") and "situacao atual" in nt:
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif nt.startswith("6.") and "mapa" in nt:
                story.append(CondPageBreak(12 * cm))
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif nt.startswith("12.") and "orientacoes" in nt:
                story.append(CondPageBreak(6 * cm))
                pending_keep = [p]
                hold_flush = True
            elif _should_keep(title):
                pending_keep = [p]
            else:
                _emit(p)
        elif line.startswith("### "):
            title = line[4:]
            p = Paragraph(_md_inline_to_rl(title), h3)
            nt = _norm_title(title)
            if nt.startswith("a. drivers"):
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif nt.startswith("11.1"):
                if pending_keep is None:
                    pending_keep = [p]
                else:
                    pending_keep.append(p)
                hold_flush = True
            elif nt.startswith("b. contexto") and t2t3 is not None:
                t2t3.append(p)
            elif nt.startswith("b. contexto") and pending_keep is not None and hold_flush:
                pending_keep.append(p)
            elif "articulacoes intersetoriais" in nt:
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif any(
                k in nt
                for k in (
                    "24 a 48 horas",
                    "ate a proxima sala",
                    "até a próxima sala",
                    "proximas semanas",
                    "próximas semanas",
                )
            ):
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif "geolocalizacao" in nt or "geolocalização" in nt.lower():
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif nt.startswith("11.4"):
                _flush_keep()
                pending_keep = [p]
            elif "como a classe" in nt:
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = True
            elif _should_keep(title):
                _flush_keep()
                pending_keep = [p]
            else:
                _flush_keep()
                _emit(p)
        elif re.match(r"^\*\*CEN[ÁA]RIO", line, re.I):
            p = Paragraph(_md_inline_to_rl(line), h3)
            if pending_keep is not None and hold_flush:
                pending_keep.append(p)
            else:
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
            close_on_fonte = False
        elif re.match(r"^\*\*Municípios com aldeias", line, re.I) or re.match(
            r"^\*\*Comunidades quilombolas", line, re.I
        ):
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(_clean_inline(line)), h3)]
            hold_flush = True
            close_on_fonte = False
        elif line.startswith("- "):
            blocos = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                blocos.append(
                    NoSplitParagraph(_md_inline_to_rl(lines[i].strip()[2:]), bullet, bulletText="•")
                )
                i += 1
            if pending_keep is not None and hold_flush:
                pending_keep.extend(blocos)
            elif len(blocos) <= 8:
                _emit(KeepTogether(blocos), force_keep=True)
            else:
                for b in blocos:
                    _emit(b, force_keep=True)
            continue
        elif re.match(r"^\d+\.\s+", line):
            text_item = re.sub(r"^\d+\.\s+", "", line)
            _emit(NoSplitParagraph(_md_inline_to_rl(text_item), bullet), force_keep=True)
        elif line.startswith("> "):
            _emit(NoSplitParagraph(_md_inline_to_rl(line[2:]), quote), force_keep=True)
        elif line.startswith("_") and line.endswith("_") and not line.startswith("__"):
            _emit(NoSplitParagraph(_md_inline_to_rl(line.strip("_")), note), force_keep=True)
        elif line.startswith("http") or re.match(r"^\[\d+\]", line) or "Disponível em:" in line:
            _emit(Paragraph(_md_inline_to_rl(line), ref_style), force_keep=True)
        elif re.match(r"^\*\*Tabela\s+\d+", line):
            m_tn = re.match(r"^\*\*Tabela\s+(\d+)", line)
            n_tbl = int(m_tn.group(1)) if m_tn else 0
            p = Paragraph(_md_inline_to_rl(line), tbl_cap)
            if n_tbl == 2:
                _flush_keep()
                t2t3 = [p]
                last_tbl_n = 2
            elif n_tbl == 3 and t2t3 is not None:
                t2t3.append(p)
                last_tbl_n = 3
            elif n_tbl == 1:
                # secao 4: anexar ao keep do titulo ## 4, se existir
                if pending_keep is None:
                    pending_keep = [p]
                else:
                    pending_keep.append(p)
                hold_flush = True
                close_on_fonte = True
            elif n_tbl == 7:
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = True
            elif n_tbl == 4:
                # secao 10: manter com titulo
                if pending_keep is None:
                    pending_keep = [p]
                else:
                    pending_keep.append(p)
                hold_flush = True
                close_on_fonte = True
            elif pending_keep is not None:
                pending_keep.append(p)
            else:
                pending_keep = [p]
        elif _clean_inline(line).lower() in {"glossário", "glossario"}:
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(_clean_inline(line)), gloss_h)]
            hold_flush = True
            close_on_fonte = True
        elif re.match(r"^Fonte:", line, re.I):
            note_p = Paragraph(_md_inline_to_rl(line), note)
            if t2t3 is not None:
                t2t3.append(note_p)
                if last_tbl_n == 3:
                    _flush_t2t3()
            elif pending_keep is not None and hold_flush:
                pending_keep.append(note_p)
                if close_on_fonte:
                    # Tabelas 1/4/7: fecha apos Fonte; Nota/Leitura ainda podem entrar
                    close_on_fonte = False
            else:
                _emit(note_p, force_keep=True)
                close_on_fonte = False
        elif re.match(r"^Nota:", line, re.I):
            np = NoSplitParagraph(_md_inline_to_rl(line), note)
            if pending_keep is not None and hold_flush:
                pending_keep.append(np)
            else:
                _emit(np, force_keep=True)
        elif re.match(r"^\*\*Mapa\s+\d+", line) or re.match(r"^Mapa\s+\d+", _clean_inline(line)):
            _flush_keep()
            p = Paragraph(_md_inline_to_rl(line), body)
            # Mapa 1: bloco indivisivel (titulo + imagem + Fonte + Nota + Atual/Projecao/Agravamento)
            if re.search(r"Mapa\s+1\b", _clean_inline(line), re.I):
                story.append(CondPageBreak(12 * cm))
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = False
            elif re.search(r"Mapa\s+3\b", _clean_inline(line), re.I):
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = True
            else:
                pending_keep = [p]
                hold_flush = True
                close_on_fonte = True
        elif re.match(r"^\*\*Leitura epidemiol", line, re.I) or _clean_inline(line).lower() == "leitura epidemiologica":
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(_clean_inline(line)), h3)]
            hold_flush = True
        elif _clean_inline(line).startswith("O que isso significa"):
            _flush_keep()
            _emit(NoSplitParagraph(_md_inline_to_rl(line), body), force_keep=False)
        elif re.match(r"^\*\*Mapa\s+2", line) or (
            re.match(r"^Mapa\s+2", _clean_inline(line))
        ):
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(line), body)]
            hold_flush = True
            close_on_fonte = True
        elif re.match(r"^\*\*Saúde do Trabalhador", line, re.I) or re.match(
            r"^Saúde do Trabalhador", _clean_inline(line), re.I
        ):
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(line), h3)]
            hold_flush = True
            close_on_fonte = False
        elif re.match(r"^\*\*Leitura regional", line, re.I) or _clean_inline(line).lower().startswith(
            "leitura regional"
        ):
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(line), body)]
            hold_flush = True
        elif re.match(r"^(24 a 48 horas|Esta semana|Até a próxima Sala|Ate a proxima Sala)", _clean_inline(line), re.I):
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(line), h3)]
            hold_flush = True
        elif (
            line.startswith("**")
            and line.endswith("**")
            and any(
                k in line
                for k in (
                    "UNIEVS",
                    "CIEVS",
                    "Atenção à Saúde",
                    "Assistência Farmacêutica",
                    "Comunicação",
                    "Vigilância",
                    "Gestão Regional",
                    "COSEMS",
                )
            )
        ):
            p = Paragraph(_md_inline_to_rl(line), body)
            if pending_keep is not None and hold_flush:
                pending_keep.append(p)
            else:
                _flush_keep()
                pending_keep = [p]
                hold_flush = True
        elif re.match(r"^\*\*Geolocalização", line, re.I):
            _flush_keep()
            pending_keep = [Paragraph(_md_inline_to_rl(line), h3)]
            hold_flush = True
            close_on_fonte = True
        else:
            p = NoSplitParagraph(_md_inline_to_rl(line), body)
            if line.startswith("**Leitura combinada") or line.startswith("**Grupos ocupacionais"):
                if pending_keep is not None:
                    pending_keep.append(p)
                    # manter Fonte/Nota/Leitura da Tabela 7 juntos
                    hold_flush = True
                else:
                    pending_keep = [p]
                    hold_flush = True
            elif re.match(r"^\*\*(Atual|Projeção|Projecao|Agravamento)\.", line, re.I):
                if pending_keep is not None:
                    pending_keep.append(p)
                    if re.match(r"^\*\*Agravamento", line, re.I):
                        _flush_keep()
                else:
                    _emit(p, force_keep=True)
            elif pending_keep is not None and hold_flush and (
                line.startswith("Municípios com dados")
                or line.startswith("Nota:")
                or line.startswith("Associação temporal")
                or line.startswith("O Mapa 3 localiza")
            ):
                pending_keep.append(p)
                if line.startswith("Associação temporal"):
                    # secao 10: titulo + frase; tabela entra no keep via close_on_fonte
                    pass
            else:
                _emit(p, force_keep=False)
        i += 1

    _flush_keep()
    _flush_t2t3()

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
        print(f"QA PDF: páginas={len(pdf)}")
        comps = ("Intensidade", "Estresse térmico", "Persistência", "Onda de calor")
        for i, page in enumerate(pdf, start=1):
            t = page.get_text() or ""
            if "Tabela" in t and "Componentes do risco térmico" in t:
                hits = [c for c in comps if c in t]
                if len(hits) != 4:
                    print(f"QA PDF: TABLE_SPLIT_ERROR metodologia p{i}")
                break
        content_h = A4[1] - CONTENT_TOP_MARGIN - CONTENT_BOTTOM_MARGIN
        for i, page in enumerate(pdf, start=1):
            blocks = page.get_text("blocks") or []
            if not blocks:
                print(f"QA PDF: PAGE_UNDERFILLED p{i}")
                continue
            ys = [b[1] for b in blocks]
            ye = [b[3] for b in blocks]
            used = max(ye) - min(ys)
            if i < len(pdf) and used < 0.45 * content_h:
                print(f"QA PDF: PAGE_UNDERFILLED p{i} used={used:.0f}")
            text = page.get_text() or ""
            if i < len(pdf) and len(text.strip()) < 180 and not page.get_images():
                print(f"QA PDF: ORPHAN_TEXT p{i}")
            if re.search(r"\bSAF\b", text):
                print(f"QA PDF: ACRONYM_FIRST_USE_ERROR SAF p{i}")
            if re.search(r"ROUTE_|MODEL_SATURATION_WARNING|SCORE_CLIPPING_WARNING|DRIVER_REDUNDANCY_WARNING|RISCO_TÉRMICO_PROJETADO", text):
                print(f"QA PDF: INTERNAL_TECH_TERM p{i}")
            if "Mato Grosso do Sul (MS)" in text or "estabilidade (sem previsão" in text:
                print(f"QA PDF: INTERNAL_TECH_TERM p{i}")
            if "9 municípios no recorte hidrológico" in text or "não há evidência municipal suficiente" in text.lower():
                print(f"QA PDF: HYDRO_TOTAL_ERROR p{i}")
        pag = _qa_paginacao(pdf)
        flags = {
            "TABLE_SINGLE_ROW_BEFORE_BREAK": any("TABLE_SINGLE_ROW" in x for x in pag),
            "HEADING_ORPHAN": any("HEADING_ORPHAN" in x for x in pag),
            "HEADING_WITHOUT_BODY": any("HEADING_WITHOUT_BODY" in x for x in pag),
            "PARAGRAPH_ORPHAN": any("PARAGRAPH_ORPHAN" in x for x in pag),
            "GLOSSARY_TITLE_ORPHAN": any("GLOSSARY_TITLE_ORPHAN" in x for x in pag),
            "LIST_SINGLE_ITEM_CONTINUATION": any("LIST_SINGLE_ITEM" in x for x in pag),
            "SECTION_SEQUENCE_ERROR": any("SECTION_SEQUENCE" in x for x in pag),
            "TABLE_UNIT_MISSING": any("TABLE_UNIT_MISSING" in x for x in pag),
            "MAP_SOURCE_SEPARATED_FROM_MAP": any("MAP_SOURCE_SEPARATED" in x for x in pag),
            "TABLE_SOURCE_SEPARATED": any("TABLE_SOURCE_SEPARATED" in x for x in pag),
            "ACTION_OWNER_ORPHAN": any("ACTION_OWNER_ORPHAN" in x for x in pag),
            "SINGULAR_PLURAL_ERROR": any("SINGULAR_PLURAL" in x for x in pag),
            "ZERO_VALUE_INTERPRETED_AS_PRESENCE": any("ZERO_VALUE_INTERPRETED" in x for x in pag),
        }
        for name, bad in flags.items():
            print(f"QA PDF: {name} = {1 if bad else 0}")
        for issue in pag:
            print("QA PDF: REPROVADO —", issue)
        gloss_pages = [i for i, page in enumerate(pdf, start=1) if "Glossário" in (page.get_text() or "")]
        tab9_pages = [i for i, page in enumerate(pdf, start=1) if "Tabela 9" in (page.get_text() or "")]
        if gloss_pages and tab9_pages and gloss_pages[0] != tab9_pages[0]:
            print(f"QA PDF: TABLE_CAPTION_ORPHAN Glossário p{gloss_pages[0]} tabela p{tab9_pages[0]}")
    except Exception as exc:  # noqa: BLE001
        print("QA PDF: inspeção de texto indisponível:", exc)

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera PDF apresentável do boletim El Niño (padrão SES-MT).")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="Markdown de origem")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="PDF de saída")
    parser.add_argument("--render-pages", action="store_true", help="Exporta PNG de cada página para inspeção visual")
    parser.add_argument("--force", action="store_true", help="Ignora bloqueio de QA do Mapa 3 (não usar em publicação)")
    args = parser.parse_args()
    qa_log = args.src.with_suffix(".qa.log")
    if qa_log.exists() and not args.force:
        qtxt = qa_log.read_text(encoding="utf-8", errors="ignore")
        blockers = (
            "MAP3_STALE_ERROR: 1",
            "MAP3_CLASS_DISTRIBUTION_ERROR: 1",
            "MAP3_FILE_CREATED_THIS_RUN=false",
            "MAP3_CLASSIFICATION_HASH_MATCH=false",
            "CIEVS_NAME_ERROR: 1",
        )
        hit = [b for b in blockers if b in qtxt]
        if hit or "MAP3_MUNICIPAL_DIFF_COUNT: " in qtxt and not re.search(
            r"MAP3_MUNICIPAL_DIFF_COUNT: 0\b", qtxt
        ):
            # DIFF count > 0 também bloqueia
            m = re.search(r"MAP3_MUNICIPAL_DIFF_COUNT:\s*(\d+)", qtxt)
            if hit or (m and int(m.group(1)) > 0):
                print("BLOQUEIO: QA do Mapa 3 / CIEVS impede versão apresentável:", hit or m.group(0))
                print("Use --force apenas para inspeção local (não publicação).")
                return 2
    path = build_pdf(args.src, args.out)
    print(path)
    # Cópia com nomenclatura oficial da Sala (SE inferida do nome do MD, se possível).
    try:
        from sisclima.plano.participantes import nome_arquivo_boletim_sala

        m = re.search(r"SE[_\s-]?(\d+)[-_/]?(\d{4})", args.src.name, re.I)
        if m:
            sala_name = nome_arquivo_boletim_sala(se=m.group(1), ano=m.group(2))
            sala_path = args.out.parent / sala_name
            sala_path.write_bytes(path.read_bytes())
            print(sala_path)
    except Exception as exc:  # noqa: BLE001
        print("Aviso: não gerou cópia com nome da Sala:", exc)
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
