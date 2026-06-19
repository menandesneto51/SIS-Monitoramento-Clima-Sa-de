# Operação diária

## Rotina recomendada

1. 07h30: ingestão de meteorologia, INMET, Copernicus e dados assistenciais do dia anterior.
2. 08h00: pipeline executa indicadores e classifica nível.
3. 08h15: sala de situação valida boletim automático.
4. Até 2 horas após alerta INMET: comunicação municipal publicada.
5. 12h e 17h: reprocessamento nos níveis Laranja, Vermelha e Roxa.
6. Pós-evento: análise de auditoria, morbimortalidade, falhas, custo e lições aprendidas.

## Agendamento Windows

Usar Agendador de Tarefas apontando para:

```bat
rodar_pipeline.bat
```

Nos níveis críticos, criar segunda tarefa às 12h e 17h.
