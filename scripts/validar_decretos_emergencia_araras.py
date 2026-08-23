# -*- coding: utf-8 -*-
"""Gera lista validada de atos para inserção no boletim ARARAS."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from sisclima.core.config import ROOT as SIS_ROOT
from sisclima.core.db import read_table, write_df

# Atos validados manualmente a partir do conteúdo IOMAT (não só score automático)
ATOS_VALIDADOS = [
    {
        "status": "INSERIR",
        "tipo": "Decreto estadual",
        "identificacao": "Decreto n.º 2.015, de 28 de abril de 2026",
        "ementa": (
            "Declara estado de emergência ambiental, dispõe sobre o período proibitivo "
            "de queimadas e constitui a Sala de Situação (ambiental / combate a incêndios)."
        ),
        "data_publicacao": "2026-04-29",
        "diario_id": 19059,
        "pagina": 2,
        "url": "https://www.iomat.mt.gov.br/portal/edicoes/download/19059",
        "relevancia_araras": "Base ambiental estadual vigente para emergência e proibição de queimadas.",
        "evidencia": "Título e ementa explícitos no IOMAT (edição 29/04/2026).",
    },
    {
        "status": "INSERIR",
        "tipo": "Portaria SES-MT",
        "identificacao": "Portaria n.º 0590/2026/GBSES (Sala de Situação Saúde e Clima — El Niño 2026–2027)",
        "ementa": (
            "Institui, no âmbito da SES-MT, a Sala de Situação em Saúde para preparação, "
            "monitoramento e resposta aos impactos do El Niño 2026–2027 e eventos climáticos extremos."
        ),
        "data_publicacao": "2026-08-13",
        "diario_id": 19279,
        "pagina": 56,
        "url": "https://www.iomat.mt.gov.br/portal/edicoes/download/19279",
        "relevancia_araras": "Base normativa direta do boletim El Niño / ARARAS / CIEVS-MT.",
        "evidencia": (
            "Texto integral da instituição da Sala de Situação em Saúde localizado na "
            "edição IOMAT de 13/08/2026, p. 56 (mesmo ato já referenciado no boletim)."
        ),
    },
    {
        "status": "INSERIR",
        "tipo": "Instrução Normativa conjunta",
        "identificacao": "Instrução Normativa Conjunta SEMA/CBM-MT n.º 03, de 12 de agosto de 2026",
        "ementa": (
            "Dispõe sobre procedimentos para abertura de aceiros em propriedades rurais "
            "na Área de Uso Restrito do Pantanal durante o período de emergência ambiental "
            "do Decreto n.º 2.015/2026."
        ),
        "data_publicacao": "2026-08-13",
        "diario_id": 19279,
        "pagina": 10,
        "url": "https://www.iomat.mt.gov.br/portal/edicoes/download/19279",
        "relevancia_araras": "Operacionaliza emergência ambiental / fogo no Pantanal.",
        "evidencia": "Publicação IOMAT 13/08/2026 com referência explícita ao Decreto 2.015/2026.",
    },
    {
        "status": "REFERENCIAL",
        "tipo": "Menção / aplicação",
        "identificacao": "Menções operacionais ao Decreto n.º 2.015/2026 (jun/2026)",
        "ementa": (
            "Publicações que aplicam o Decreto 2.015/2026 (ex.: período 1º/07 a 30/11/2026; "
            "extratos SEMA). Não são novos decretos de emergência."
        ),
        "data_publicacao": "2026-06-10",
        "diario_id": 19136,
        "pagina": 23,
        "url": "https://www.iomat.mt.gov.br/portal/edicoes/download/19136",
        "relevancia_araras": "Confirma vigência/operacionalização do Decreto 2.015; não republicar como ato novo.",
        "evidencia": "Trechos IOMAT 10/06/2026 citando o Decreto 2.015.",
    },
]

DESCARTES_NOTAVEIS = [
    "Portaria 0578/2026/GBSES — cofinanciamento hospitalar Rondonópolis (falso positivo na mesma edição).",
    "Decreto 2.017/2026 — medalha a policial militar (ruído na edição do Decreto 2.015).",
    "Decreto 2.215/2026 — Selo Parceiro do Meio Ambiente (não é emergência).",
    "Editais, contratos, apostilamentos, licitações e portarias de designação com coocorrência lexical.",
]


def main() -> None:
    rows = []
    for a in ATOS_VALIDADOS:
        rows.append(
            {
                "uid": f"val-{a['diario_id']}-{a.get('pagina')}-{a['status']}",
                "status_validacao": a["status"],
                "tipo": a["tipo"],
                "identificacao": a["identificacao"],
                "ementa": a["ementa"],
                "data_publicacao": a["data_publicacao"],
                "diario_id": a["diario_id"],
                "pagina": a.get("pagina"),
                "url": a["url"],
                "relevancia_araras": a["relevancia_araras"],
                "evidencia": a["evidencia"],
                "validado_em": datetime.now().isoformat(timespec="seconds"),
            }
        )
    df = pd.DataFrame(rows)
    write_df(df, "iomat_decretos_validados")

    out = SIS_ROOT / "docs" / "apresentacoes" / f"Decretos_Emergencia_ARARAS_VALIDADOS_{datetime.now():%Y-%m-%d}.md"
    linhas = [
        "# Decretos / atos validados para inserção — ARARAS MT",
        "",
        f"Validação em {datetime.now():%d/%m/%Y às %Hh%M}.",
        "",
        "Critério: **somente atos oficiais do IOMAT** com ementa climática/ambiental/saúde "
        "verificável no trecho. Score automático **não** basta.",
        "",
        f"Coleta bruta anterior: {len(read_table('iomat_decretos_emergencia'))} itens → "
        f"**{sum(1 for a in ATOS_VALIDADOS if a['status']=='INSERIR')} para inserir**, "
        f"{sum(1 for a in ATOS_VALIDADOS if a['status']=='REFERENCIAL')} referenciais.",
        "",
        "## Aprovar para inserção no boletim",
        "",
    ]
    for a in ATOS_VALIDADOS:
        if a["status"] != "INSERIR":
            continue
        linhas += [
            f"### {a['identificacao']}",
            f"- Tipo: {a['tipo']}",
            f"- Publicação IOMAT: {a['data_publicacao']} (p. {a.get('pagina')})",
            f"- Ementa: {a['ementa']}",
            f"- Por que entra no ARARAS: {a['relevancia_araras']}",
            f"- Evidência: {a['evidencia']}",
            f"- Link: {a['url']}",
            "",
        ]
    linhas += ["## Referenciais (não inserir como decreto novo)", ""]
    for a in ATOS_VALIDADOS:
        if a["status"] != "REFERENCIAL":
            continue
        linhas += [
            f"- **{a['identificacao']}** — {a['ementa']} ({a['data_publicacao']}; {a['url']})",
        ]
    linhas += ["", "## Descartados (exemplos de ruído)", ""]
    for d in DESCARTES_NOTAVEIS:
        linhas.append(f"- {d}")
    linhas += [
        "",
        "---",
        "",
        "**Próximo passo:** confirmar esta lista. Após o OK, inserir no boletim El Niño "
        "uma seção curta “Atos oficiais de emergência / preparação climática”.",
        "",
        "Tabela SQLite: `iomat_decretos_validados`.",
    ]
    out.write_text("\n".join(linhas), encoding="utf-8")
    print(f"OK: {out}")
    print(df[["status_validacao", "identificacao"]].to_string(index=False))


if __name__ == "__main__":
    main()
