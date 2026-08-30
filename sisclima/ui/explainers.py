# -*- coding: utf-8 -*-
"""Textos explicativos para leitores leigos do painel ARARAS."""
from __future__ import annotations

LEVEL_GUIDE: dict[str, dict[str, str]] = {
    "verde": {
        "titulo": "Verde — situação sob controle",
        "o_que_e": "Os indicadores climáticos e de saúde estão em faixa habitual para o município.",
        "o_que_fazer": "Manter monitoramento de rotina. Não exige mobilização especial.",
        "analogia": "Como um semáforo verde: pode seguir, mas continue olhando o painel.",
    },
    "amarela": {
        "titulo": "Amarela — atenção",
        "o_que_e": "Há sinais de calor, ar ou saúde acima do esperado. Ainda não é emergência.",
        "o_que_fazer": "Reforçar vigilância climática e de SRAG/arboviroses. Comunicar a regional.",
        "analogia": "Semáforo amarelo: reduza a velocidade e observe com mais cuidado.",
    },
    "laranja": {
        "titulo": "Laranja — alerta",
        "o_que_e": "Pressão relevante de calor e/ou indicadores de saúde. Prioridade operacional.",
        "o_que_fazer": "Articular regional e assistência. Revisar estoques e plantão.",
        "analogia": "Alerta: prepare a equipe e acompanhe o município de perto.",
    },
    "vermelha": {
        "titulo": "Vermelha — resposta intensificada",
        "o_que_e": "Condições críticas de calor e/ou carga sanitária elevada.",
        "o_que_fazer": "Sala de situação, reforço de comunicação à população e apoio assistencial.",
        "analogia": "Situação grave: ação coordenada imediata.",
    },
    "roxa": {
        "titulo": "Roxa — situação excepcional",
        "o_que_e": "Nível máximo do ARARAS: múltiplos gatilhos ao mesmo tempo.",
        "o_que_fazer": "Mobilização plena do CIEVS e articulação estadual.",
        "analogia": "Prioridade absoluta nesta rodada do painel.",
    },
    "cinza": {
        "titulo": "Cinza — dados incompletos",
        "o_que_e": "Faltam informações suficientes para classificar com segurança.",
        "o_que_fazer": "Verificar fontes e atualizar o pipeline antes de decidir.",
        "analogia": "Painel sem leitura clara — não interprete como ‘tudo bem’.",
    },
}

HOW_TO_READ_PUBLIC = [
    "1. Abra a aba Visão: faixa de nível, cards do recorte e o mapa de risco de 3 dias.",
    "2. Filtre regional ou município no topo — o recorte vale para todas as abas.",
    "3. Em Mapas, compare calor, fumaça, vulnerabilidade e a predição de 7 dias.",
    "4. Em Território, confira a malha municipal e as populações vulneráveis.",
    "5. Em Qualidade do ar, veja PM2,5, IQA e focos de queimadas.",
    "6. Em Série ambiental, compare a janela atual com a série histórica de calor/ar.",
    "7. Em Arboviroses, acompanhe dengue, zika e chikungunya (casos 7 dias e mapa).",
    "8. Em Óbitos e clima, veja a série SIM sensível ao calor e a metodologia.",
    "9. Em Cemaden / ANA, veja alertas de desastre, nível de rio e chuva.",
    "10. Em Sazonalidade / OR, compare o mês atual com o histórico e o odds ratio ecológico.",
    "11. Em Cálculos, leia como cada indicador publicado é composto.",
]

GLOSSARIO_PUBLICO = [
    "nivel",
    "tmax",
    "utci_proxy",
    "risco_cumulativo_3d",
    "indice_tensao_climatica",
    "indice_carga_saude",
    "indice_vigilancia_integrada",
    "indice_prioridade_global",
    "faixa_prioridade_global",
    "tendencia_7d",
    "tendencia_prioridade_7d",
    "pressao_calor_pct",
    "indice_pressao_saude",
    "ocupacao_leitos_pct",
    "pm25_ugm3",
    "iq_ar_score",
    "qualidade_ar_nivel",
    "focos_queimadas_7d",
    "focos_queimadas_24h",
    "nivel_queimadas",
    "indice_vulnerabilidade_calor",
    "casos_arbovirus_7d",
    "incidencia_arbovirus_100k",
    "risco_vetorial_climatico",
    "indice_saturacao_solo",
    "situacao_hidro",
    "indice_sazonal",
    "odds_ratio",
]

INDICATOR_GLOSSARY: dict[str, dict[str, str]] = {
    "nivel": {
        "nome": "Nível operacional",
        "leigo": "Resumo colorido da gravidade do município hoje (Verde → Roxa).",
        "como_ler": "Quanto mais escuro/alto o nível, maior a prioridade para o CIEVS.",
    },
    "score": {
        "nome": "Score operacional",
        "leigo": "Nota numérica que acompanha o nível (quanto maior, mais crítico).",
        "como_ler": "Use para ranquear municípios no mesmo nível.",
    },
    "tmax": {
        "nome": "Temperatura máxima (Tmax)",
        "leigo": "Maior temperatura do dia no município (°C).",
        "como_ler": "Acima de ~35 °C já exige atenção a grupos vulneráveis.",
    },
    "utci_proxy": {
        "nome": "UTCI proxy",
        "leigo": "Estimativa de ‘como o corpo sente’ o calor (não só o termômetro).",
        "como_ler": "Valores altos indicam estresse térmico mesmo com Tmax moderada.",
    },
    "risco_cumulativo_3d": {
        "nome": "Risco cumulativo 3 dias",
        "leigo": "Soma do estresse térmico dos últimos 3 dias — calor que ‘acumula’.",
        "como_ler": "Útil para ondas de calor: um dia quente é diferente de três seguidos.",
    },
    "pressao_calor_pct": {
        "nome": "Pressão assistencial (proxy clima)",
        "leigo": "Proxy clima+saúde quando se quer um sinal único; não é censo de leitos nem fila SISREG.",
        "como_ler": "Não substitua ocupação IndicaSUS nem solicitações SISREG por este número.",
    },
    "ocupacao_leitos_pct": {
        "nome": "Ocupação hospitalar (IndicaSUS)",
        "leigo": "% de leitos ocupados no BdSES/IndicaSUS, só onde há unidade notificante.",
        "como_ler": "‘—’ ou SEM_LEITOS = município sem hospital/leitos no IndicaSUS (normal). Não inventamos ocupação.",
    },
    "fonte_ocupacao": {
        "nome": "Fonte da ocupação",
        "leigo": "INDICASUS_TEMPO_REAL (censo) ou SEM_LEITOS_INDICASUS (sem unidade notificante).",
        "como_ler": "Não use SISREG como fonte de ocupação_pct.",
    },
    "indice_pressao_saude": {
        "nome": "Índice de pressão em saúde",
        "leigo": "Nota 0–100 composta: ocupação (se houver) + pressão SISREG + SINAN + SIM.",
        "como_ler": "Verde ≤39, amarela 40–69, vermelha ≥70. Sem IndicaSUS, o peso da ocupação é redistribuído.",
    },
    "kpi_sisreg_solicitacoes": {
        "nome": "Pressão hospitalar SISREG (solicitações)",
        "leigo": "Volume de solicitações/fila de regulação no município (demanda).",
        "como_ler": "Serve para todos os municípios que usam a Central — distinto da % de leitos ocupados.",
    },
    "kpi_sisreg_fila_h": {
        "nome": "Fila SISREG (horas)",
        "leigo": "Tempo médio de espera na regulação, quando a base live informar.",
        "como_ler": "Pressão de acesso, não ocupação de leito.",
    },
    "semaforo_pressao": {
        "nome": "Semáforo de pressão",
        "leigo": "Verde / amarela / vermelha — leitura rápida da pressão assistencial-epidemiológica.",
        "como_ler": "Não confundir com o nível operacional de 5 cores (até roxa).",
    },
    "tendencia_pressao_7d": {
        "nome": "Tendência da pressão (7 dias)",
        "leigo": "Se a pressão deve subir, ficar estável ou cair na próxima semana.",
        "como_ler": "↑ alta · → estável · ↓ queda — compara índice atual × previsão 7d.",
    },
    "pm25_ugm3": {
        "nome": "PM2,5",
        "leigo": "Partículas finas no ar (fumaça/poeira) que entram fundo no pulmão.",
        "como_ler": "Valores altos preocupam asma, idosos e crianças — comum em queimadas.",
    },
    "casos_arbovirus_7d": {
        "nome": "Casos de arboviroses (7 dias)",
        "leigo": "Notificações de dengue, zika, chikungunya e correlatas na última semana.",
        "como_ler": "Janela curta — mostra a pressão recente, não a temporada inteira.",
    },
    "incidencia_arbovirus_100k": {
        "nome": "Incidência de arboviroses / 100 mil",
        "leigo": "Casos proporcionais à população, para comparar municípios grandes e pequenos.",
        "como_ler": "Use a incidência (não só o número absoluto) para comparar o território.",
    },
    "qualidade_ar_nivel": {
        "nome": "Nível da qualidade do ar",
        "leigo": "Faixa da qualidade do ar a partir dos poluentes disponíveis no município.",
        "como_ler": "Quanto pior a faixa, maior a atenção a asma, idosos e crianças.",
    },
    "situacao_hidro": {
        "nome": "Situação hidrológica (ANA)",
        "leigo": "Leitura de seca, normalidade ou risco de cheia no rio próximo ao município.",
        "como_ler": "Cruze com os alertas do Cemaden e com a chuva recente. Sem dado ≠ risco zero.",
    },
    "focos_queimadas_7d": {
        "nome": "Focos de queimadas AQUA_M-T (7 dias)",
        "leigo": "Focos de calor do satélite de referência AQUA_M-T (INPE/BDQueimadas) no município na última semana.",
        "como_ler": "Comparável ao Portal Queimadas. ≥20 amarelo/laranja · ≥50 vermelho · ≥120 roxo — cruzar com PM2,5 e SRAG.",
    },
    "focos_queimadas_24h": {
        "nome": "Focos de queimadas AQUA_M-T (24 h)",
        "leigo": "Focos AQUA_M-T no último dia — sinal quase em tempo real de fogo ativo.",
        "como_ler": "Pico diário ajuda a priorizar comunicação e atenção respiratória imediata.",
    },
    "deteccoes_queimadas_7d": {
        "nome": "Detecções multi-satélite (7 dias)",
        "leigo": "Soma de detecções de todos os satélites do CSV INPE (GOES, NPP, NOAA etc.). Não equivale a focos distintos.",
        "como_ler": "Usar como sensibilidade/contexto; o indicador oficial de focos é AQUA_M-T.",
    },
    "nivel_queimadas": {
        "nome": "Nível operacional de queimadas",
        "leigo": "Semáforo Verde→Roxa baseado nos focos AQUA_M-T (independente do nível climático geral).",
        "como_ler": "Use junto com qualidade do ar — muitos focos sem PM2,5 ainda exigem atenção.",
    },
    "onda_fria_2d": {
        "nome": "Onda de frio (≥2 dias)",
        "leigo": "Tmín abaixo do limiar de alerta por dois ou mais dias seguidos.",
        "como_ler": "1 = evento em curso — reforçar abrigo e vigilância de pneumonia/COPD.",
    },
    "severidade_onda_fria": {
        "nome": "Severidade da onda de frio (0–4)",
        "leigo": "Intensidade do frio extremo com base na Tmín e na duração.",
        "como_ler": "0 rotina · 1–2 atenção · 3–4 risco alto para grupos vulneráveis.",
    },
    "casos_srag": {
        "nome": "Casos SRAG",
        "leigo": "Síndrome Respiratória Aguda Grave notificada (hospitalizações graves).",
        "como_ler": "Picos podem acompanhar vírus, fumaça ou ambos — cruzar com clima/ar.",
    },
    "indice_tensao_climatica": {
        "nome": "Índice de tensão climática (0–100)",
        "leigo": "Nota nova do ARARAS que resume calor + umidade + risco acumulado em uma escala fácil.",
        "como_ler": "0–30 baixo · 31–60 moderado · 61–80 alto · >80 muito alto.",
    },
    "indice_carga_saude": {
        "nome": "Índice de carga em saúde (0–100)",
        "leigo": "Resume SRAG, arboviroses e qualidade do ar disponíveis no município.",
        "como_ler": "Alto = mais sinais sanitários simultâneos — priorizar investigação.",
    },
    "indice_vigilancia_integrada": {
        "nome": "Índice de vigilância integrada (0–100)",
        "leigo": "Combina clima + saúde + alinhamento com o nível oficial (Verde→Roxa).",
        "como_ler": "Use junto com o nível operacional — agora Roxa tende a ficar ≥ Vermelha.",
    },
    "indice_vigilancia_bruta": {
        "nome": "Vigilância bruta (0–100)",
        "leigo": "Mesma lógica climática/sanitária, sem misturar o nível oficial.",
        "como_ler": "Útil para ver pressão ‘pura’ de clima+saúde quando o nível veio de outro gatilho.",
    },
    "tendencia_7d": {
        "nome": "Tendência 7 dias",
        "leigo": "Compara o nível de hoje com a predição da próxima semana.",
        "como_ler": "Subindo / estável / descendo — horizonte curto, não é previsão de setembro.",
    },
    "completude_dados_pct": {
        "nome": "Completude dos dados (%)",
        "leigo": "Quanto das informações-chave do município está preenchido nesta rodada.",
        "como_ler": "Baixa completude = interprete com cautela (pode faltar ar, leitos etc.).",
    },
    "indice_prioridade_global": {
        "nome": "Prioridade global (0–100)",
        "leigo": "Nota única que combina vigilância, pressão em saúde, AdaptaSUS, fragilidade da rede e alerta integrado.",
        "como_ler": "0–30 baixa · 31–60 moderada · 61–80 alta · >80 muito alta. Não substitui o nível Verde→Roxa.",
    },
    "faixa_prioridade_global": {
        "nome": "Faixa da prioridade global",
        "leigo": "Leitura rápida da prioridade global (baixa / moderada / alta / muito alta).",
        "como_ler": "Use para ranking de plantão; confirme no território e no nível operacional.",
    },
    "completude_prioridade_pct": {
        "nome": "Completude da prioridade (%)",
        "leigo": "Quantos pilares entraram no cálculo da prioridade global nesta rodada.",
        "como_ler": "Baixa completude = interprete com cautela (faltou pressão, resiliência etc.).",
    },
    "tendencia_prioridade_7d": {
        "nome": "Tendência da prioridade (~7 dias)",
        "leigo": "Sinal de aumento, manutenção ou queda da prioridade no horizonte curto.",
        "como_ler": "Combina tendência climática e de pressão assistencial quando disponíveis.",
    },
    "indice_vulnerabilidade_calor": {
        "nome": "Vulnerabilidade territorial ao calor",
        "leigo": "Índice que junta população mais exposta (idosos, crianças, zona rural) ao calor no município.",
        "como_ler": "Quanto maior, mais o território precisa de atenção na onda de calor — não é diagnóstico clínico.",
    },
    "iq_ar_score": {
        "nome": "Índice de qualidade do ar (IQA)",
        "leigo": "Nota da qualidade do ar no município (fumaça e poluentes disponíveis).",
        "como_ler": "Valores altos indicam ar ruim — cruze com PM2,5 e grupos vulneráveis.",
    },
    "percentil_risco_estadual": {
        "nome": "Percentil de risco no Estado",
        "leigo": "Posição do município frente aos demais (ex.: percentil 90 = entre os 10% piores).",
        "como_ler": "Ajuda a relativizar: ‘quente’ em relação a Mato Grosso hoje.",
    },
    "orientacao_leiga": {
        "nome": "Orientação em linguagem simples",
        "leigo": "Frase automática sugerindo o que observar no município nesta rodada.",
        "como_ler": "É um resumo didático — confirme sempre com o nível, o motivo e o plantão CIEVS.",
    },
    "indice_adaptacao_climatica": {
        "nome": "Índice de adaptação climática (0–100)",
        "leigo": "Síntese dos riscos prioritários do AdaptaSUS cobertos pelo ARARAS nesta rodada.",
        "como_ler": "Quanto maior, maior a pressão climática–saúde agregada. Baixa completude penaliza o índice.",
    },
    "risco_adaptasus_dominante": {
        "nome": "Risco AdaptaSUS dominante",
        "leigo": "Qual dos 6 riscos prioritários mais pressiona o município hoje.",
        "como_ler": "Use para escolher o checklist SOP (calor, ar, vetorial, chuva…). SAN permanece lacuna explícita.",
    },
    "risco_wash": {
        "nome": "Risco WASH (água/saneamento)",
        "leigo": "Déficit domiciliar de rede de água e esgoto (Censo IBGE), amplificado em estiagem.",
        "como_ler": "Alto = mais domicílios sem rede adequada. Não substitui monitoramento operacional SNIS/SINISA em tempo real.",
    },
    "indice_deficit_wash": {
        "nome": "Índice de déficit WASH",
        "leigo": "Combina falta de rede de água, água não canalizada e esgoto inadequado (0–100).",
        "como_ler": "Base estrutural (Censo). Em estiagem o risco AdaptaSUS pode subir acima deste piso.",
    },
    "cobertura_rede_agua_pct": {
        "nome": "Cobertura rede de água (%)",
        "leigo": "% de domicílios com ligação à rede geral usada como forma principal (Censo 2022).",
        "como_ler": "Complementar com Vigilância Ambiental em eventos de desabastecimento.",
    },
    "deficit_esgoto_inadequado_pct": {
        "nome": "Déficit esgoto inadequado (%)",
        "leigo": "% de domicílios com fossa rudimentar, vala, corpo d'água ou sem banheiro.",
        "como_ler": "Prioriza risco de veiculação hídrica após chuva intensa ou em seca prolongada.",
    },
    "risco_calor_vulneravel": {
        "nome": "Risco calor × vulnerabilidade",
        "leigo": "Combina tensão térmica com demografia IBGE (idosos/crianças/rural) e porte populacional.",
        "como_ler": "Prioriza municípios quentes com mais grupos sensíveis — não substitui cadastro APS.",
    },
    "pop_vulneravel_exposta": {
        "nome": "População vulnerável exposta",
        "leigo": "Estimativa de idosos (≥60) + crianças (0–4) em município sob calor alto ou fumaça.",
        "como_ler": "Proxy Censo×clima para volume de atenção; não é lista nominal de vulneráveis.",
    },
    "indice_exposicao_vulneravel": {
        "nome": "Índice exposição × vulnerabilidade",
        "leigo": "Fraçao demográfica sensível amplificada pela intensidade de calor/fumaça (0–100).",
        "como_ler": "Ajuda a ranquear onde a exposição climática encontra mais pessoas sensíveis.",
    },
    "idosos_pct": {
        "nome": "% idosos (≥60 anos)",
        "leigo": "Parcela da população com 60 anos ou mais (Censo IBGE 2022).",
        "como_ler": "Grupo prioritário em ondas de calor, frio e fumaça.",
    },
    "risco_ar_queimadas": {
        "nome": "Risco ar / queimadas",
        "leigo": "PM2,5 amplificado por seca (chuva baixa).",
        "como_ler": "Sem PM2,5 no município o indicador fica vazio — não é ar limpo.",
    },
    "risco_vetorial_climatico": {
        "nome": "Risco vetorial climático",
        "leigo": "Arboviroses 7d cruzadas com calor e chuva favorável ao vetor.",
        "como_ler": "Apoia mutirões e investigação — não projeta a temporada inteira.",
    },
    "pressao_rede_climatica": {
        "nome": "Pressão da rede climática",
        "leigo": "Ocupação/pressão assistencial misturada com tensão climática.",
        "como_ler": "Ajuda a ver se o calor chega na porta da urgência.",
    },
    "odds_ratio": {
        "nome": "Odds Ratio (OR) ecológico",
        "leigo": "Compara chance de desfecho em municípios mais expostos vs menos expostos.",
        "como_ler": "OR > 1 sugere maior chance no grupo exposto. Não implica causalidade individual.",
    },
    "indice_sazonal": {
        "nome": "Índice sazonal",
        "leigo": "Compara a média de um mês com a média geral do período histórico.",
        "como_ler": "Acima de 1 indica mês historicamente mais crítico para o desfecho analisado.",
    },
    "indice_saturacao_solo": {
        "nome": "Índice de saturação do solo",
        "leigo": "Quanto o solo está ‘encheu’ de água (0–100), a partir da umidade volumétrica Open-Meteo.",
        "como_ler": "Alta/crítica aumenta atenção a alagamento junto com Cemaden/ANA — distinto de saturação de leitos.",
    },
    "indice_resiliencia": {
        "nome": "Índice de resiliência operacional",
        "leigo": "Capacidade de resposta do município (leitos livres, estoque, infra, busca, comunicação).",
        "como_ler": "Quanto maior, melhor. Com CNES, a capacidade mistura leitos livres e capacidade instalada.",
    },
    "indice_capacidade_cnes": {
        "nome": "Índice de capacidade CNES",
        "leigo": "Proxy da capacidade instalada (leitos e estabelecimentos por população + UTI).",
        "como_ler": "Não substitui resiliência operacional; mostra ‘quanto tem na rede’.",
    },
    "nivel_alerta_integrado": {
        "nome": "Alerta integrado ARARAS",
        "leigo": "Nível único que une estágio ARARAS com INMET, Cemaden, solo e hidro.",
        "como_ler": "É o max das camadas. Veja o componente dominante para saber o que puxou o alerta.",
    },
}

SECTION_GUIDES: dict[str, dict[str, str]] = {
    "Visão executiva": {
        "para_que_serve": "Visão rápida do Estado: mapa colorido e lista de municípios que pedem atenção primeiro.",
        "como_usar": "Comece pelo mapa. Depois abra a tabela ordenada por vigilância/score. Clique nas outras seções para detalhar.",
        "cuidado": "O nível é uma síntese operacional — não é diagnóstico clínico nem alerta oficial do INMET.",
    },
    "Mapas": {
        "para_que_serve": "Ver no território indicadores de calor, ar, pressão, vigilância e vulnerabilidade.",
        "como_usar": "Escolha o indicador no seletor. Compare regionais filtrando no topo da página.",
        "cuidado": "Alguns indicadores (PM2,5, leitos) têm cobertura parcial — ‘vazio’ no mapa ≠ zero risco.",
    },
    "Clima / TITAN": {
        "para_que_serve": "Calor/UTCI, saturação do solo e alertas oficiais INMET + Cemaden + ANA.",
        "como_usar": "Veja calor, depois solo e as abas de alertas; cruze com Assistência/Operacional.",
        "cuidado": "Só APIs oficiais e Python claro — sem scrapers ofuscados (política SES).",
    },
    "Qualidade do ar": {
        "para_que_serve": "Acompanhar fumaça e poluição (PM2,5/PM10/O3) quando houver medição.",
        "como_usar": "Cruze com SRAG e queimadas na seca. Priorize polos com PM2,5 alto.",
        "cuidado": "Cobertura limitada a municípios com dado — não generalize para todo o MT.",
    },
    "Assistência": {
        "para_que_serve": "Separar ocupação hospitalar (IndicaSUS) de pressão hospitalar/regulação (SISREG), mais SINAN/SIM no índice G/A/V.",
        "como_usar": "1) Ocupação só onde há leitos notificados. 2) SISREG para demanda/fila em todo o território. 3) Semáforo composto e tendência 7d.",
        "cuidado": "Município sem IndicaSUS não está ‘zerado’ — use SISREG. Nunca trate fila SISREG como % de ocupação de leitos.",
    },
    "Arboviroses": {
        "para_que_serve": "Acompanhar dengue, zika, chikungunya e correlatas no corte municipal.",
        "como_usar": "Olhe casos 7d, incidência e mapa; cruze com calor/chuva na Visão executiva.",
        "cuidado": "Janela curta (7d) — não projeta a temporada inteira só com este número.",
    },
    "SIVEP": {
        "para_que_serve": "Monitorar SRAG hospitalar e indicadores alinhados ao MS/SVSA.",
        "como_usar": "Veja casos, incidência, vírus e qualidade laboratorial; compare com ar/calor.",
        "cuidado": "Atraso de notificação pode existir — interprete tendências, não só o último dia.",
    },
    "Sentinela SG": {
        "para_que_serve": "Vigilância sentinela de síndrome gripal (indicadores SG-01…SG-13).",
        "como_usar": "Confira se as unidades atingem as metas MS e a circulação viral.",
        "cuidado": "Depende de unidades sentinela alimentadas — ausência de dado ≠ ausência de gripe.",
    },
    "GeoCalor": {
        "para_que_serve": "Explorar associação entre ondas de calor e desfechos cardiorrespiratórios (lags).",
        "como_usar": "Escolha o município e veja o risco relativo (RR) por defasagem de dias.",
        "cuidado": "Modelo exploratório — não é laudo causal individual.",
    },
    "Correlação clima-saúde": {
        "para_que_serve": "Explorar associações estatísticas entre clima e saúde no corte municipal.",
        "como_usar": "Olhe os pares com |ρ| alto e depois o scatter — gere hipóteses, não certezas.",
        "cuidado": "Correlação ecológica ≠ causalidade individual.",
    },
    "Cemaden / ANA": {
        "para_que_serve": "Riscos hidrológicos: alertas Cemaden, telemetria ANA e chuva.",
        "como_usar": "Cruze alertas com precipitação e nível operacional do município.",
        "cuidado": "Cobertura de estações é desigual no território.",
    },
    "Inteligência": {
        "para_que_serve": "Predição 7 dias, alerta inteligente e indicadores compostos AdaptaSUS.",
        "como_usar": "Use para a semana seguinte; cruze com a aba AdaptaSUS / Guia MS.",
        "cuidado": "Predição 7d ≠ forecast mensal de setembro.",
    },
    "AdaptaSUS / Guia MS": {
        "para_que_serve": "Alinhar a operação CIEVS-MT aos 6 riscos prioritários do AdaptaSUS e ao Guia MS.",
        "como_usar": "Veja cobertura estadual, risco dominante no mapa e ranking por índice de adaptação.",
        "cuidado": "SAN ainda sem fonte SES — lacuna explícita, não risco zero. WASH usa Censo IBGE (estrutural).",
    },
    "Sazonalidade / OR": {
        "para_que_serve": "Mostrar sazonalidade histórica e OR ecológico clima–agravos/ocupação.",
        "como_usar": "Comece pelo índice mensal e pelo heatmap SE×ano; depois veja OR e lags.",
        "cuidado": "OR e correlação temporal são exploratórios e não provam causalidade clínica individual.",
    },
    "Operacional": {
        "para_que_serve": "Estoque, infraestrutura CNES e resiliência operacional.",
        "como_usar": "Priorize municípios com baixa autonomia ou alta prioridade proxy.",
        "cuidado": "Algumas bases logísticas ainda são parciais/proxy.",
    },
    "Geografia": {
        "para_que_serve": "Conferir cadastro territorial, unidades CNES no mapa e deduplicação municipal.",
        "como_usar": "Use o mapa CNES para ver UBS/hospitais no recorte. Ponto oficial é lat/lon do cadastro; centroide municipal não é o endereço da unidade.",
        "cuidado": "Inconsistências de nome/IBGE afetam mapas e joins. Nem todo CNES tem coordenada preenchida.",
    },
    "Alertas": {
        "para_que_serve": "Boletins CIEVS no padrão SES-MT: estadual (canal central), regionais, municipais e Vigidesastre Cuiabá.",
        "como_usar": "Na aba Alertas, valide a prévia operacional (resumo → KPI → ações → prioritários) antes de armar o envio.",
        "cuidado": "Canal central recebe só o estadual. Identidade visual do portal SES-MT (azul). Envio externo desligado por padrão.",
    },
    "Cálculos": {
        "para_que_serve": "Transparência metodológica: limiares, pesos e o que entra no nível.",
        "como_usar": "Consulte antes de questionar um município ‘por que ficou vermelho?’.",
        "cuidado": "Mudanças em settings.yaml alteram índices compostos na próxima rodada.",
    },
    "Guia do leitor": {
        "para_que_serve": "Explicar cores, indicadores e como ler o painel sem jargão.",
        "como_usar": "Leia o glossário e a legenda de níveis antes da primeira reunião de sala de situação.",
        "cuidado": "Textos didáticos não substituem protocolos oficiais do CIEVS/SES.",
    },
    "El Niño / Contingência": {
        "para_que_serve": "Vincular o monitoramento do ARARAS ao Plano de Contingência / preparação El Niño.",
        "como_usar": "Veja cenário oficial, prioridades municipais do ARARAS e a matriz Meta→Ação→Responsável→Status.",
        "cuidado": "Sinal do painel não ativa COE nem decreta emergência — decisão é da autoridade competente.",
    },
    "Eventos em saúde": {
        "para_que_serve": "Receber rumores e eventos de saúde pública ligados ao clima (calor, fumaça, estiagem, fogo, surto) notificados por SMS/CRS, no mesmo espírito da ficha de eventos do VigiBarragens.",
        "como_usar": "SMS/CRS preenche a ficha territorial. CIEVS tria (rumor → verificação → confirmado/encerrado). Cruze com o nível ARARAS e com decretos de emergência.",
        "cuidado": "Não é ficha SINAN: sem nome, CPF ou prontuário. Manchete e rumor não viram caso confirmado automaticamente.",
    },
    "Prontidão climática": {
        "para_que_serve": "Dizer ao município o que conferir e preparar (farmácia, assistência, água, vigilância) antes do impacto sanitário.",
        "como_usar": "Abra o ranking IPMEC, escolha o município e execute o plano 0–24h / 24–72h / 3–7d. Redistribuição regional é sinal para a Sala de Situação.",
        "cuidado": "Sem BNAFAR o estoque é CONFERIR, não ruptura confirmada. A IA não prescreve medicamentos.",
    },
}

HOW_TO_READ_PANEL = [
    "1. Olhe a faixa colorida e os 6 cards de Situação estadual: nível, alerta, ameaça, tendência, pressão e frescor.",
    "2. Use Prioridades de hoje (top 10): motivo, tendência, ocupação/CNES/resiliência, lacunas e ação.",
    "3. Lembre: sinal do ARARAS ≠ ativação formal de COE/emergência.",
    "4. Em Alertas: registre validação humana, gere a prévia do boletim SES e só então arme o envio.",
    "5. Na Visão executiva, o mapa responde ‘onde?’ e ‘Por que este nível?’ explica o score.",
    "6. Em dúvida sobre um número, abra Frescor por fonte, Cálculos ou o Guia do leitor.",
]

HOW_TO_READ_PUBLIC = [
    "1. Abra a aba Visão: faixa de nível, cards do recorte e o mapa de risco de 3 dias.",
    "2. Filtre regional ou município no topo — o recorte vale para todas as abas.",
    "3. Em Mapas, compare calor, fumaça, vulnerabilidade e a predição de 7 dias.",
    "4. Em Território, confira a malha municipal e as populações vulneráveis.",
    "5. Em Qualidade do ar, veja PM2,5, IQA e focos de queimadas.",
    "6. Em El Niño, leia o cenário oficial (ASO) e o boletim da semana.",
    "7. Em Série ambiental, compare a janela atual com a série histórica de calor/ar.",
    "8. Em Arboviroses, acompanhe dengue, zika e chikungunya (casos 7 dias e mapa).",
    "9. Em Óbitos e clima, veja a série SIM sensível ao calor e a metodologia.",
    "10. Em Cemaden / ANA, veja alertas de desastre, nível de rio e chuva.",
    "11. Em Sazonalidade / OR, compare o mês atual com o histórico e o odds ratio ecológico.",
    "12. Em Cálculos, leia como cada indicador publicado é composto.",
]

GLOSSARIO_PUBLICO = [
    "nivel",
    "tmax",
    "utci_proxy",
    "risco_cumulativo_3d",
    "indice_tensao_climatica",
    "indice_carga_saude",
    "indice_vigilancia_integrada",
    "indice_prioridade_global",
    "faixa_prioridade_global",
    "tendencia_7d",
    "tendencia_prioridade_7d",
    "pressao_calor_pct",
    "indice_pressao_saude",
    "ocupacao_leitos_pct",
    "pm25_ugm3",
    "iq_ar_score",
    "qualidade_ar_nivel",
    "focos_queimadas_7d",
    "focos_queimadas_24h",
    "nivel_queimadas",
    "indice_vulnerabilidade_calor",
    "casos_arbovirus_7d",
    "incidencia_arbovirus_100k",
    "risco_vetorial_climatico",
    "indice_saturacao_solo",
    "situacao_hidro",
    "indice_sazonal",
    "odds_ratio",
]


def level_plain(nivel: str) -> dict[str, str]:
    key = str(nivel or "cinza").strip().lower()
    return LEVEL_GUIDE.get(key, LEVEL_GUIDE["cinza"])


def section_plain(secao: str) -> dict[str, str] | None:
    g = SECTION_GUIDES.get(secao)
    if not g:
        return None
    if "para_que_serve" not in g and "para_que_serve" in g:
        return {**g, "para_que_serve": g["para_que_serve"]}
    return g
