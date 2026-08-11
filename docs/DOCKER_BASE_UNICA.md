# Docker + Base Única (PostgreSQL) + DW SES/MT

## Arquitetura

```text
DW SQL Server (SES/MT)  ──leitura──▶  pipeline (Docker)
                                          │
                                          ▼
                               PostgreSQL (base única)
                               sis_clima_saude
                                          │
                                          ▼
                               Streamlit app (Docker)
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

5. (Opcional) Suba app+pipeline em containers:

```powershell
docker compose up -d --build
```

Painel: http://localhost:8501


## Observações de rede

- No Windows, se o DW estiver na rede corporativa, o container precisa alcançar `DW_SERVER` (VPN/firewall).
- No Linux container o driver padrão é `ODBC Driver 18 for SQL Server`.
- Se o DW só for acessível da máquina host, rode o pipeline no host apontando `DATABASE_URL` para `localhost:5432`.
