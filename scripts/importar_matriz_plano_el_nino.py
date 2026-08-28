# -*- coding: utf-8 -*-
"""Importa a planilha de controle El Niño para o catálogo oficial ARARAS.

Uso:
  python scripts/importar_matriz_plano_el_nino.py --xlsx CAMINHO.xlsx
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT_YAML = ROOT / "config" / "plano_el_nino_matriz.yaml"

_AREA_RULES: list[tuple[str, str, str]] = [
    (r"COVSAN", "covsan", "Coordenadoria de Vigilância Sanitária"),
    (r"COVSAT|CEREST|Saúde do Trabalhador", "covsat", "Coordenadoria de Vigilância em Saúde do Trabalhador"),
    (r"COVSAM|VIGIAGUA|VIGIAR|Vigilância Ambiental", "covsam", "Coordenadoria de Vigilância em Saúde Ambiental"),
    (r"CPEI|Imuniza|Rede de Frio", "cpei", "Coordenadoria do Programa Estadual de Imunização"),
    (r"Assistência Farmacêutica|Farmaceu", "saf", "Superintendência de Assistência Farmacêutica"),
    (r"Atenção Terciária", "sas_terciaria", "Coordenadoria de Atenção Terciária / SAS"),
    (r"Atenção Secundária", "sas_secundaria", "Coordenadoria de Atenção Secundária / SAS"),
    (r"Urgência e Emergência|COAPRE|Redes de Urgência", "sas_urgencia", "Coordenadoria de Organização de Redes de Urgência e Emergência"),
    (r"Atenção à Saúde|Atenção/Regulação|Atenção \+", "sas_atencao", "Superintendência de Atenção à Saúde"),
    (r"Comunica", "comunicacao", "Assessoria de Comunicação / SES-MT"),
    (r"LACEN", "lacen", "Laboratório Central de Saúde Pública de Mato Grosso"),
    (r"CIEVS|VIGIDESASTRES|UNIEVS", "cievs", "UNIEVS/CIEVS — secretaria-executiva"),
]


def _txt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return re.sub(r"\s+", " ", str(v).strip())


def _area(responsavel: str) -> tuple[str, str]:
    t = responsavel or ""
    for pat, code, nome in _AREA_RULES:
        if re.search(pat, t, re.I):
            return code, nome
    if re.search(r"\bERS\b", t, re.I):
        return "ers", "Escritórios Regionais de Saúde"
    return "cievs", "UNIEVS/CIEVS — secretaria-executiva"


def _auto_class(raw: str) -> str:
    t = (raw or "").lower()
    if "manual" in t:
        return "manual"
    if "semi" in t:
        return "semiautomatico"
    if "auto" in t:
        return "automatico"
    return "semiautomatico"


def _tipo(raw: str) -> str:
    t = (raw or "").lower()
    if "risco" in t or "gatilho" in t:
        return "risco_gatilho"
    if "capacidade" in t or "prontid" in t:
        return "capacidade"
    if "resultado" in t:
        return "resultado"
    return "execucao"


def load_xlsx(path: Path) -> dict:
    matriz = pd.read_excel(path, sheet_name="Matriz_ARARA")
    acoes = pd.read_excel(path, sheet_name="Acoes_Originais")
    indicadores = []
    for _, row in matriz.iterrows():
        resp = _txt(row.get("Responsável"))
        area_id, area_nome = _area(resp)
        auto_raw = _txt(row.get("Automação"))
        indicadores.append(
            {
                "id": _txt(row.get("ID ARARA")),
                "linha_origem": int(row["Linha origem"]) if pd.notna(row.get("Linha origem")) else None,
                "eixo": _txt(row.get("Eixo")),
                "meta": _txt(row.get("Meta original")),
                "acao": _txt(row.get("Ação original")),
                "responsavel_texto": resp,
                "area_id": area_id,
                "area_nome": area_nome,
                "prazo_original": _txt(row.get("Prazo original")),
                "prioridade": _txt(row.get("Prioridade")) or "Alta",
                "tipo": _tipo(_txt(row.get("Tipo"))),
                "indicador": _txt(row.get("Indicador ARARA proposto")),
                "formula": _txt(row.get("Fórmula / regra de cálculo")),
                "meta_gatilho": _txt(row.get("Meta / gatilho")),
                "unidade": _txt(row.get("Unidade")),
                "direcao": _txt(row.get("Direção")),
                "fonte": _txt(row.get("Fonte primária sugerida")),
                "periodicidade": _txt(row.get("Periodicidade")),
                "automacao": _auto_class(auto_raw),
                "automacao_detalhe": auto_raw,
                "viabilidade": _txt(row.get("Viabilidade ARARA")),
                "semaforo": _txt(row.get("Regra de semáforo / gatilho")),
                "evidencia_minima": _txt(row.get("Evidência mínima")),
            }
        )
    acoes_out = []
    for _, row in acoes.iterrows():
        resp = _txt(row.get("Responsável"))
        area_id, area_nome = _area(resp)
        acoes_out.append(
            {
                "linha_fonte": int(row["Linha fonte"]) if pd.notna(row.get("Linha fonte")) else None,
                "meta": _txt(row.get("Meta")),
                "acao": _txt(row.get("Ação")),
                "responsavel_texto": resp,
                "area_id": area_id,
                "area_nome": area_nome,
                "prazo": _txt(row.get("Prazo")),
                "prioridade": _txt(row.get("Prioridade")) or "Alta",
                "status_inicial": _txt(row.get("Status inicial")),
            }
        )
    return {
        "plano": {
            "id": "plano-el-nino-ses-mt-2026-2027",
            "nome": "Plano Estadual El Niño 2026–2027 — SES-MT",
            "secretaria_executiva": "UNIEVS/CIEVS",
            "base_legal": "Portaria n.º 0590/2026/GBSES",
            "fonte_planilha": path.name,
        },
        "totais": {
            "acoes_originais": len(acoes_out),
            "indicadores": len(indicadores),
            "automaticos": sum(1 for i in indicadores if i["automacao"] == "automatico"),
            "semiautomaticos": sum(1 for i in indicadores if i["automacao"] == "semiautomatico"),
            "manuais": sum(1 for i in indicadores if i["automacao"] == "manual"),
        },
        "acoes": acoes_out,
        "indicadores": indicadores,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--xlsx",
        default=r"C:\Users\Menandesneto\Downloads\Controle_Indicacoes_El_Nino_SES_MT_2026.xlsx",
    )
    args = ap.parse_args()
    src = Path(args.xlsx)
    if not src.exists():
        raise SystemExit(f"Planilha não encontrada: {src}")
    payload = load_xlsx(src)
    OUT_YAML.parent.mkdir(parents=True, exist_ok=True)
    OUT_YAML.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    t = payload["totais"]
    print(
        f"Catálogo gravado em {OUT_YAML} — "
        f"{t['acoes_originais']} ações, {t['indicadores']} indicadores "
        f"(auto={t['automaticos']}, semi={t['semiautomaticos']}, manual={t['manuais']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
