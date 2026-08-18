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
# Ativar fan-out territorial (depois de preencher a planilha)
mkdir -p data/input
cp config/contatos_alertas.exemplo.csv data/input/contatos_alertas.csv
# editar e-mails/chats reais…
# no .env: ALERT_FANOUT_ENABLED=true
```

## Produção: servidor da SES

O ARARAS MT roda **na rede interna da SES**. DW (`10.15.1.50`), IndicaSUS e SISREG são hosts locais — **não há VPN** nesse cenário. Modelo de `.env`: `.env.producao.example`. Detalhe de implantação: `docs/STI_IMPLANTACAO_SERVIDOR_SES.md`.

```bash
# No servidor SES (Docker)
docker compose up -d db etl-scheduler app alerts-scheduler
```

| Serviço | Função |
|---|---|
| `db` | Postgres operacional |
| `etl-scheduler` | Pipeline a cada 6 h (`ETL_INTERVAL_HOURS`) — clima + DW + indicadores |
| `app` | Painel Streamlit (`:8501`) |
| `alerts-scheduler` | Digest de alertas (só depois de ETL fresca) |

O painel lê o Postgres já atualizado; recarregar o navegador basta. `--offline` e o Agendador do Windows no notebook são só para desenvolvimento fora da SES.

## Pasta `data/input`

A pasta não vai para o Git. Na primeira máquina:

```powershell
python scripts\preparar_data_input.py
```

Isso cria `data/input` e `data/input/sivep_atualizacao`, copia CSVs de exemplo (se existirem em `data/sample`) e o modelo de contatos.

| O que entra | Onde | Como entra no painel |
|---|---|---|
| Export SIVEP/SRAG (CSV/XLSX/Parquet) | `data/input/sivep_atualizacao/` | `atualizar_sivep_local.bat` ou a rotina diária |
| Planilha de contatos | `data/input/contatos_alertas.csv` | Fan-out com `ALERT_FANOUT_ENABLED=true` |
| CSV de fallback (INMET, rumores, leitos…) | `data/input\` nomes em `config/settings.yaml` | Pipeline, se a API/DW estiver vazia |
| IndicaSUS, SINAN, SIM, GAL, CNES | DW (`DW_*` no `.env`) | Rede interna SES (servidor de produção) |

SIVEP oficial não se inventa: coloque o export da vigilância na pasta de atualização. Sem arquivo, a aba SIVEP fica vazia.

## Windows Server (sem Docker)

Se o servidor da SES for Windows e a STI não usar Compose, agendar no próprio host:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\criar_tarefas_windows.ps1
```

`rodar_pipeline.bat` chama `rotina_diaria_ops.py` (clima + DW + ANA + SISREG). O `--offline` não deve ser usado nesse host.
