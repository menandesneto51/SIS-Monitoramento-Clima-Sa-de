# -*- coding: utf-8 -*-
"""Envia o boletim El Niño apresentável aos contatos da Sala de Situação.

Uso:
  # lista destinatários (sem SMTP)
  python scripts/enviar_boletim_sala.py --dry-run

  # teste só CIEVS (menandesneto + notifica + tatiana se no catálogo)
  python scripts/enviar_boletim_sala.py --teste-cievs

  # envio real à lista completa (Sala + rede ERS + COSEMS)
  python scripts/enviar_boletim_sala.py --enviar

PDF padrão: v10 apresentável renomeado com a nomenclatura da Sala.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.alerts.notifier import send_email  # noqa: E402
from sisclima.plano.participantes import (  # noqa: E402
    carregar_participantes,
    destinatarios_boletim_sala,
    nome_arquivo_boletim_sala,
)

DEFAULT_PDF_V10 = (
    ROOT / "docs" / "apresentacoes" / "Boletim_ElNino_SE_34-2026_apresentavel_v10_2.pdf"
)
DEFAULT_SE = 34
DEFAULT_ANO = 2026


def _ensure_named_pdf(src: Path, *, se: int, ano: int) -> Path:
    dest = src.parent / nome_arquivo_boletim_sala(se=se, ano=ano)
    if src.resolve() == dest.resolve():
        return dest
    if not src.is_file():
        raise FileNotFoundError(f"PDF fonte inexistente: {src}")
    shutil.copy2(src, dest)
    return dest


def _corpo(*, se: int, ano: int, pdf_name: str) -> tuple[str, str, str]:
    subject = f"Boletim Informativo Sala de Situação MT El Niño · SE {se}-{ano}"
    plain = (
        f"Prezados(as) participantes da Sala de Situação,\n\n"
        f"Segue em anexo o Boletim Informativo da Sala de Situação MT — El Niño "
        f"(semana epidemiológica {se}/{ano}).\n\n"
        f"Arquivo: {pdf_name}\n"
        f"Produto: ARARAS MT · CIEVS-MT / SES-MT\n"
        f"Base normativa: Portaria nº 0590/2026/GBSES.\n\n"
        f"Em caso de dúvida, responder a este e-mail ou contatar o CIEVS-MT.\n"
    )
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.55;color:#12354e">
      <p>Prezados(as) participantes da Sala de Situação,</p>
      <p>Segue em anexo o <strong>Boletim Informativo da Sala de Situação MT — El Niño</strong>
         (semana epidemiológica <strong>{se}/{ano}</strong>).</p>
      <p>Arquivo: <em>{pdf_name}</em><br/>
         Produto: ARARAS MT · CIEVS-MT / SES-MT<br/>
         Base normativa: Portaria nº 0590/2026/GBSES.</p>
      <p>Em caso de dúvida, responder a este e-mail ou contatar o CIEVS-MT.</p>
    </div>
    """
    return subject, plain, html


def main() -> int:
    p = argparse.ArgumentParser(description="Envia boletim El Niño apresentável à Sala")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF_V10, help="PDF fonte (v10 apresentável)")
    p.add_argument("--se", type=int, default=DEFAULT_SE)
    p.add_argument("--ano", type=int, default=DEFAULT_ANO)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="Só lista destinatários e prepara PDF")
    g.add_argument("--teste-cievs", action="store_true", help="Envia só para CIEVS (teste)")
    g.add_argument("--enviar", action="store_true", help="Envia à lista completa da Sala")
    args = p.parse_args()

    cat = carregar_participantes()
    dests = destinatarios_boletim_sala(cat)
    pend_ers = cat.get("pendencias_regionais_email") or []
    sem_email = cat.get("sem_email") or []

    pdf = _ensure_named_pdf(args.pdf, se=args.se, ano=args.ano)
    subject, plain, html = _corpo(se=args.se, ano=args.ano, pdf_name=pdf.name)

    if args.teste_cievs:
        allow = {
            "menandesneto@ses.mt.gov.br",
            "tatianabelmonte@ses.mt.gov.br",
            "notifica@ses.mt.gov.br",
        }
        emails = sorted({d["email"] for d in dests if d["email"] in allow} | {"notifica@ses.mt.gov.br"})
        modo = "teste_cievs"
    else:
        emails = [d["email"] for d in dests]
        modo = "dry_run" if args.dry_run else "enviar"

    report = {
        "quando": datetime.now(timezone.utc).isoformat(),
        "modo": modo,
        "pdf": str(pdf),
        "assunto": subject,
        "n_destinatarios": len(emails),
        "emails": emails,
        "por_canal": {},
        "pendencias_regionais_email": pend_ers,
        "sem_email": sem_email,
        "enviado": False,
    }
    from collections import Counter

    report["por_canal"] = dict(Counter(d.get("canal_distribuicao") or "?" for d in dests))

    print("=== Boletim Sala de Situação ===")
    print(f"PDF: {pdf.name} ({pdf.stat().st_size // 1024} KB)")
    print(f"Assunto: {subject}")
    print(f"Destinatários ({len(emails)}):")
    for e in emails:
        print(f"  - {e}")
    if pend_ers:
        print(f"Pendências e-mail ERS individuais ({len(pend_ers)}): ainda sem endereço cadastrado")
    if sem_email:
        print(f"Sem e-mail na lista SES: {', '.join(sem_email)}")

    if args.dry_run:
        out = ROOT / "logs" / f"boletim_sala_dryrun_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Dry-run OK · relatório: {out}")
        return 0

    ok = send_email(subject, plain, html_body=html, to=emails, attachments=[pdf])
    report["enviado"] = bool(ok)
    out = ROOT / "logs" / f"boletim_sala_{modo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Envio: {'OK' if ok else 'FALHOU'} · {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
