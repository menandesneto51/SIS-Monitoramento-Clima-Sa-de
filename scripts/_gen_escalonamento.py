# -*- coding: utf-8 -*-
"""Gera config/plano_el_nino_escalonamento.yaml a partir do Anexo A + catálogo."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CAT = ROOT / "config" / "plano_el_nino_2026_catalogo.yaml"
ANNEX = ROOT / "_annex_clean.json"
OUT = ROOT / "config" / "plano_el_nino_escalonamento.yaml"

CANON = {
    "ARARA-068": "IND-006",
    "ARARA-073": "IND-015",
    "ARARA-074": "IND-029",
}
OVERRIDE = {
    "ARARA-003": {"classe": "C", "perfil": "E1", "tipo_emergencia": "prontidao"},
    "ARARA-078": {"classe": "C", "perfil": "E9", "tipo_emergencia": "prontidao"},
    "ARARA-079": {"classe": "A", "perfil": "E3", "tipo_emergencia": "resultado"},
}
TIPO_MAP = {
    "Execução": "execucao",
    "Capacidade/Prontidão": "prontidao",
    "Resultado": "resultado",
    "Risco/Gatilho": "risco_gatilho",
}
AUTO_MAP = {
    "Automático": "automatico",
    "Semiautomático": "semiautomatico",
    "Manual": "documental",
}
CAD = {
    "E1": {"verde": "mensal", "amarelo": "72h", "laranja": "diario", "vermelho": "12-24h", "roxo": "periodo_operacional"},
    "E2": {"verde": "semanal_mensal", "amarelo": "72h", "laranja": "diario", "vermelho": "12-24h", "roxo": "6-12h"},
    "E3": {"verde": "preventivo", "amarelo": "alerta_prioritario", "laranja": "diario", "vermelho": "a_cada_mudanca", "roxo": "continuo"},
    "E4": {"verde": "estoque_minimo", "amarelo": "72h", "laranja": "diario", "vermelho": "12h", "roxo": "turno"},
    "E5": {"verde": "baseline", "amarelo": "prontidao", "laranja": "diario", "vermelho": "12-24h", "roxo": "continuo"},
    "E6": {"verde": "norma_cadastro", "amarelo": "orientar_visa", "laranja": "24-48h", "vermelho": "fiscalizacao_focal", "roxo": "risco_essencial"},
    "E7": {"verde": "plano_amostral", "amarelo": "ampliar_vulneraveis", "laranja": "24-48h", "vermelho": "diario", "roxo": "humanitario"},
    "E8": {"verde": "rede_frio", "amarelo": "autonomia_prioritarios", "laranja": "diario", "vermelho": "12-24h", "roxo": "servico_essencial"},
    "E9": {"verde": "perfis", "amarelo": "grupos_expostos", "laranja": "vigilancia_ativa", "vermelho": "eventos_rapidos", "roxo": "equipes_resposta"},
    "E10": {"verde": "camadas", "amarelo": "72h", "laranja": "busca_ativa_pai", "vermelho": "protecao_integrada", "roxo": "humanitario"},
    "E11": {"verde": "simulado", "amarelo": "checklist_prontidao", "laranja": "licoes_durante", "vermelho": "corretivas", "roxo": "pos_incidente"},
    "E12": {"verde": "baseline", "amarelo": "sinal_precoce", "laranja": "ativacao_comando", "vermelho": "resposta_ampliada", "roxo": "mobilizacao_maxima"},
    "E13": {"verde": "matriz_decisao", "amarelo": "pai_simplificado", "laranja": "pai_completo_diario", "vermelho": "12-24h", "roxo": "periodo_operacional"},
    "E14": {"verde": "cadastro_territorial", "amarelo": "72h", "laranja": "diario", "vermelho": "12-24h", "roxo": "coordenacao_continua"},
    "E15": {"verde": "disponibilidade", "amarelo": "backup", "laranja": "suporte_prioritario", "vermelho": "24x7", "roxo": "contingencia_maxima"},
}
PEND_B = {
    "IND-041": "Homologar universo de estabelecimentos-alvo e meta de fiscalização no período crítico.",
    "IND-049": "Homologar universo de EAS/EIS-alvo para sinantrópicos.",
    "IND-053": "Pactuar SLA de denúncias prioritárias (COVSAN).",
    "IND-075": "Validar limiar técnico de positividade de ovitrampas.",
    "IND-076": "Validar regra oficial do IDO.",
    "IND-077": "Validar IIP/Breteau e fonte LIRAa/LIA.",
    "IND-080": "Definir denominador de municípios prioritários COVSAT.",
}
PERFIS = {
    "E1": "Governança e articulação",
    "E2": "Monitoramento e inteligência",
    "E3": "Comunicação e alerta",
    "E4": "Logística e recursos",
    "E5": "Assistência e serviços",
    "E6": "Vigilância sanitária",
    "E7": "Água / VIGIÁGUA",
    "E8": "Imunização e Rede de Frio",
    "E9": "Saúde do trabalhador",
    "E10": "Vulnerabilidade",
    "E11": "Simulado e melhoria",
    "E12": "Gatilho de risco (não é meta)",
    "E13": "Gestão da resposta / PAI",
    "E14": "Gestão territorial",
    "E15": "Sistema e continuidade digital",
}
CIEVS = [
    ("CIEVS-01", "Sala com pontos focais designados", "C", "E1", "prontidao"),
    ("CIEVS-02", "Fluxo da Sala formalizado e vigente", "C", "E1", "prontidao"),
    ("CIEVS-03", "ERS com contato da Sala atualizado", "B", "E1", "prontidao"),
    ("CIEVS-04", "Briefing da Sala no prazo do estágio", "A", "E13", "execucao"),
    ("CIEVS-05", "SitRep emitido no prazo do estágio", "A", "E13", "execucao"),
    ("CIEVS-06", "Decisões da Sala com responsável e prazo", "A", "E13", "execucao"),
    ("CIEVS-07", "Decisões concluídas no prazo", "A", "E13", "resultado"),
    ("CIEVS-08", "Pendências críticas em aberto", "A", "E13", "resultado"),
    ("CIEVS-09", "Pendências críticas vencidas", "A", "E13", "resultado"),
    ("CIEVS-10", "Tempo de deliberação da Sala", "B", "E13", "resultado"),
    ("CIEVS-11", "Avaliações de risco no prazo", "A", "E2", "execucao"),
    ("CIEVS-12", "Latência da análise de risco", "A", "E2", "resultado"),
    ("CIEVS-13", "Territórios com avaliação de risco válida", "A", "E2", "capacidade"),
    ("CIEVS-14", "Alertas emitidos no SLA", "A", "E3", "execucao"),
    ("CIEVS-15", "Confirmação de recebimento dos alertas", "B", "E3", "resultado"),
    ("CIEVS-16", "Oportunidade dos alertas ao evento", "A", "E3", "resultado"),
    ("CIEVS-17", "Municípios prioritários acompanhados", "A", "E14", "execucao"),
    ("CIEVS-18", "Demandas territoriais em fila atualizada", "A", "E14", "execucao"),
    ("CIEVS-19", "Produtos da Sala publicados no período", "A", "E2", "execucao"),
    ("CIEVS-20", "Fontes críticas com dado válido", "A", "E2", "capacidade"),
    ("CIEVS-21", "Completude das fontes da Sala", "A", "E2", "resultado"),
    ("CIEVS-22", "Mensagens de risco no prazo", "A", "E3", "execucao"),
    ("CIEVS-23", "Alcance da comunicação de risco", "A", "E3", "resultado"),
    ("CIEVS-24", "PAI vigente a partir do Amarelo", "A", "E13", "execucao"),
    ("CIEVS-25", "Ações do PAI atualizadas no SLA", "A", "E13", "resultado"),
    ("CIEVS-26", "Escalonamentos registrados e rastreados", "A", "E13", "execucao"),
    ("CIEVS-27", "Checklist de prontidão da Sala", "C", "E11", "prontidao"),
    ("CIEVS-28", "Lições e ações corretivas registradas", "A", "E11", "execucao"),
    ("CIEVS-29", "Trilha de auditoria das decisões", "A", "E13", "execucao"),
    ("CIEVS-30", "Disponibilidade operacional do ARARAS", "C", "E15", "prontidao"),
]


def main() -> None:
    cat = yaml.safe_load(CAT.read_text(encoding="utf-8"))
    annex = json.loads(ANNEX.read_text(encoding="utf-8"))
    by_arara: dict[str, dict] = {}
    for r in annex:
        iid = str(r.get("id") or "")
        if not iid.startswith("ARARA-"):
            continue
        if r.get("classe") not in {"A", "B", "C", "D"}:
            continue
        by_arara.setdefault(iid, r)

    indicadores = []
    for item in cat.get("indicadores") or []:
        iid = str(item.get("id") or "")
        src = str(item.get("codigo_fonte") or item.get("codigo_fonte") or "")
        ax = by_arara.get(src) or {}
        ov = OVERRIDE.get(src) or {}
        classe = ov.get("classe") or ax.get("classe") or "A"
        perfil = ov.get("perfil") or ax.get("perfil") or "E2"
        tipo_em = ov.get("tipo_emergencia") or TIPO_MAP.get(ax.get("tipo") or "", "execucao")
        rec = {
            "id": iid,
            "codigo_fonte": src,
            "classe_emergencia": classe,
            "perfil_escalonamento": perfil,
            "tipo_emergencia": tipo_em,
            "gate_prontidao": classe == "C",
            "cadencia_por_estagio": dict(CAD.get(perfil) or CAD["E2"]),
            "automacao_relatorio": AUTO_MAP.get(ax.get("automacao") or "", item.get("modo_atualizacao")),
        }
        if PEND_B.get(iid):
            rec["pendencia_parametro"] = PEND_B[iid]
        if CANON.get(src):
            rec["id_canonico"] = CANON[src]
        indicadores.append(rec)

    cievs = []
    for cid, nome, classe, perfil, tipo in CIEVS:
        cievs.append(
            {
                "id": cid,
                "nome": nome,
                "classe_emergencia": classe,
                "perfil_escalonamento": perfil,
                "tipo_emergencia": tipo,
                "gate_prontidao": classe == "C",
                "cadencia_por_estagio": dict(CAD.get(perfil) or CAD["E13"]),
                "pendencia_parametro": (
                    "Definir denominador de ERS/contatos da Sala."
                    if cid == "CIEVS-03"
                    else "Pactuar SLA de deliberação da Sala."
                    if cid == "CIEVS-10"
                    else "Definir meio de confirmação de recebimento do alerta."
                    if cid == "CIEVS-15"
                    else None
                ),
            }
        )
        if cievs[-1]["pendencia_parametro"] is None:
            cievs[-1].pop("pendencia_parametro")

    doc = {
        "versao": "1.0",
        "fonte": "Relatorio_Avaliacao_Escalonamento_Indicadores_ARARA_El_Nino_2026_2027.docx",
        "produto": "ARARAS",
        "nota": (
            "ARARA-xxx é codigo_fonte. IDs oficiais no sistema: IND-xxx. "
            "Limiares da classe B não foram inventados — pendem homologação CIEVS. "
            "Estágio de ativação é decisão do Comando, independente do nível de risco."
        ),
        "estagios": ["verde", "amarelo", "laranja", "vermelho", "roxo"],
        "classes": {
            "A": "Pronto para operação escalável",
            "B": "Usável após parametrizar SLA/limiar/denominador",
            "C": "Gate de prontidão — não é KPI isolado de crise",
            "D": "Alias; usar id_canonico",
        },
        "pesos_completude": {
            "fonte": 25,
            "atualidade": 25,
            "numerador": 20,
            "denominador": 15,
            "evidencia": 10,
            "responsavel": 5,
        },
        "limiares_completude": {
            "calculavel": 95,
            "ressalva": 80,
        },
        "duplicidades": [
            {"id": "IND-068", "id_canonico": "IND-006", "codigo_fonte": "ARARA-068"},
            {"id": "IND-073", "id_canonico": "IND-015", "codigo_fonte": "ARARA-073"},
            {"id": "IND-074", "id_canonico": "IND-029", "codigo_fonte": "ARARA-074"},
        ],
        "perfis": {k: {"nome": v, "cadencia_por_estagio": CAD[k]} for k, v in PERFIS.items()},
        "indicadores": indicadores,
        "indicadores_cievs": cievs,
    }
    OUT.write_text(
        "# Escalonamento operacional do Plano El Niño no ARARAS.\n"
        "# Homologação CIEVS dos 7 itens B (pendencia_parametro) ainda aberta.\n"
        + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    c = Counter(i["classe_emergencia"] for i in indicadores)
    print("wrote", OUT, "n=", len(indicadores), dict(c), "cievs", len(cievs))


if __name__ == "__main__":
    main()
