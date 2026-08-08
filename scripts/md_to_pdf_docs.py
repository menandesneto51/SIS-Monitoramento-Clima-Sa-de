# -*- coding: utf-8 -*-
"""Converte Markdown institucional em PDF (xhtml2pdf)."""
from __future__ import annotations

import sys
from pathlib import Path

import markdown
from xhtml2pdf import pisa

ROOT = Path(__file__).resolve().parents[1]
CSS = """
@page { size: A4; margin: 1.8cm 1.6cm 2cm 1.6cm; }
body { font-family: Helvetica, Arial, sans-serif; font-size: 10.5pt; color: #1a1a1a; line-height: 1.45; }
h1 { font-size: 18pt; color: #0b3d5c; border-bottom: 2px solid #0b3d5c; padding-bottom: 6px; margin-top: 0; }
h2 { font-size: 13pt; color: #0b3d5c; margin-top: 18px; border-bottom: 1px solid #c5d4de; padding-bottom: 3px; }
h3 { font-size: 11.5pt; color: #1f4e79; margin-top: 14px; }
h4 { font-size: 10.5pt; color: #333; }
p, li { orphans: 3; widows: 3; }
code, pre { font-family: Courier, monospace; font-size: 8.5pt; background: #f4f6f8; }
pre { padding: 8px; border: 1px solid #dde3ea; white-space: pre-wrap; }
table { width: 100%; border-collapse: collapse; margin: 10px 0 14px 0; font-size: 9pt; }
th, td { border: 1px solid #b0bec5; padding: 4px 6px; vertical-align: top; }
th { background: #e8eef3; color: #0b3d5c; text-align: left; }
blockquote { border-left: 3px solid #0b3d5c; margin-left: 0; padding-left: 10px; color: #444; }
hr { border: none; border-top: 1px solid #ccc; margin: 16px 0; }
a { color: #0b3d5c; text-decoration: none; }
.meta { font-size: 9pt; color: #555; margin-bottom: 16px; }
"""


def md_to_pdf(src: Path, dst: Path) -> None:
    text = src.read_text(encoding="utf-8")
    body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        output_format="html5",
    )
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <title>{src.stem}</title>
  <style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("wb") as out:
        result = pisa.CreatePDF(html, dest=out, encoding="utf-8")
    if result.err:
        raise SystemExit(f"Falha ao gerar PDF: {src} -> {dst} (erros={result.err})")
    print(f"OK {dst} ({dst.stat().st_size / 1024:.1f} KB)")


def main(argv: list[str] | None = None) -> int:
    out_dir = ROOT / "docs" / "apresentacoes"
    docs = [
        ROOT / "docs" / "RELATORIO_PRONTIDAO_INSTITUCIONAL.md",
        ROOT / "docs" / "STI_IMPLANTACAO_SERVIDOR_SES.md",
    ]
    for src in docs:
        if not src.exists():
            print(f"AUSENTE {src}", file=sys.stderr)
            return 1
        dst = out_dir / f"{src.stem}.pdf"
        md_to_pdf(src, dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
