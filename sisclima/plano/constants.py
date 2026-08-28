# -*- coding: utf-8 -*-
"""Máquinas de status, modos de indicador e eventos de notificação do Plano El Niño."""
from __future__ import annotations

PRODUTO = "ARARAS MT"
PRODUTO_EXPANSAO = "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde"
PLANO_ID = "plano-el-nino-2026"

# Painel climático existente (não misturar com perfis do Plano).
NIVEIS_PAINEL_SALA = frozenset({"ses", "admin"})

PERFIS_PLANO: tuple[tuple[str, str], ...] = (
    ("admin_araras", "Administração ARARAS — catálogo, vínculos e auditoria"),
    ("secretaria_executiva_cievs", "Secretaria-executiva CIEVS — validação e Sala"),
    ("coordenador_area", "Coordenador de área — atualiza só a própria área"),
    ("tecnico_area", "Técnico de área — registra evidência da própria área"),
    ("gestor", "Gestor — leitura de briefing da Sala"),
    ("consulta", "Consulta — leitura sem evidência baixável"),
)

STATUS_ACAO: tuple[tuple[str, str], ...] = (
    ("nao_iniciada", "Não iniciada"),
    ("em_andamento", "Em andamento"),
    ("em_validacao", "Em validação"),
    ("concluida", "Concluída"),
    ("impedida", "Impedida"),
    ("suspensa", "Suspensa"),
    ("nao_aplicavel", "Não aplicável"),
)
STATUS_ACAO_SET = {k for k, _ in STATUS_ACAO}

STATUS_COR: dict[str, str] = {
    "nao_iniciada": "#6b7280",
    "em_andamento": "#1351B4",
    "em_validacao": "#d97706",
    "concluida": "#16803c",
    "impedida": "#dc2626",
    "suspensa": "#6d28d9",
    "nao_aplicavel": "#9ca3af",
}

# Transições permitidas na ação (histórico sempre append; a linha nova carrega o status).
TRANSICOES_STATUS: dict[str, frozenset[str]] = {
    "nao_iniciada": frozenset({"em_andamento", "impedida", "suspensa", "nao_aplicavel"}),
    "em_andamento": frozenset({"em_validacao", "impedida", "suspensa", "nao_aplicavel"}),
    "em_validacao": frozenset({"concluida", "em_andamento", "impedida"}),  # rejeição volta a em_andamento
    "concluida": frozenset({"em_andamento"}),  # reabertura excepcional
    "impedida": frozenset({"em_andamento", "suspensa", "nao_aplicavel"}),
    "suspensa": frozenset({"em_andamento", "nao_aplicavel"}),
    "nao_aplicavel": frozenset({"nao_iniciada", "em_andamento"}),
}

MODOS_INDICADOR: tuple[tuple[str, str], ...] = (
    ("automatico", "Automático — lido de sistema/fonte, sem digitação da área"),
    ("semiautomatico", "Semiautomático — sistema sugere; área confirma"),
    ("documental", "Documental — área envia evidência (SEI/PDF)"),
)
MODOS_INDICADOR_SET = {k for k, _ in MODOS_INDICADOR}

# Planilha-fonte: Classe de automação → modo ARARAS.
MAPA_MODO_PLANILHA: dict[str, str] = {
    "automatico": "automatico",
    "semiautomatico": "semiautomatico",
    "manual": "documental",
}

TIPOS_INDICADOR: tuple[tuple[str, str], ...] = (
    ("execucao", "Execução"),
    ("capacidade", "Capacidade/Prontidão"),
    ("resultado", "Resultado"),
    ("risco_gatilho", "Risco/Gatilho — não entra no % de implementação"),
)
TIPOS_NO_INDICE = frozenset({"execucao", "capacidade", "resultado"})

MAPA_TIPO_PLANILHA: dict[str, str] = {
    "execucao": "execucao",
    "capacidade/prontidao": "capacidade",
    "capacidade/prontidão": "capacidade",
    "resultado": "resultado",
    "risco/gatilho": "risco_gatilho",
}

SITUACAO_VALIDACAO: tuple[tuple[str, str], ...] = (
    ("informado", "Informado"),
    ("em_validacao", "Em validação"),
    ("validado", "Validado"),
    ("rejeitado", "Rejeitado"),
)
SITUACAO_VALIDACAO_SET = {k for k, _ in SITUACAO_VALIDACAO}

# informado → em_validacao → validado | rejeitado
TRANSICOES_VALIDACAO: dict[str, frozenset[str]] = {
    "informado": frozenset({"em_validacao"}),
    "em_validacao": frozenset({"validado", "rejeitado"}),
    "validado": frozenset(),
    "rejeitado": frozenset({"informado"}),  # nova atualização, nunca overwrite
}

CAMPOS_EVIDENCIA: tuple[str, ...] = (
    "tipo",
    "documento",
    "data",
    "area",
    "acao_id",
    "versao",
    "responsavel_envio",
    "uploaded_at",
    "situacao",
    "link_sei",
    "arquivo",
    "observacao",
)

EVENTOS_NOTIFICACAO: tuple[tuple[str, str, str], ...] = (
    ("nova_acao", "Nova ação atribuída à área", "email"),
    ("prazo_15d", "Prazo em 15 dias", "email"),
    ("prazo_7d", "Prazo em 7 dias", "email"),
    ("prazo_3d", "Prazo em 3 dias", "email"),
    ("vencido", "Prazo vencido", "email"),
    ("evidencia_enviada", "Evidência enviada", "email"),
    ("evidencia_rejeitada", "Evidência rejeitada", "email"),
    ("meta_atingida", "Meta atingida (após validação)", "email"),
    ("indicador_critico", "Indicador crítico / semáforo vermelho", "email"),
    ("escalonamento", "Escalonamento à Secretaria-executiva / Sala", "email"),
)

SITUACAO_EVIDENCIA = ("enviada", "em_validacao", "aceita", "rejeitada", "substituida")
