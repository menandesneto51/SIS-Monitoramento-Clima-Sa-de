"""Gera preview local do pacote VIGIA (4 categorias) sem enviar.

Uso:
  .\\.venv\\Scripts\\python.exe preview_alerta_vigia.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from sisclima.core.db import read_table
from sisclima.alerts.vigia_alerts import compose_vigia_messages


def _slug(text: str) -> str:
    out = re.sub(r"[^\w\-]+", "_", str(text), flags=re.UNICODE)
    return out.strip("_")[:80] or "item"


def main() -> int:
    resumo = read_table("resumo_municipal_atual")
    estado = read_table("resumo_situacao_atual")
    if resumo is None or resumo.empty:
        # Fallback CSV público (quando SQLite não tem o ciclo)
        csv = Path("data/public/ops_resumo_operacional_cnes.csv")
        if csv.exists():
            resumo = pd.read_csv(csv)
        else:
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
    for sub in ("01_estado", "02_regionais", "03_municipais", "04_cuiaba"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)

    contagem = {"estado": 0, "regional": 0, "municipal": 0, "cuiaba": 0}
    index_rows = []
    for m in msgs:
        tipo = m["tipo"]
        contagem[tipo] = contagem.get(tipo, 0) + 1
        if tipo == "estado":
            path = out_dir / "01_estado" / "estado.txt"
        elif tipo == "regional":
            path = out_dir / "02_regionais" / f"{_slug(m.get('destino'))}.txt"
        elif tipo == "municipal":
            path = out_dir / "03_municipais" / f"{_slug(m.get('destino'))}.txt"
        else:
            path = out_dir / "04_cuiaba" / "cuiaba.txt"
        path.write_text(m["message"], encoding="utf-8")
        index_rows.append(
            {
                "tipo": tipo,
                "destino": m.get("destino"),
                "subject": m.get("subject"),
                "arquivo": str(path),
                "ai_fonte": m.get("ai_fonte"),
            }
        )

    idx = pd.DataFrame(index_rows)
    idx_path = out_dir / "indice.csv"
    idx.to_csv(idx_path, index=False)

    print("=" * 72)
    print("Pacote VIGIA — 4 categorias")
    print(f"Total alertas: {len(msgs)} | contagem={contagem}")
    print(f"Índice: {idx_path}")
    for tipo in ("estado", "regional", "municipal", "cuiaba"):
        sample = next((r for r in index_rows if r["tipo"] == tipo), None)
        if not sample:
            continue
        print("-" * 72)
        print(sample["subject"])
        print(f"arquivo: {sample['arquivo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
