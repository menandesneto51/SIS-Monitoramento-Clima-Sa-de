# -*- coding: utf-8 -*-
"""Constantes editoriais do boletim semanal El Niño."""
from __future__ import annotations

INDISPONIVEL = "Dado indisponível nesta rodada."
NAO_CALCULADO = "Não calculado por ausência de dados suficientes."
NAO_APLICAVEL = "Indicador não aplicável nesta rodada."

SELLOBS = "OBSERVADO"
SELOBS = SELLOBS  # alias
SELPREV = "PREVISÃO OFICIAL"
SELPROJ = "PROJEÇÃO ARARAS ~7 DIAS"
SELSAZ = "CENÁRIO SAZONAL"
SELDERIV = "INDICADOR DERIVADO"
SELIND = "DADO INDISPONÍVEL"

# Título institucional atual (padrão). Alternativa da Sala de Situação: só após validação.
USAR_TITULO_SALA_SITUACAO = False
TITULO_PRODUTO_ATUAL = "RELATÓRIO SEMANAL EL NIÑO"
TITULO_SALA_SITUACAO = "BOLETIM SEMANAL DA SALA DE SITUAÇÃO SAÚDE E CLIMA"
SUBTITULO_SALA_SITUACAO = "El Niño 2026–2027 e eventos climáticos extremos"
UNIEVS_NOME_OFICIAL = (
    "Unidade de Informações Estratégicas de Vigilância em Saúde (UNIEVS/CIEVS-MT)"
)
SUBTITULO_INSTITUCIONAL = (
    "Sala de Situação da Unidade de Informações Estratégicas de "
    "Vigilância em Saúde (CIEVS-MT)"
)
# Denominação pública do satélite de referência INPE/Queimadas (código interno: AQUA_M-T).
FOGO_SATELITE_REFERENCIA_PUBLICO = (
    "satélite de referência do Programa Queimadas/INPE (sensor MODIS)"
)
FOGO_SATELITE_REFERENCIA_CURTO = "satélite de referência INPE"

NIVEIS_CLASSE_ORDEM = ["verde", "amarela", "laranja", "vermelha", "roxa"]

# Sigla → primeira expansão (minúsculas preservadas onde couber)
SIGLAS: dict[str, str] = {
    "INMET": "Instituto Nacional de Meteorologia (INMET)",
    "INPE": "Instituto Nacional de Pesquisas Espaciais (INPE)",
    "ANA": "Agência Nacional de Águas e Saneamento Básico (ANA)",
    "CEMADEN": "Centro Nacional de Monitoramento e Alertas de Desastres Naturais (CEMADEN)",
    "SGB": "Serviço Geológico do Brasil (SGB)",
    "SEDEC": "Secretaria Nacional de Proteção e Defesa Civil (SEDEC)",
    "CENSIPAM": "Centro Gestor e Operacional do Sistema de Proteção da Amazônia (CENSIPAM)",
    "NOAA": "National Oceanic and Atmospheric Administration (NOAA)",
    "TSM": "Temperatura da Superfície do Mar (TSM)",
    "SOI": "Índice de Oscilação Sul (SOI)",
    "ENSO": "El Niño–Oscilação Sul (ENSO)",
    "APCC": "APEC Climate Center (APCC)",
    "CPTEC": "Centro de Previsão de Tempo e Estudos Climáticos (CPTEC)",
    "FUNCEME": "Fundação Cearense de Meteorologia e Recursos Hídricos (FUNCEME)",
    "ASO": "agosto–setembro–outubro (ASO)",
    "PM2,5": "material particulado fino com diâmetro aerodinâmico de até 2,5 micrômetros (PM2,5)",
    "PM2.5": "material particulado fino com diâmetro aerodinâmico de até 2,5 micrômetros (PM2,5)",
    "UTCI": "*Universal Thermal Climate Index* (UTCI)",
    "APS": "Atenção Primária à Saúde (APS)",
    "CNES": "Cadastro Nacional de Estabelecimentos de Saúde (CNES)",
    "RENAME": "Relação Nacional de Medicamentos Essenciais (RENAME)",
    "PCDT": "Protocolos Clínicos e Diretrizes Terapêuticas (PCDT)",
    "SEMA-MT": "Secretaria de Estado de Meio Ambiente de Mato Grosso (SEMA-MT)",
    "SRAG": "Síndrome Respiratória Aguda Grave (SRAG)",
    "LACEN": "Laboratório Central de Saúde Pública (LACEN)",
    "LACEN-MT": "Laboratório Central de Saúde Pública de Mato Grosso (LACEN-MT)",
    "DDA": "Doença Diarreica Aguda (DDA)",
    "IQA": "Índice de Qualidade do Ar (IQA)",
    "ETA": "tempo estimado (ETA)",
    "CIEVS-MT": "Centro de Informações Estratégicas em Vigilância em Saúde de Mato Grosso (CIEVS-MT)",
    "CIEVS": "Centro de Informações Estratégicas em Vigilância em Saúde (CIEVS)",
    "SES-MT": "Secretaria de Estado de Saúde de Mato Grosso (SES-MT)",
    "SES": "Secretaria de Estado de Saúde (SES)",
    "SMS": "Secretaria Municipal de Saúde (SMS)",
    "SUS": "Sistema Único de Saúde (SUS)",
    "FUNAI": "Fundação Nacional dos Povos Indígenas (FUNAI)",
    "DSEI": "Distrito Sanitário Especial Indígena (DSEI)",
    "CEREST": "Centro de Referência em Saúde do Trabalhador (CEREST)",
    "SESAI": "Secretaria Especial de Saúde Indígena (SESAI)",
    "COSEMS-MT": "Conselho de Secretarias Municipais de Saúde de Mato Grosso (COSEMS-MT)",
    "VISAT": "Vigilância em Saúde do Trabalhador (VISAT)",
    "UNIEVS": UNIEVS_NOME_OFICIAL,
    "DPOC": "Doença Pulmonar Obstrutiva Crônica (DPOC)",
    "ARARAS": "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS)",
    "ARARAS MT": "Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde (ARARAS MT)",
    "Tmáx": "temperatura máxima (Tmáx)",
    "UR": "umidade relativa (UR)",
    "AMACRO": "AMACRO (Acre, Amazonas e Rondônia)",
}

HIDRO_LABEL: dict[str, str] = {
    "seca_baixa": "Sinal hidrológico de baixa disponibilidade (nível baixo)",
    "seca_moderada": "Sinal hidrológico de baixa disponibilidade (nível moderado)",
    "seca_alta": "Sinal hidrológico de baixa disponibilidade (nível alto)",
    "inundacao_alta": "Risco elevado de inundação",
    "inundacao_moderada": "Risco moderado de inundação",
    "normal": "Situação hidrológica habitual",
    "pendente_sql_dw": "Integração de dados ainda não disponível",
}

NIVEL_LEGENDA: dict[str, str] = {
    "verde": "Verde — situação favorável; monitoramento de rotina.",
    "amarela": "Amarela — atenção; acompanhar evolução e reforçar comunicação.",
    "laranja": "Laranja — alerta; preparação proporcional e articulação regional.",
    "vermelha": "Vermelha — alerta elevado; revisar capacidade assistencial e estoques.",
    "roxa": "Roxa — situação excepcional; mobilização proporcional e validação pela gestão.",
    "cinza": "Cinza — sem classificação operacional nesta rodada.",
}

REFERENCIAS_PADRAO: list[str] = [
    "INSTITUTO NACIONAL DE METEOROLOGIA; INSTITUTO NACIONAL DE PESQUISAS ESPACIAIS; "
    "AGÊNCIA NACIONAL DE ÁGUAS E SANEAMENTO BÁSICO; CENTRO NACIONAL DE MONITORAMENTO "
    "E ALERTAS DE DESASTRES NATURAIS; SERVIÇO GEOLÓGICO DO BRASIL; SECRETARIA NACIONAL "
    "DE PROTEÇÃO E DEFESA CIVIL; CENTRO GESTOR E OPERACIONAL DO SISTEMA DE PROTEÇÃO DA "
    "AMAZÔNIA. Painel El Niño 2026–2027, boletim mensal n.º 02. Brasília, jul. 2026.",
    "SECRETARIA DE ESTADO DE SAÚDE DE MATO GROSSO; CENTRO DE INFORMAÇÕES ESTRATÉGICAS "
    "EM VIGILÂNCIA EM SAÚDE DE MATO GROSSO. ARARAS MT — Análise, Resposta e "
    "Acompanhamento de Riscos, Agravos e Saúde. Cuiabá, 2026.",
]
