# -*- coding: utf-8 -*-
"""
Completa o ARARAS para operação: pressão proxy, correlações, predição 7d,
alerta inteligente e gaps de SIVEP/arboviroses/ar/ANA no resumo.

Uso:
  .venv\\Scripts\\python.exe completar_sistema_operacional.py
"""
from __future__ import annotations

import json
import sys

from sisclima.engines.operational_enrichment import run_operational_enrichment


def main() -> int:
    try:
        # Tenta atualizar ocupação IndicaSUS se configurado (não bloqueia se falhar)
        try:
            from atualizar_ocupacao_indicasus import main as upd_occ
            print("[INFO] Tentando atualizar ocupação IndicaSUS...")
            upd_occ()
        except SystemExit:
            pass
        except Exception as exc:
            print(f"[AVISO] IndicaSUS ocupação não atualizada: {exc}")

        summary = run_operational_enrichment(reclassify=True)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        print("[OK] Sistema enriquecido e tabelas de inteligência gravadas.")
        return 0
    except Exception as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
