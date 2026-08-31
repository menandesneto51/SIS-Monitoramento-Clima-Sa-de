# Docker + Base Única (PostgreSQL) + DW SES/MT

## Arquitetura

```text
DW/IndicaSUS/SISREG + fontes públicas
                 │
                 ▼
       etl-scheduler (a cada 6 h)
                 │
                 ▼
       PostgreSQL (base única)
          ┌──────┴────────┐
          ▼               ▼
    Streamlit app   alerts-scheduler
                    (somente com ETL fresca)
```

- **DW**: fonte institucional (SINAN, SIM, GAL, IndicaSUS, CNES). Somente leitura.
- **PostgreSQL**: base operacional única do ARARAS MT (resumos, arboviroses, alertas, SIVEP, auditoria).
- **SQLite local**: fallback se `DATABASE_URL` não apontar para Postgres.

## Subir tudo

1. Copie o ambiente:

```powershell
copy .env.example .env
```

2. Preencha no `.env`:

- `DW_SERVER`, `DW_DATABASE`, `DW_USER`, `DW_PASSWORD`
- `POSTGRES_PASSWORD` (troque o padrão)
- `USE_SQLSERVER=true`
- No Docker Linux use `DW_CLIENT=pymssql` (padrão automático)

3. Suba a base única (Postgres):

```powershell
docker compose up -d db
```

4. Rode o pipeline no host apontando para o Postgres (recomendado na rede SES):

```powershell
$env:DATABASE_URL="postgresql+psycopg2://sisclima:SENHA@localhost:5432/sis_clima_saude"
.\.venv\Scripts\python.exe -m pip install psycopg2-binary pymssql
.\.venv\Scripts\python.exe validar_dw_conexao.py
.\.venv\Scripts\python.exe -c "from sisclima.pipeline import run_pipeline; print(run_pipeline(send_alerts=False))"
.\.venv\Scripts\python.exe -m streamlit run app_v9.py
```

5. Suba o painel e a ETL automática:

```powershell
docker compose up -d --build db etl-scheduler app landing
```

6. Depois da homologação funcional, suba o agendador de alertas:

```powershell
docker compose up -d alerts-scheduler
```

O serviço `etl-scheduler` executa uma rodada imediatamente e repete a cada
`ETL_INTERVAL_HOURS` (padrão: 6 horas). Uma falha gera nova tentativa após
`ETL_RETRY_MINUTES` (padrão: 15 minutos). O estado da última rodada fica em
`logs/etl_scheduler_health.json`.

O `alerts-scheduler` verifica esse arquivo antes de comunicar. Com
`ALERT_REQUIRE_FRESH_ETL=true`, nenhuma mensagem é enviada se a ETL estiver
ausente, com erro ou mais antiga que `ALERT_MAX_ETL_AGE_HOURS`.

Entrada (landing): http://localhost/  (`sites/araras-mt/`, porta `LANDING_PORT` padrão 80)  
Painel: http://localhost:8501


## Operação e diagnóstico

```powershell
# Situação dos containers
docker compose ps

# Acompanhar cada ciclo da ETL
docker compose logs -f etl-scheduler

# Rodada manual extraordinária
docker compose run --rm pipeline

# Estado consumido pelo gate dos alertas
Get-Content .\logs\etl_scheduler_health.json
```

Variáveis principais:

```env
ETL_INTERVAL_HOURS=6
ETL_RETRY_MINUTES=15
ETL_RUN_ON_START=true
ETL_HEALTH_FILE=logs/etl_scheduler_health.json
ETL_LOCK_FILE=logs/etl_scheduler.lock
ALERT_REQUIRE_FRESH_ETL=true
ALERT_MAX_ETL_AGE_HOURS=12
```

A trava em `logs/etl_scheduler.lock` impede sobreposição entre instâncias do
agendador que compartilham o mesmo volume. O histórico técnico detalhado continua
sendo gravado na tabela `pipeline_runs`.

## Observações de rede

- No Windows, se o DW estiver na rede corporativa, o container precisa alcançar `DW_SERVER` (VPN/firewall).
- No Linux container o driver padrão é `ODBC Driver 18 for SQL Server`.
- Se o DW só for acessível da máquina host, rode o pipeline no host apontando `DATABASE_URL` para `localhost:5432`.
