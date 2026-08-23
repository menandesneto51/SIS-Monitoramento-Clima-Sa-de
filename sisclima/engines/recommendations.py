from __future__ import annotations

from typing import Any

import pandas as pd

RECS = {
    'verde': [
        ('Governança', 'Manter monitoramento rotineiro e revisar plano semanalmente no período crítico.'),
        ('Dados', 'Atualizar cadastros de vulneráveis, unidades, estoques e infraestrutura.'),
        ('Capacitação', 'Treinar APS, UPAs e hospitais em sinais de alerta, hidratação e resfriamento rápido.'),
        ('Arboviroses', 'Manter rotina de eliminação de criadouros e monitoramento SINAN de dengue/zika/chikungunya.'),
        ('Atenção farmacêutica estadual', 'SAF/CEME: programar estoque estratégico de SRO, broncodilatadores e hipoclorito para redistribuição às regionais — sem substituir a farmácia municipal.'),
        ('Atenção farmacêutica municipal', 'CBAF/UBS: conferir validade de SRO, broncodilatadores e corticoides; Visa municipal mantém hipoclorito 2,5% de pronta entrega.'),
    ],
    'amarela': [
        ('Sala de Situação', 'Ativar sala de situação e boletim diário de calor.'),
        ('APS', 'Iniciar busca ativa de idosos sozinhos, acamados, gestantes, crianças e pessoas em situação de rua.'),
        ('Comunicação', 'Emitir alerta municipal em até 2 horas após alerta INMET ou gatilho local.'),
        ('Insumos', 'Checar autonomia de SRO, soro, água potável e materiais de resfriamento.'),
        ('Arboviroses', 'Reforçar mutirão de limpeza, visita casa a casa e investigação de casos suspeitos de arboviroses.'),
        ('Atenção farmacêutica estadual', 'SAF: antecipar nota técnica às regionais e conferir estoque estratégico (SRO, soro EV, linha respiratória).'),
        ('Atenção farmacêutica municipal', 'Farmácia/UBS: SRO e antitérmicos na porta; se IQA amarelo+, máscara opcional a grupos sensíveis.'),
    ],
    'laranja': [
        ('COE parcial', 'Ativar COE parcial com vigilância, APS, regulação, assistência social, hospitais e comunicação.'),
        ('Assistência', 'Abrir salas climatizadas adicionais e pré-posicionar insumos nas portas de urgência.'),
        ('Busca ativa', 'Alcançar cobertura mínima de 90% da população prioritária cadastrada.'),
        ('Pontos de resfriamento', 'Ativar pontos municipais de resfriamento e hidratação em territórios prioritários.'),
        ('Arboviroses', 'Intensificar bloqueio de transmissão, nebulização seletiva e atendimento oportuno de dengue grave.'),
        ('Atenção farmacêutica estadual', 'Redistribuir linha respiratória e SRO às regionais críticas; orientar PFF2 a trabalhadores da saúde se IQA laranja+.'),
        ('Atenção farmacêutica municipal', 'Conferir broncodilatadores (salbutamol, ipratrópio), corticoides e espaçadores; PFF2 a asmáticos/DPOC/crianças/idosos se IQA laranja+.'),
    ],
    'vermelha': [
        ('COE pleno', 'Ativar COE pleno com reunião operacional ao menos 2 vezes ao dia.'),
        ('Regulação', 'Priorizar desidratação grave, hipertermia, insuficiência renal aguda e descompensações cardiorrespiratórias.'),
        ('Rede', 'Expandir observação climatizada e avaliar suspensão seletiva de agendas eletivas.'),
        ('Infraestrutura', 'Acionar contingência de energia, água e climatização nas unidades estratégicas.'),
        ('Arboviroses', 'Garantir leitos/observação para dengue grave, fluxos clínicos e comunicação de risco vetorial.'),
        ('Atenção farmacêutica estadual', 'Posicionar insumos de hidratação venosa, linha respiratória e hipoclorito nas regionais em vermelha; reportar rupturas à CEME.'),
        ('Atenção farmacêutica municipal', 'PFF2 em atividade externa se IQA ruim; checar oxigênio, inalação e SRO; em cheia, hipoclorito 2,5% e água segura.'),
    ],
    'roxa': [
        ('Crise', 'Ativar comando unificado municipal/estadual e solicitar apoio interfederativo.'),
        ('Logística', 'Executar redistribuição emergencial de insumos, água, transporte e leitos.'),
        ('Comunicação de crise', 'Disseminar orientações para salvar vidas em todos os canais disponíveis.'),
        ('Pós-evento', 'Planejar recuperação, análise de mortalidade, auditoria e reposição imediata de recursos.'),
        ('Arboviroses', 'Mobilizar apoio estadual/federal para controle vetorial e assistência às arboviroses em emergência.'),
        ('Atenção farmacêutica estadual', 'Logística excepcional: redistribuição plena de SRO, respiratórios, hipoclorito e imunobiológicos articulados com CEME/PNI.'),
        ('Atenção farmacêutica municipal', 'PFF2 à população se IQA péssimo; farmácia em regime de urgência; Visa com hipoclorito na ponta se houver inundação.'),
    ]
}


def recommendations_for_stage(stage: str):
    return RECS.get(stage, RECS['verde'])


def recommendations_for_context(stage: str, resumo: pd.DataFrame | None = None) -> list[tuple[str, Any]]:
    """Checklist de estágio + ações farmacêuticas ancoradas no clima/IQA/hidro atuais."""
    recs = [(eixo, texto) for eixo, texto in recommendations_for_stage(stage) if "farmac" not in str(eixo).lower()]
    try:
        from sisclima.engines.atencao_farmaceutica import recomendacoes_pipeline

        recs.extend(recomendacoes_pipeline(stage, resumo))
    except Exception:
        pass
    return recs
