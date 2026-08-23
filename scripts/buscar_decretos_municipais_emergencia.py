# -*- coding: utf-8 -*-
"""Triagem municipal: busca 'situação de emergência' e filtra Prefeitura + tema ARARAS."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sisclima.core.db import write_df

HEADERS = {"User-Agent": "ARARAS-MT/1.0", "Accept": "application/json"}
BASE = "https://www.iomat.mt.gov.br/busca/busca/buscar/query"

QUERIES = [
    "situação de emergência",
    "\"situação de emergência\"",
    "estado de calamidade pública",
    "\"calamidade pública\"",
    "reconhece a situação de emergência",
    "declara situação de emergência",
]

PAT_MUN = re.compile(
    r"PREFEITURA\s+MUNICIPAL\s+DE\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç\s\-']{2,45})"
    r"|PODER\s+EXECUTIVO\s+MUNICIPAL[^\n]{0,80}?"
    r"PREFEITURA\s+MUNICIPAL\s+DE\s+([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇa-záéíóúâêôãõç\s\-']{2,45})",
    re.I,
)
PAT_SE = re.compile(
    r"situa[cç][aã]o\s+de\s+emerg[eê]ncia|estado\s+de\s+calamidade(?:\s+p[uú]blica)?|"
    r"calamidade\s+p[uú]blica",
    re.I,
)
PAT_TEMA = re.compile(
    r"estiagem|seca|queimad|inc[eê]ndio(?:s)?\s+florest|fuma[cç]a|onda\s+de\s+calor|"
    r"inunda[cç][aã]o|enchente|desastre|cobrade|el\s*ni[nñ]o|chuvas?\s+intens|"
    r"vendaval|granizo|estiagem\s+prolongada",
    re.I,
)
PAT_DEC = re.compile(
    r"DECRETO\s+(?:MUNICIPAL\s+)?N[º°\.]*\s*[\d\.\/\-]+[^\n]{0,220}",
    re.I,
)
PAT_RUIDO = re.compile(
    r"preg[aã]o\s+eletr[oô]nico|inexigibilidade|concorr[eê]ncia\s+p[uú]blica|"
    r"credenciamento|extrato\s+de\s+contrato|chamada\s+p[uú]blica|"
    r"folha\s+de\s+pagamento|nomea[cç][aã]o",
    re.I,
)


def fetch_pages(q: str, max_pages: int = 8) -> list[dict]:
    out = []
    for page in range(1, max_pages + 1):
        # sem filtro de ano no path — filtra por data depois (API y:2026 ranqueia mal)
        url = f"{BASE}/{page}/?1=1&q={quote_plus(q)}"
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
        hits = ((r.json().get("hits") or {}).get("hits") or [])
        if not hits:
            break
        for h in hits:
            src = h.get("_source") or {}
            out.append(
                {
                    "consulta": q,
                    "data_publicacao": str(src.get("data") or "")[:10],
                    "pagina": src.get("pagina"),
                    "diario_id": src.get("diario_id"),
                    "conteudo": src.get("conteudo") or "",
                    "url": f"https://www.iomat.mt.gov.br/portal/edicoes/download/{src.get('diario_id')}",
                }
            )
    return out


def municipio_from(c: str) -> str | None:
    m = PAT_MUN.search(c)
    if not m:
        return None
    nome = m.group(1) or m.group(2)
    if not nome:
        return None
    nome = re.sub(r"\s+", " ", nome).strip(" .,-")
    # corta lixo após nome
    nome = re.split(r"\s{2,}|N[º°]|P[aá]gina|PUBLICA|EXTRATO|AVISO|DECRETO", nome, maxsplit=1)[0]
    return nome.strip().title() if len(nome) >= 3 else None


def main() -> None:
    corte = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    seen = set()
    rows = []
    for q in QUERIES:
        hits = fetch_pages(q, max_pages=10)
        print(f"{q!r}: {len(hits)} hits brutos")
        for h in hits:
            key = (h["diario_id"], h["pagina"])
            if key in seen:
                continue
            seen.add(key)
            c = h["conteudo"]
            dt = h["data_publicacao"]
            if not dt or dt < corte:
                continue
            if not PAT_SE.search(c):
                continue
            mun = municipio_from(c)
            # municipal se tem Prefeitura no texto OU título de decreto municipal
            is_mun = bool(mun) or bool(re.search(r"decreto\s+municipal|prefeitura\s+municipal", c, re.I))
            if not is_mun:
                continue
            tema_ok = bool(PAT_TEMA.search(c))
            ruido = bool(PAT_RUIDO.search(c[:500])) and not tema_ok
            if ruido:
                status = "DESCARTAR"
            elif tema_ok:
                status = "CANDIDATO"
            else:
                status = "REVISAR"
            dec = PAT_DEC.search(c)
            se = PAT_SE.search(c)
            temas = sorted({t.casefold() for t in PAT_TEMA.findall(c)})[:8]
            # contexto ao redor do match SE
            i = se.start() if se else 0
            ctx = c[max(0, i - 120) : i + 280].replace("\n", " ")
            rows.append(
                {
                    "status": status,
                    "municipio": mun,
                    "data_publicacao": dt,
                    "pagina": h["pagina"],
                    "diario_id": h["diario_id"],
                    "url": h["url"],
                    "decreto_match": (dec.group(0)[:200].replace("\n", " ") if dec else None),
                    "se_match": se.group(0) if se else None,
                    "temas": "; ".join(temas),
                    "contexto_se": ctx,
                    "consulta": h["consulta"],
                }
            )

    df = pd.DataFrame(rows)
    print("filtrados municipais:", len(df))
    if df.empty:
        print("Nenhum ato municipal com SE/calamidade na janela.")
        # ainda gera MD vazio explicativo
        out = ROOT / "docs" / "apresentacoes" / f"Decretos_Municipais_Emergencia_ARARAS_{datetime.now():%Y-%m-%d}.md"
        out.write_text(
            "\n".join(
                [
                    "# Decretos municipais de emergência — triagem ARARAS MT",
                    "",
                    f"Gerado em {datetime.now():%d/%m/%Y às %Hh%M}.",
                    "",
                    f"Janela desde {corte}.",
                    "",
                    "**Resultado:** nenhum decreto municipal de situação de emergência/calamidade "
                    "com tema ARARAS (seca/estiagem/queimadas/fumaça/calor/inundação) foi localizado "
                    "nas primeiras páginas da busca IOMAT para os termos testados.",
                    "",
                    "Isso **não prova ausência** — a API de busca do IOMAT ranqueia mal e páginas "
                    "municipais antigas podem não aparecer no topo. Próximos caminhos:",
                    "1. Lista de municípios reconhecidos pela Defesa Civil / S2iD (SEDEC).",
                    "2. Busca por município nominal (ex.: `PREFEITURA DE X situação de emergência`).",
                    "3. Sinais de imprensa → validação pontual no IOMAT.",
                ]
            ),
            encoding="utf-8",
        )
        print("OK", out)
        return

    write_df(df, "iomat_decretos_municipais_candidatos")
    print(df["status"].value_counts())
    print("municípios:", sorted(df["municipio"].dropna().unique().tolist())[:40])

    out = ROOT / "docs" / "apresentacoes" / f"Decretos_Municipais_Emergencia_ARARAS_{datetime.now():%Y-%m-%d}.md"
    lines = [
        "# Decretos municipais de emergência — triagem ARARAS MT",
        "",
        f"Gerado em {datetime.now():%d/%m/%Y às %Hh%M}.",
        f"Janela desde {corte}. Total: **{len(df)}** | CANDIDATO: "
        f"**{(df.status=='CANDIDATO').sum()}** | REVISAR: **{(df.status=='REVISAR').sum()}**.",
        "",
        "> Triagem automática. Validar número/vigência/tema antes de inserir no boletim.",
        "",
        "## Candidatos",
        "",
    ]
    for _, r in df[df.status == "CANDIDATO"].sort_values("data_publicacao", ascending=False).iterrows():
        lines += [
            f"### {r.municipio or 'Município a confirmar'} — {r.data_publicacao}",
            f"- Decreto (match): {r.decreto_match or 'não extraído'}",
            f"- Temas: {r.temas}",
            f"- IOMAT: p. {r.pagina} — {r.url}",
            f"- Contexto: {r.contexto_se}",
            "",
        ]
    lines += ["## Revisar", ""]
    for _, r in df[df.status == "REVISAR"].head(25).iterrows():
        lines.append(
            f"- **{r.municipio or '?'}** ({r.data_publicacao}) — {r.decreto_match or r.contexto_se[:120]} — {r.url}"
        )
    out.write_text("\n".join(lines), encoding="utf-8")
    print("OK", out)


if __name__ == "__main__":
    main()
