from __future__ import annotations

RECS = {
    'verde': [
        ('Governança', 'Manter monitoramento rotineiro e revisar plano semanalmente no período crítico.'),
        ('Dados', 'Atualizar cadastros de vulneráveis, unidades, estoques e infraestrutura.'),
        ('Capacitação', 'Treinar APS, UPAs e hospitais em sinais de alerta, hidratação e resfriamento rápido.'),
        ('Arboviroses', 'Manter rotina de eliminação de criadouros e monitoramento SINAN de dengue/zika/chikungunya.')
    ],
    'amarela': [
        ('Sala de Situação', 'Ativar sala de situação e boletim diário de calor.'),
        ('APS', 'Iniciar busca ativa de idosos sozinhos, acamados, gestantes, crianças e pessoas em situação de rua.'),
        ('Comunicação', 'Emitir alerta municipal em até 2 horas após alerta INMET ou gatilho local.'),
        ('Insumos', 'Checar autonomia de SRO, soro, água potável e materiais de resfriamento.'),
        ('Arboviroses', 'Reforçar mutirão de limpeza, visita casa a casa e investigação de casos suspeitos de arboviroses.')
    ],
    'laranja': [
        ('COE parcial', 'Ativar COE parcial com vigilância, APS, regulação, assistência social, hospitais e comunicação.'),
        ('Assistência', 'Abrir salas climatizadas adicionais e pré-posicionar insumos nas portas de urgência.'),
        ('Busca ativa', 'Alcançar cobertura mínima de 90% da população prioritária cadastrada.'),
        ('Pontos de resfriamento', 'Ativar pontos municipais de resfriamento e hidratação em territórios prioritários.'),
        ('Arboviroses', 'Intensificar bloqueio de transmissão, nebulização seletiva e atendimento oportuno de dengue grave.')
    ],
    'vermelha': [
        ('COE pleno', 'Ativar COE pleno com reunião operacional ao menos 2 vezes ao dia.'),
        ('Regulação', 'Priorizar desidratação grave, hipertermia, insuficiência renal aguda e descompensações cardiorrespiratórias.'),
        ('Rede', 'Expandir observação climatizada e avaliar suspensão seletiva de agendas eletivas.'),
        ('Infraestrutura', 'Acionar contingência de energia, água e climatização nas unidades estratégicas.'),
        ('Arboviroses', 'Garantir leitos/observação para dengue grave, fluxos clínicos e comunicação de risco vetorial.')
    ],
    'roxa': [
        ('Crise', 'Ativar comando unificado municipal/estadual e solicitar apoio interfederativo.'),
        ('Logística', 'Executar redistribuição emergencial de insumos, água, transporte e leitos.'),
        ('Comunicação de crise', 'Disseminar orientações para salvar vidas em todos os canais disponíveis.'),
        ('Pós-evento', 'Planejar recuperação, análise de mortalidade, auditoria e reposição imediata de recursos.'),
        ('Arboviroses', 'Mobilizar apoio estadual/federal para controle vetorial e assistência às arboviroses em emergência.')
    ]
}


def recommendations_for_stage(stage: str):
    return RECS.get(stage, RECS['verde'])
