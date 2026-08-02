# Operação diária

## Rotina recomendada

1. 07h30: ingestão de meteorologia, INMET, Copernicus e dados assistenciais do dia anterior.
2. 08h00: pipeline executa indicadores e classifica nível.
3. 08h15: sala de situação valida boletim automático.
4. Até 2 horas após alerta INMET: comunicação municipal publicada.
5. 12h e 17h: reprocessamento nos níveis Laranja, Vermelha e Roxa.
6. Pós-evento: análise de auditoria, morbimortalidade, falhas, custo e lições aprendidas.

## Alertas — quem recebe o quê

| Escopo | Destinatário | Situação atual |
|---|---|---|
| **Estadual (SES/CIEVS)** | Canal central: `ALERT_EMAIL_TO` (ex. Menandes + `notifica@ses.mt.gov.br`) e `TELEGRAM_CHAT_ID` | **Ativo** — único escopo enviado ao CIEVS |
| Regional / municipal / Cuiabá | Destinatários da planilha `data/input/contatos_alertas.csv` | **Gerados e gravados**; envio só com planilha + `ALERT_FANOUT_ENABLED=true` |

Modelo da planilha: `config/contatos_alertas.exemplo.csv`.

```bash
# Validar planilha e ver quem receberia cada boletim (não envia)
python -m sisclima.alerts.contacts --validate --plan

# Ativar fan-out territorial (depois de preencher a planilha)
mkdir -p data/input
cp config/contatos_alertas.exemplo.csv data/input/contatos_alertas.csv
# editar e-mails/chats reais…
# no .env: ALERT_FANOUT_ENABLED=true
# opcional em homologação: ALERT_FANOUT_DRY_RUN=true (planeja sem enviar)
```

## Agendador diário sem notebook

O serviço Docker `alerts-scheduler` (`restart: unless-stopped`) roda no **servidor/host**, independente do notebook estar ligado ou na rede:

```bash
# No servidor SES / VPS com Docker
docker compose up -d db alerts-scheduler
```

Padrão: ciclo a cada **24 h** (`ALERT_INTERVAL_HOURS=24`). Disparo manual:

```bash
docker compose run --rm alerts-scheduler --once --force
# ou
python -m sisclima.alerts.scheduler --once --force
```

Alternativa sem Docker Compose contínuo: cron no servidor (`0 8 * * *`) chamando o mesmo comando `--once`.

## Agendamento Windows

Usar Agendador de Tarefas apontando para:

```bat
rodar_pipeline.bat
```

Nos níveis críticos, criar segunda tarefa às 12h e 17h.
