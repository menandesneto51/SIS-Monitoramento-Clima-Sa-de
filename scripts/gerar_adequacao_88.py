# -*- coding: utf-8 -*-
"""Gera config/plano_el_nino_adequacao.yaml a partir do texto extraído da proposta 28/08/2026."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tmp" / "_proposta_88.txt"
OUT = ROOT / "config" / "plano_el_nino_adequacao.yaml"

PAPEIS = {
    "operacional": "operacional",
    "preparação": "preparacao",
    "preparacao": "preparacao",
    "gatilho": "gatilho",
    "híbrido": "hibrido",
    "hibrido": "hibrido",
    "alias": "alias",
}

CADENCIA_S = {
    "S1": {
        "nome": "Governança/coordenação",
        "verde": "mensal",
        "amarelo": "semanal",
        "laranja": "diario_24h",
        "vermelho": "12h",
        "roxo": "6h_periodo",
    },
    "S2": {
        "nome": "Inteligência/análise",
        "verde": "mensal_semanal",
        "amarelo": "72h",
        "laranja": "diario_24h",
        "vermelho": "12h",
        "roxo": "6h_periodo",
    },
    "S3": {
        "nome": "Vigilância ambiental/epidemiológica",
        "verde": "rotina",
        "amarelo": "semanal_72h",
        "laranja": "diaria_48h",
        "vermelho": "24h",
        "roxo": "12h",
    },
    "S4": {
        "nome": "Assistência/capacidade",
        "verde": "mensal",
        "amarelo": "semanal",
        "laranja": "diario",
        "vermelho": "12h",
        "roxo": "6h_turno",
    },
    "S5": {
        "nome": "Logística/estoque",
        "verde": "semanal_mensal",
        "amarelo": "72h",
        "laranja": "24h",
        "vermelho": "12h",
        "roxo": "6h",
    },
    "S6": {
        "nome": "Comunicação",
        "verde": "materiais_prontos",
        "amarelo": "alerta_24h",
        "laranja": "12h",
        "vermelho": "6h",
        "roxo": "2h_periodo",
    },
    "S7": {
        "nome": "Vigilância Sanitária",
        "verde": "rotina",
        "amarelo": "semanal_dirigida",
        "laranja": "48h",
        "vermelho": "24h",
        "roxo": "12h",
    },
    "S8": {
        "nome": "Imunização/Rede de Frio",
        "verde": "semanal_mensal",
        "amarelo": "48h",
        "laranja": "24h",
        "vermelho": "12h",
        "roxo": "6h",
    },
    "S9": {
        "nome": "Saúde do Trabalhador",
        "verde": "mensal_trimestral",
        "amarelo": "semanal",
        "laranja": "48h",
        "vermelho": "24h",
        "roxo": "12h",
    },
    "S10": {
        "nome": "Prontidão/documento/simulado",
        "verde": "concluir_100",
        "amarelo": "revalidar_72h",
        "laranja": "somente_validade",
        "vermelho": "somente_validade",
        "roxo": "somente_validade",
    },
    "S11": {
        "nome": "Gatilho de risco",
        "verde": "baseline",
        "amarelo": "aumentar_frequencia",
        "laranja": "diario_fonte",
        "vermelho": "12_24h",
        "roxo": "6_12h",
    },
    "S12": {
        "nome": "Evento/SLA",
        "verde": "sla_ordinario",
        "amarelo": "48h",
        "laranja": "24h",
        "vermelho": "12h",
        "roxo": "6h_critico_2h",
    },
}

PADROES_C = {
    "C1": "percentual_cobertura",
    "C2": "documento_gate",
    "C3": "sla_tempo",
    "C4": "risco_gatilho",
    "C5": "indice_capacidade",
    "C6": "estoque_autonomia",
    "C7": "evento_resposta",
    "C8": "capacitacao_simulado",
}

CANONICOS = {
    "ARARA-068": "IND-006",
    "ARARA-073": "IND-015",
    "ARARA-074": "IND-029",
}


def _parse_blocks(text: str) -> list[dict]:
    parts = re.split(r"(?=ARARA-\d{3}L\d+)", text)
    out = []
    for part in parts:
        m = re.match(r"ARARA-(\d{3})L(\d+)\s*\n(.*)", part, re.S)
        if not m:
            continue
        num, linha, rest = m.group(1), m.group(2), m.group(3).strip()
        lines = [ln.strip() for ln in rest.splitlines() if ln.strip()]
        if len(lines) < 5:
            continue
        papel_raw = lines[0].casefold()
        papel = PAPEIS.get(papel_raw)
        if not papel:
            continue
        atual, decisao, ajustado = lines[1], lines[2], lines[3]
        alteracao = " ".join(lines[4:])
        sm = re.search(r"S(\d+)\s*·\s*C(\d+)", alteracao)
        perfil = f"S{sm.group(1)}" if sm else ""
        padrao = f"C{sm.group(2)}" if sm else ""
        auto = ""
        if sm:
            auto = alteracao[sm.end() :].lstrip(" ·").strip()
            auto = re.split(r"\s*ID / linha\b", auto)[0].strip()
        codigo = f"ARARA-{num}"
        item = {
            "id": f"IND-{num}",
            "codigo_fonte": codigo,
            "linha_fonte": int(linha),
            "papel": papel,
            "nome_atual": atual,
            "decisao": decisao,
            "nome_ajustado": ajustado,
            "alteracao": alteracao[: sm.start()].strip() if sm else alteracao,
            "perfil_s": perfil,
            "padrao_completude": padrao,
            "alvo_automacao": auto,
        }
        if codigo in CANONICOS:
            item["id_canonico"] = CANONICOS[codigo]
            item["papel"] = "alias"
        if codigo == "ARARA-062":
            item["subindicadores"] = [
                {
                    "id": "IND-062A",
                    "codigo_fonte": "ARARA-062A",
                    "nome": "Domicílios pesquisados com triatomíneos versus baseline",
                    "papel": "gatilho",
                    "perfil_s": "S11",
                    "padrao_completude": "C4",
                },
                {
                    "id": "IND-062B",
                    "codigo_fonte": "ARARA-062B",
                    "nome": "Ocorrências/presença de peçonhentos versus universo definido",
                    "papel": "gatilho",
                    "perfil_s": "S11",
                    "padrao_completude": "C4",
                },
            ]
        out.append(item)
    return out


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    indicadores = _parse_blocks(text)
    seen = {i["id"] for i in indicadores}
    missing = [f"IND-{n:03d}" for n in range(1, 89) if f"IND-{n:03d}" not in seen]
    papeis = {}
    for i in indicadores:
        papeis[i["papel"]] = papeis.get(i["papel"], 0) + 1
    data = {
        "versao": "28-08-2026",
        "fonte": "Proposta_Adequacao_88_Indicadores_ARARAS_Sala_Situacao_28-08-2026.docx",
        "nota": (
            "Preserva os 88 IDs. Aliases não calculam. Gatilho não entra no índice de execução. "
            "Sem dado nunca vira 0. Denominador 0 = N/A."
        ),
        "deliberacoes": [
            "Separar nível de risco, estágio de resposta, desempenho e completude.",
            "Parametrizar periodicidade/SLA pelos perfis S1–S12.",
            "ARARA-068, 073 e 074 são aliases sem cálculo próprio.",
            "Documentos/protocolos/planos/simulados são gates de prontidão.",
            "Gatilhos de risco não integram o Índice de Implementação.",
            "Completude: NÃO CALCULÁVEL se faltar campo crítico; denom 0 = N/A.",
            "PAI automático a partir do Amarelo (gatilho, SLA, pendência crítica, interrupção).",
        ],
        "perfis_s": CADENCIA_S,
        "padroes_completude": {
            "C1": {
                "nome": "Percentual/cobertura",
                "campos": "numerador + denominador válido + território + período + fonte/data. Denom 0 = N/A.",
            },
            "C2": {
                "nome": "Documento/gate",
                "campos": "documento/link + versão + aprovação + vigência + responsável.",
            },
            "C3": {
                "nome": "SLA/tempo",
                "campos": "abertura + fechamento/primeira ação + prioridade + estágio + responsável + desfecho. P50/P90.",
            },
            "C4": {
                "nome": "Risco/gatilho",
                "campos": "valor + baseline/limiar versionado + território + período + frescura. Sem 'meta atingida'.",
            },
            "C5": {
                "nome": "Índice/capacidade composta",
                "campos": "componentes + pesos + versão do algoritmo. Componente crítico ausente = incompleto, não zero.",
            },
            "C6": {
                "nome": "Estoque/autonomia",
                "campos": "item + saldo + consumo médio + mínimo por estágio + local + timestamp.",
            },
            "C7": {
                "nome": "Evento/resposta",
                "campos": "evento + território/unidade + ação + responsável + timestamp + status/evidência.",
            },
            "C8": {
                "nome": "Capacitação/simulado",
                "campos": "universo-alvo + cobertos + data + validade + evidência + plano de melhoria.",
            },
        },
        "resumo": {
            "n": len(indicadores),
            "por_papel": papeis,
            "faltando": missing,
        },
        "indicadores": indicadores,
    }
    OUT.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8",
    )
    print("n", len(indicadores), "papeis", papeis, "faltando", missing)


if __name__ == "__main__":
    main()
