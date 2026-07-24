# Tutorial — Continuidade da última etapa (produção real)

Este guia cobre a etapa final: configurar o `.env`, validar o ambiente com preflight, executar o pipeline completo e confirmar o dashboard.

---

## 1) Objetivo desta etapa

Ao final, você deve ter:

1. `.env` preenchido com senhas/tokens reais  
2. `python preflight_real.py` com **exit code 0**  
3. pipeline executado com `RUN_PREFLIGHT=true`  
4. dashboard refletindo o ciclo mais recente  

---

## 2) Pré-requisitos no Windows

1. Abrir PowerShell na pasta do projeto.  
2. Ambiente virtual ativo:

```powershell
cd "C:\Users\Menandesneto\OneDrive\CIEVS MT\Monitoramento ondas de calor"
.\.venv\Scripts\Activate.ps1
```

3. Dependências instaladas:

```powershell
pip install -r requirements.txt
```

4. Driver ODBC instalado:
   - **ODBC Driver 18 for SQL Server** (x64)
   - Confirme com:

```powershell
python -c "import pyodbc; print(pyodbc.drivers())"
```

Se não aparecer `ODBC Driver 18 for SQL Server`, instale o driver da Microsoft e reabra o terminal.

---

## 3) Criar/atualizar o `.env`

### 3.1 Copiar o modelo

```powershell
copy .env.producao.example .env
notepad .env
```

### 3.2 Preencher campos obrigatórios

Substitua apenas os placeholders:

| Campo | O que colocar |
|---|---|
| `DW_PASSWORD` | senha real do DW (`menandes_cievs`) |
| `INDICASUS_PASSWORD` | senha real do **Roney** (`roneydamaceno`) no BdSES — **não** use a senha do DW |
| `SISREG_PASSWORD` | senha real SISREG (se usar) |
| `COPERNICUS_KEY` | `UID:TOKEN` do ADS/CDS |
| `SMTP_PASSWORD` | senha/app password do e-mail |
| `TELEGRAM_BOT_TOKEN` | token real do bot |
| `INMET_ALERTS_URL` | URL real de alertas (se tiver) |

### 3.2.1 Agregar SIM / SINAN / GAL (DW) + IndicaSUS (Roney)

No `.env` deixe assim (SRAG continua local):

```env
USE_SQLSERVER=true
USE_DW_SIM=true
USE_DW_SINAN=true
USE_DW_GAL=true
USE_DW_INDICASUS=true
USE_DW_CNES=true
EPI_LOOKBACK_DAYS=90

# DW = SIM/SINAN/GAL/CNES
DW_HOST=10.15.1.50
DW_DATABASE=Datawarehouse
DW_USER=menandes_cievs
DW_PASSWORD=<senha_dw>
DW_ENCRYPT=no
DW_TRUST_SERVER_CERTIFICATE=yes

# IndicaSUS tempo real = usuário Roney (não herdar DW)
INDICASUS_HOST=10.15.0.222
INDICASUS_SERVER=10.15.0.222
INDICASUS_DATABASE=BdSES
INDICASUS_USER=roneydamaceno
INDICASUS_PASSWORD=<senha_roney>
INDICASUS_ENCRYPT=no
INDICASUS_TRUST_SERVER_CERTIFICATE=yes
INDICASUS_USE_DW_CREDENTIALS=false
USE_INDICASUS_OCCUPANCY_SCRIPT=true

# SRAG fora do DW neste fluxo
USE_SIVEP_LOCAL=true
```

Validar conexões e extratores:

```powershell
.\.venv\Scripts\python.exe validar_fontes_dw.py
```

Esperado: `[OK]` em SIM, SINAN e/ou GAL; probe IndicaSUS `conectado como roneydamaceno no banco BdSES`.

### 3.3 Confirmar chaves essenciais já no modelo

- `RUN_PREFLIGHT=true`
- `USE_SQLSERVER=true`
- `USE_COPERNICUS=true`
- `USE_OPENMETEO=true`
- `REFRESH_OPENMETEO=true`
- `USE_SIVEP_LOCAL=true`
- `USE_EMAIL=true`
- `USE_TELEGRAM=true`
- `SMTP_PORT=465`
- `SMTP_SSL=true`
- `MUNICIPIOS_CSV=data/input/municipios_mt.csv`
- `POPULACAO_CSV=data/input/populacao_municipal_mt_2020_2025.csv`

Salve e feche o arquivo.

---

## 4) Garantir arquivos territoriais obrigatórios

Coloque estes arquivos (ou ajuste o caminho no `.env`):

```text
data/geo/municipios_mt/MT_Municipios_2025.shp
data/input/municipios_mt.csv
data/input/populacao_municipal_mt_2020_2025.csv
data/input/sivep_atualizacao/   (pasta com exportações SIVEP, se houver)
```

Se ainda não tiver a população/municípios na pasta `data/input`, copie os arquivos reais da sua pasta operacional para esses caminhos.

---

## 5) Rodar o pré-flight (obrigatório)

```powershell
python preflight_real.py
```

### Interpretação

- **Exit code 0**: ambiente pronto  
- **Exit code 2**: há falhas críticas (corrija antes do pipeline)

No final do relatório, observe:

```text
RESUMO:
- total: ...
- ok: ...
- fail: ...
- critical_fail: ...
- required_fail: ...
```

---

## 6) Como corrigir falhas críticas comuns

### A) `ODBC SQL Server driver`
- Instale ODBC Driver 18  
- Reabra PowerShell e rode novamente o preflight  

### B) `DW runtime query`
- Confirme VPN/rede interna SES  
- Confirme `DW_HOST`, `DW_PORT`, `DW_DATABASE`, `DW_USER`, `DW_PASSWORD`  
- Teste:

```powershell
python -c "from sisclima.ingestion.sqlserver import read_sqlserver; print(read_sqlserver('DW','SELECT 1 AS ok'))"
```

### C) `Copernicus credencial`
- Preencha `COPERNICUS_KEY=UID:TOKEN`  
  **ou**
- Crie `%USERPROFILE%\.cdsapirc`

### D) `CSV municípios` / `População municipal`
- Coloque os arquivos nos caminhos do `.env`  
- Ou ajuste `MUNICIPIOS_CSV` e `POPULACAO_CSV` para o caminho real  

### E) `SIVEP pasta atualização`
- Confirme existência de `data/input/sivep_atualizacao`  
- Se houver exports, coloque os arquivos nessa pasta  

---

## 7) Executar o pipeline completo (com gate)

Quando o preflight estiver com exit 0:

```powershell
python -c "from sisclima.core.db import init_db; from sisclima.pipeline import run_pipeline; init_db(); print(run_pipeline(send_alerts=False))"
```

### Resultado esperado
- `status: success`
- nível e score calculados
- exportação automática para `data/public` (log no console)

> Dica: use `send_alerts=False` na validação inicial.  
> Só ative envio real depois (`send_alerts=True`) quando estiver estável.

---

## 8) Gerar boletim/relatório

```powershell
python -c "from sisclima.ai.report_generator import generate_daily_report; print(generate_daily_report(send=False))"
```

Arquivo gerado em:

```text
exports/relatorios/boletim_sis_mt_clima_saude_YYYYMMDD_HHMMSS.txt
```

---

## 9) Abrir o dashboard

```powershell
streamlit run streamlit_app.py
```

No painel, confirme:

1. nível operacional atualizado  
2. municípios/indicadores carregando  
3. aba de alertas com arquivos públicos preenchidos  

Arquivos públicos sincronizados automaticamente pelo pipeline:

```text
data/public/resumo_municipal_atual.csv
data/public/status_alertas_vigia.csv
data/public/alertas_estado_vigia.csv
data/public/alertas_regionais_vigia.csv
data/public/alerta_cuiaba_vigia.csv
...
```

---

## 10) Sequência rápida (copiar/colar)

```powershell
cd "C:\Users\Menandesneto\OneDrive\CIEVS MT\Monitoramento ondas de calor"
.\.venv\Scripts\Activate.ps1

# 1) Ajustar .env (uma vez)
copy .env.producao.example .env
notepad .env

# 2) Validar ambiente
python preflight_real.py

# 3) Rodar ciclo (somente se preflight = 0)
python -c "from sisclima.core.db import init_db; from sisclima.pipeline import run_pipeline; init_db(); print(run_pipeline(send_alerts=False))"

# 4) Relatório
python -c "from sisclima.ai.report_generator import generate_daily_report; print(generate_daily_report(send=False))"

# 5) Dashboard
streamlit run streamlit_app.py
```

---

## 11) Checklist de aceite desta etapa

- [ ] `.env` preenchido sem placeholders `COLE_AQUI_*`  
- [ ] ODBC Driver 18 visível em `pyodbc.drivers()`  
- [ ] `preflight_real.py` retornou exit `0`  
- [ ] pipeline retornou `status=success`  
- [ ] CSVs em `data/public` atualizados  
- [ ] boletim gerado em `exports/relatorios`  
- [ ] Streamlit abriu e mostrou nível/indicadores  

---

## 12) O que me enviar para continuarmos juntos

Cole aqui o trecho final do preflight:

```text
RESUMO:
- total: ...
- ok: ...
- fail: ...
- critical_fail: ...
- required_fail: ...
```

e, se houver falha, as linhas com `severity = critical`.

Com isso eu te guio item a item até zerar todas as pendências e fechar a etapa.
