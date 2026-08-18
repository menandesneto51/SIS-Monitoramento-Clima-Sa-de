# -*- coding: utf-8 -*-
"""Preview local do boletim estadual SES (sem envio).

Uso:
  .venv\\Scripts\\python.exe scripts/preview_alerta_ses.py
  .venv\\Scripts\\python.exe scripts/preview_alerta_ses.py --out tmp/alerta_ses_preview.txt

Critérios do plano (alerta SES legível):
  - ordem: resumo → KPI → ações → (IA) → prioritários → rodapé
  - < ~6500 caracteres
  - prioritários em 1 linha; ocupação local/estimado
  - legenda única; sem eco SAF:; HTML sem rodapé duplo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser(description="Preview do alerta estadual SES/CIEVS")
    ap.add_argument("--out", type=Path, default=None, help="Salvar texto em arquivo")
    ap.add_argument("--html-out", type=Path, default=None, help="Salvar HTML em arquivo")
    ap.add_argument("--max-chars", type=int, default=6500)
    args = ap.parse_args()

    from sisclima.alerts.digest import (
        build_multilevel_pack,
        build_orientacoes_ses_setores,
        format_ses_html,
        format_ses_telegram,
    )

    payloads, _fp, meta = build_multilevel_pack()
    ses = next((p for p in payloads if p.get("escopo") == "estadual"), None)
    if not ses:
        print("ERRO: sem payload estadual", file=sys.stderr)
        return 2

    ses["orientacoes_setores"] = build_orientacoes_ses_setores(ses)
    # Preview sem chamar LLM (evita latência/custo); use digest real para IA.
    ses.setdefault("orientacao_ia", None)
    txt = format_ses_telegram(ses)
    html = format_ses_html(ses)

    checks = {
        "chars": len(txt),
        "order_ok": (
            txt.find("Resumo executivo")
            < txt.find("Situação estadual")
            < txt.find("Ações por setor")
            < txt.find("Municípios prioritários")
        ),
        "has_legend": "Legenda:" in txt,
        "no_saf_echo": "SAF: Assistência" not in txt,
        "prio_one_line": True,
        "html_single_footer": html.lower().count("validar no painel") <= 1,
        "html_h2": html.count("<h2") >= 3,
        "top8": len(ses.get("municipios_prioritarios") or []) <= 8,
    }
    prio_lines = [
        ln for ln in txt.splitlines() if ln[:4].strip()[:1].isdigit() and ". " in ln[:5]
    ]
    checks["prio_n"] = len(prio_lines)
    checks["prio_one_line"] = bool(prio_lines) and all("|" in ln for ln in prio_lines)
    checks["ocup_tagged"] = any((" local" in ln) or ("estimado" in ln) for ln in prio_lines)
    checks["under_max"] = len(txt) <= args.max_chars

    print(txt)
    print("\n--- VALIDATION ---")
    for k, v in checks.items():
        print(f"{k}: {v}")
    print(f"nivel: {meta.get('nivel')} | fingerprint meta n_ses={meta.get('n_ses')}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt, encoding="utf-8")
        print(f"salvo: {args.out}")
    if args.html_out:
        args.html_out.parent.mkdir(parents=True, exist_ok=True)
        args.html_out.write_text(html, encoding="utf-8")
        print(f"salvo: {args.html_out}")

    ok = all(
        [
            checks["order_ok"],
            checks["has_legend"],
            checks["no_saf_echo"],
            checks["prio_one_line"],
            checks["html_single_footer"],
            checks["under_max"],
            checks["top8"],
        ]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
