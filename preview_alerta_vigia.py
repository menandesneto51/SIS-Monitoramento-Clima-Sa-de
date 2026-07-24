"""Gera preview local dos 3 alertas VIGIA sem enviar.

Uso:
  .\\.venv\\Scripts\\python.exe preview_alerta_vigia.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from sisclima.core.db import read_table
from sisclima.alerts.vigia_alerts import compose_vigia_messages


def main() -> int:
    resumo = read_table("resumo_municipal_atual")
    estado = read_table("resumo_situacao_atual")
    if resumo is None or resumo.empty:
        print("Tabela resumo_municipal_atual vazia. Rode o pipeline antes.")
        return 1

    ind = {}
    if estado is not None and not estado.empty:
        ind = estado.tail(1).iloc[0].to_dict()
    else:
        ind = resumo.sort_values("score", ascending=False).head(1).iloc[0].to_dict()

    motivos = str(ind.get("motivo", "")).split("; ")
    msgs = compose_vigia_messages(
        data_referencia=str(ind.get("data_referencia") or ind.get("data") or ""),
        nivel=str(ind.get("nivel", "roxa")),
        motivos=motivos,
        resumo_mun=resumo,
        old_nivel=str(ind.get("nivel")),
        force=True,
        indicadores=ind,
    )

    out_dir = Path("exports") / "preview_alertas"
    out_dir.mkdir(parents=True, exist_ok=True)
    for m in msgs:
        path = out_dir / f"preview_{m['tipo']}.txt"
        path.write_text(m["message"], encoding="utf-8")
        print("=" * 72)
        print(m["subject"])
        print(f"ai_fonte={m.get('ai_fonte')}")
        print(f"salvo em: {path}")
        print(m["message"][:1200])
        print("...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
