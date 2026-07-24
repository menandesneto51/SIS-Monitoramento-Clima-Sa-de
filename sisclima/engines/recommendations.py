from __future__ import annotations

"""Playbook operacional por nível — ações concretas além de "acionar COE".

Cada nível traz eixos de: governança, vigilância, APS, urgência/hospital,
regulação, logística/insumos, comunicação, grupos vulneráveis e pós-evento.
"""

RECS = {
    "verde": [
        ("Monitoramento", "Manter painel diário de UTCI/Tmax e revisão semanal do plano municipal de calor."),
        ("Cadastros", "Atualizar lista de idosos sozinhos, acamados, gestantes, população em situação de rua e instituições de longa permanência."),
        ("Capacitação", "Treinar APS/UPA em reconhecimento de exaustão/golpe de calor, hidratação oral e resfriamento externo."),
        ("Insumos", "Conferir estoque mínimo de SRO, soro, água e dispositivos de resfriamento nas portas de urgência."),
        ("Comunicação", "Revisar roteiros de mensagem preventiva e canais oficiais (rádio, redes, CRAS, UBS)."),
    ],
    "amarela": [
        ("Sala de Situação", "Ativar sala de situação com boletim diário (clima + atendimentos + ocupação)."),
        ("APS", "Iniciar busca ativa prioritária em idosos sozinhos, acamados e territórios de alta vulnerabilidade."),
        ("UBS/ESF", "Orientar hidratação frequente, evitar pico de calor (10h–16h) e verificar moradias sem ventilação."),
        ("Urgência", "Pré-posicionar SRO/água e protocolo de resfriamento na recepção da UPA/PS."),
        ("Comunicação", "Emitir alerta municipal em até 2h após gatilho INMET/local, com linguagem clara para leigos."),
        ("Insumos", "Garantir autonomia ≥ 7 dias de SRO/soro/água nas unidades sentinela."),
    ],
    "laranja": [
        ("COE parcial", "Abrir COE parcial (vigilância, APS, regulação, assistência social, hospitais, comunicação) com briefing diário."),
        ("Busca ativa", "Cobrir ≥ 90% da população prioritária cadastrada em 48h (visita/telefone/CRAS)."),
        ("Pontos de resfriamento", "Abrir pontos públicos climatizados (escolas, ginásios, CRAS) próximos a territórios críticos."),
        ("Assistência", "Ampliar observação climatizada e triagem rápida para desidratação/hipertermia."),
        ("Regulação", "Reservar leitos de observação e definir fluxo prioritário DARC/calor."),
        ("Comunicação de risco", "Campanha intensiva em rádio/carro de som/UBS com sinais de alarme e onde buscar ajuda."),
        ("Intersetorial", "Articular defesa civil, assistência social e educação para abrigo diurno de vulneráveis."),
    ],
    "vermelha": [
        ("COE pleno", "COE pleno com reuniões ≥ 2x/dia; escala 24h de plantão técnico."),
        ("Regulação clínica", "Priorizar desidratação grave, hipertermia, IRA, descompensação cardiorrespiratória e idosos frágeis."),
        ("Rede hospitalar", "Expandir observação climatizada; avaliar suspensão seletiva de eletivos não urgentes."),
        ("APS reforçada", "Dobrar busca ativa em ILPI, abrigos e áreas sem sombra/água; kit hidratação domiciliar."),
        ("Logística", "Redistribuir SRO/água/transporte entre regionais com maior score e ocupação."),
        ("Infraestrutura", "Acionar contingência de energia, água e climatização nas unidades estratégicas."),
        ("Vigilância epi", "Monitorar SRAG, óbitos suspeitos por calor e picos de atendimento a cada 12h."),
        ("Comunicação", "Alertas horários nos canais oficiais + orientação de não exposição ao sol no pico térmico."),
    ],
    "roxa": [
        ("Comando unificado", "Ativar comando estadual/municipal integrado (SES, regionais, municípios críticos) com sala única de decisão."),
        ("Apoio interfederativo", "Solicitar reforço de equipes, ambulâncias, água e insumos às regionais satélites e, se preciso, apoio federal."),
        ("Assistência crítica", "Protocolo de resfriamento imediato nas portas; priorizar UTI/observação para golpe de calor e descompensações."),
        ("Regulação de crise", "Centralizar vagas; transferir casos graves das regionais com ocupação >70% e score ≥3."),
        ("APS e território", "Mutirão de busca ativa 24h em idosos sozinhos, rua e ILPI; abrir abrigos climatizados noturnos se necessário."),
        ("Logística emergencial", "Redistribuir água, SRO, gelo/resfriamento e transporte nas ERS com mais municípios em alerta."),
        ("Vigilância e mortalidade", "Linha rápida de notificação de óbito suspeito por calor; revisão diária de SRAG/SIM/pronto-socorro."),
        ("Comunicação de crise", "Mensagens para salvar vidas (hidratação, sombra, quando ligar 192) em todos os canais, de hora em hora se necessário."),
        ("Saúde do trabalhador", "Restringir trabalho externo no pico térmico; pausas obrigatórias e pontos de hidratação."),
        ("Pós-evento imediato", "Planejar reposição de estoque, auditoria de óbitos, relatório de lições aprendidas em até 72h após queda de nível."),
    ],
}


def recommendations_for_stage(stage: str):
    key = str(stage or "verde").strip().lower()
    return RECS.get(key, RECS["verde"])


def playbook_text(stage: str) -> str:
    lines = [f"- [{eixo}] {acao}" for eixo, acao in recommendations_for_stage(stage)]
    return "\n".join(lines)
