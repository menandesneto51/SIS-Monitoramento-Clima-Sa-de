# -*- coding: utf-8 -*-
"""Gera config/plano_el_nino_2026_catalogo.yaml a partir da planilha SES-MT."""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sisclima.plano.areas import AREAS_CANONICAS, area_id_de_responsavel  # noqa: E402
from sisclima.plano.constants import MAPA_MODO_PLANILHA, MAPA_TIPO_PLANILHA, TIPOS_NO_INDICE  # noqa: E402


def _fold(texto: str) -> str:
    txt = unicodedata.normalize("NFKD", str(texto or ""))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", txt).strip()


def _slug(texto: str, prefixo: str = "") -> str:
    base = _fold(texto).casefold()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:60]
    return f"{prefixo}{base}" if prefixo else base


def _tipo(valor: str) -> str:
    t = _fold(valor).casefold().replace(" ", "")
    return MAPA_TIPO_PLANILHA.get(t, "execucao")


def _modo(valor: str) -> str:
    t = _fold(valor).casefold().replace(" ", "")
    if t in MAPA_MODO_PLANILHA:
        return MAPA_MODO_PLANILHA[t]
    if "semi" in t:
        return "semiautomatico"
    if "manual" in t:
        return "documental"
    if "auto" in t:
        return "automatico"
    return "documental"


def gerar(path_xlsx: Path) -> dict:
    import pandas as pd

    acoes_df = pd.read_excel(path_xlsx, sheet_name="Acoes_Originais", header=0)
    matriz = pd.read_excel(path_xlsx, sheet_name="Matriz_ARARA", header=0)

    eixos_ordem: list[str] = []
    for eixo in matriz["Eixo"].astype(str):
        if eixo not in eixos_ordem and eixo.lower() != "nan":
            eixos_ordem.append(eixo)
    eixos = [{"id": _slug(nome, "eixo_"), "nome": nome, "ordem": i + 1} for i, nome in enumerate(eixos_ordem)]
    eixo_ids = {e["nome"]: e["id"] for e in eixos}

    metas_seen: dict[tuple[str, str], str] = {}
    metas: list[dict] = []
    acoes: list[dict] = []
    for i, row in acoes_df.iterrows():
        meta_txt = str(row.get("Meta") or "").strip()
        eixo_nome = ""
        linha = row.get("Linha fonte")
        hit = matriz[matriz["Linha origem"] == linha]
        if not hit.empty:
            eixo_nome = str(hit.iloc[0].get("Eixo") or "")
        eixo_id = eixo_ids.get(eixo_nome, _slug(eixo_nome or "sem_eixo", "eixo_"))
        chave = (eixo_id, meta_txt)
        if chave not in metas_seen:
            mid = f"M{len(metas_seen)+1:02d}"
            metas_seen[chave] = mid
            metas.append(
                {
                    "id": mid,
                    "eixo_id": eixo_id,
                    "descricao": meta_txt,
                    "prazo": str(row.get("Prazo") or "").strip() or None,
                }
            )
        resp = str(row.get("Responsável") or "").strip()
        acoes.append(
            {
                "id": f"A{i+1:02d}",
                "linha_fonte": int(linha) if pd.notna(linha) else None,
                "meta_id": metas_seen[chave],
                "eixo_id": eixo_id,
                "area_id": area_id_de_responsavel(resp),
                "descricao": str(row.get("Ação") or "").strip(),
                "responsavel": resp,
                "prazo": str(row.get("Prazo") or "").strip() or None,
                "prazo_iso": None,
                "prioridade": str(row.get("Prioridade") or "").strip() or None,
                "status_inicial": "nao_iniciada",
                "indicador_original": str(row.get("Indicador original") or "").strip() or None,
            }
        )
    acao_por_linha = {a["linha_fonte"]: a["id"] for a in acoes if a.get("linha_fonte")}

    indicadores: list[dict] = []
    for i, row in matriz.iterrows():
        codigo_fonte = str(row.get("ID ARARA") or f"ARARA-{i+1:03d}")
        linha = row.get("Linha origem")
        linha_i = int(linha) if pd.notna(linha) else None
        eixo_nome = str(row.get("Eixo") or "")
        resp = str(row.get("Responsável") or "").strip()
        tipo = _tipo(str(row.get("Tipo") or ""))
        indicadores.append(
            {
                "id": f"IND-{i+1:03d}",
                "codigo_fonte": codigo_fonte,
                "acao_id": acao_por_linha.get(linha_i),
                "eixo_id": eixo_ids.get(eixo_nome, _slug(eixo_nome, "eixo_")),
                "area_id": area_id_de_responsavel(resp),
                "nome": str(row.get("Indicador ARARA proposto") or "").strip(),
                "tipo": tipo,
                "modo_atualizacao": _modo(str(row.get("Classe de automação") or row.get("Automação") or "")),
                "formula": str(row.get("Fórmula / regra de cálculo") or "").strip() or None,
                "meta_numerica": str(row.get("Meta / gatilho") or "").strip() or None,
                "unidade": str(row.get("Unidade") or "").strip() or None,
                "direcao": str(row.get("Direção") or "").strip() or None,
                "fonte": str(row.get("Fonte primária sugerida") or "").strip() or None,
                "periodicidade": str(row.get("Periodicidade") or "").strip() or None,
                "responsavel": resp,
                "prazo": str(row.get("Prazo original") or "").strip() or None,
                "prioridade": str(row.get("Prioridade") or "").strip() or None,
                "semaforo": str(row.get("Regra de semáforo / gatilho") or "").strip() or None,
                "evidencia_minima": str(row.get("Evidência mínima") or "").strip() or None,
                "entra_no_indice": tipo in TIPOS_NO_INDICE,
            }
        )

    areas_usadas = sorted({a["area_id"] for a in acoes} | {i["area_id"] for i in indicadores})
    areas = [{"id": aid, "nome": next((n for k, n in AREAS_CANONICAS if k == aid), aid)} for aid in areas_usadas]

    return {
        "fonte": {
            "arquivo": path_xlsx.name,
            "abas": ["Acoes_Originais", "Matriz_ARARA", "Painel_ARARA"],
            "n_acoes": len(acoes),
            "n_indicadores": len(indicadores),
            "n_indicadores_indice": sum(1 for i in indicadores if i.get("entra_no_indice")),
            "nota": "Códigos ARARA-### são da planilha-fonte. Produto: ARARAS MT.",
        },
        "areas": areas,
        "eixos": eixos,
        "metas": metas,
        "acoes": acoes,
        "indicadores": indicadores,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--xlsx",
        default=str(Path.home() / "Downloads" / "Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx"),
    )
    parser.add_argument("--out", default=str(ROOT / "config" / "plano_el_nino_2026_catalogo.yaml"))
    args = parser.parse_args()
    src = Path(args.xlsx)
    if not src.exists():
        print("Planilha não encontrada:", src)
        return 1
    data = gerar(src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(
        f"Catálogo: {out} | ações={data['fonte']['n_acoes']} "
        f"indicadores={data['fonte']['n_indicadores']} "
        f"índice={data['fonte']['n_indicadores_indice']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
