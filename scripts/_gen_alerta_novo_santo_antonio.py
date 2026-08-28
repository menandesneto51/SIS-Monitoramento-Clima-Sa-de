# -*- coding: utf-8 -*-
"""Gera preview do alerta municipal Novo Santo Antônio (validação)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sisclima.alerts.digest import (
    build_multilevel_pack,
    build_orientacoes_municipal,
    format_municipal_telegram,
    format_payload_html,
)
from sisclima.core.db import read_table
from sisclima.engines.alertas_multinivel import build_alertas_multinivel

IBGE = "5106315"
MUN = "Novo Santo Antônio"
OUT = ROOT / "data" / "output"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    payloads, _fp, _meta = build_multilevel_pack()
    mun = [p for p in payloads if p.get("escopo") == "municipal" and str(p.get("alvo_id")) == IBGE]
    if not mun:
        resumo = read_table("resumo_municipal_atual")
        alerta = read_table("alerta_integrado_sis_titan")
        pred = read_table("predicao_calor_7d_municipal_v6")
        all_p = build_alertas_multinivel(resumo, alerta, pred, min_level="verde")
        mun = [p for p in all_p if str(p.get("alvo_id")) == IBGE]
    if not mun:
        print("ERRO: município não encontrado", file=sys.stderr)
        return 2

    p = mun[0]
    p["orientacoes_municipais"] = build_orientacoes_municipal(p)
    txt = format_municipal_telegram(p)
    html_inner = format_payload_html(p)
    full_html = (
        "<!DOCTYPE html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">"
        f"<title>Alerta Municipal - {MUN}</title></head>"
        "<body style=\"font-family:Segoe UI,Arial,sans-serif;max-width:860px;"
        "margin:0 auto;background:#f8fafc;padding:18px\">"
        f"<h1>ARARAS MT — Alerta Municipal — {MUN}</h1>"
        f"<p>Validação · rodada {p.get('data_referencia')} · IBGE {IBGE}</p>"
        f"{html_inner}</body></html>"
    )

    base = OUT / "alerta_novo_santo_antonio_v11_preview"
    txt_path = base.with_suffix(".txt")
    html_path = base.with_suffix(".html")
    txt_path.write_text(txt, encoding="utf-8")
    html_path.write_text(full_html, encoding="utf-8")

    metrics = {
        k: p.get(k)
        for k in [
            "alvo_id",
            "alvo_nome",
            "nivel",
            "nivel_rotulo",
            "score",
            "tmax",
            "utci_proxy",
            "risco_cumulativo_3d",
            "pressao_calor_pct",
            "indice_pressao_saude",
            "pm25_ugm3",
            "ocupacao_leitos_pct",
            "data_referencia",
            "motivo",
            "regional",
            "gerado_em",
        ]
    }
    print(str(txt_path.resolve()))
    print(str(html_path.resolve()))
    print("---METRICS_JSON---")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
