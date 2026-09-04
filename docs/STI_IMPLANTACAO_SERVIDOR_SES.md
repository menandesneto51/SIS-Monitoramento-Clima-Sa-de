# Documento Técnico STI — Implantação do ARARAS MT nos servidores da SES-MT

<table><tr><td><img src="../assets/branding/araras-mt-logo-horizontal.png" alt="ARARAS MT" width="360"></td><td><img src="../assets/branding/governo-ses-mt-fundo-institucional.png" alt="SES-MT e Governo de Mato Grosso" width="250"></td></tr><tr><td><strong>CIEVS-MT</strong> · <img src="../assets/branding/rede-cievs.png" alt="Rede CIEVS" width="125"></td><td><img src="../assets/branding/vigidesastres.png" alt="Vigidesastres" width="60"></td></tr></table>

**Destinatário:** Superintendência / Coordenação de Tecnologia da Informação (STI) — SES-MT
**Solicitante:** CIEVS-MT
**Sistema:** ARARAS MT — Análise, Resposta e Acompanhamento de Riscos, Agravos e Saúde
**Lema:** Clima, ambiente e saúde em uma só visão.
**Versão de referência:** branch de migração `araras-mt`, baseada em `painel-v9`
**Data:** 11/08/2026

---

## 1. Objetivo

Descrever, de forma operacional, **como instalar, configurar, expor e manter** o ARARAS MT nos servidores da SES, incluindo requisitos de rede, contas, portas, persistência, agendamento e segurança — para o painel e a rotina de dados ficarem sob governança da STI.

> **Gate de produção:** a publicação institucional não deve ser homologada enquanto o painel estiver usando o seed SQLite como base principal ou apresentar fontes essenciais fora da janela de atualização. O aceite exige Postgres, rotina concluída no dia e conferência explícita da qualidade das fontes.

Padrão de marca e comunicação: `docs/IDENTIDADE_VISUAL_ARARAS_MT.md`.

---

## 2. Visão da solução

| Componente | Função | Tecnologia |
|------------|--------|------------|
| **App** | Painel municipal (Streamlit) | Python 3.12, porta **8501** |
| **ETL scheduler** | Ingestão + indicadores + classificação periódica | Python batch / container contínuo |
| **DB** | Base operacional única | **PostgreSQL 16** |
| **Alertas** | Digest periódico (opcional) | Scheduler em loop 24 h |
| **Seed** | Contingência / demo | SQLite `data/cloud/sis_cloud_seed.db` |

Arquitetura lógica: Bronze (fontes) → Silver (padronização) → Gold (indicadores) → Dashboard.

```text
[DW/IndicaSUS/SISREG]──rede interna SES──┐
[Open-Meteo/Cemaden/ANA/INPE]──HTTPS─────┤──► Pipeline ──► Postgres ──► Streamlit :8501
[CSV locais / SIVEP]─────────────────────┘         │
                                      etl-scheduler (6 h)
                                                │
                                                ├──► Postgres / Streamlit
                                                └──► alerts-scheduler (apenas com ETL fresca)
```

---

## 3. Requisitos de infraestrutura

### 3.1 Servidor (mínimo sugerido)

| Recurso | Mínimo piloto | Recomendado produção |
|---------|---------------|----------------------|
| SO | Windows Server 2019+ **ou** Linux (Ubuntu 22.04+) | Linux com Docker |
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disco | 40 GB livres | 100 GB+ (dados + logs + PG) |
| Runtime | Docker Engine + Compose **ou** Python 3.12 + venv | Docker Compose |
| Conta OS | Serviço dedicado (sem perfil de usuário final) | Idem |

### 3.2 Portas

| Porta | Serviço | Exposição sugerida |
|-------|---------|-------------------|
| **80/TCP** | Landing institucional (`sites/araras-mt/`) | Rede interna SES (entrada oficial do host) |
| **8501/TCP** | Streamlit (painel) | Rede interna SES / reverse proxy STI |
| **5432/TCP** | Postgres | **Somente localhost** ou rede Docker interna |
| 1433/TCP (saída) | SQL Server DW / IndicaSUS / SISREG | Rede interna SES (mesmo datacenter) |

> Não publicar 5432 na internet. Preferir autenticação SSO/proxy da STI na frente do 8501.  
> Entrada sugerida no servidor piloto: `http://10.15.0.131/` (landing) → CTAs abrem `http://10.15.0.131:8501/` (painel). Se a porta 80 estiver ocupada, use `LANDING_PORT=8080`.

### 3.3 Persistência (volumes / pastas)

Manter backup e exclusão do ciclo de limpeza automática:

| Caminho | Conteúdo |
|---------|----------|
| `.env` | Segredos e flags (fora do Git) |
| `data/input/` | CSV oficiais, contatos, fallbacks |
| `data/cloud/` | Seed SQLite (contingência) |
| `data/local/sivep/` | Base SIVEP local se usada |
| `data/geo/` | Malhas / geojson |
| `logs/` | Logs de rotina e pipeline |
| `config/` | YAML limiares (versionado) |
| Volume Docker `sis_pgdata` | Dados Postgres |

---

## 4. Contas e credenciais (governança)

### 4.1 Contas de serviço (recomendado criar)

| Sistema | Host (rede SES) | Porta | Base | Permissão |
|---------|-----------------|-------|------|-----------|
| DW | `10.15.1.50` | 1433 | `Datawarehouse` | **Somente leitura** |
| IndicaSUS / BdSES | `10.15.0.222` | 1433 | `BdSES` | **Somente leitura** |
| SISREG | `10.15.1.71` | 1433 | `SES` | **Somente leitura** |
| Postgres local | `localhost` / `db` | 5432 | `sis_clima_saude` | Owner do app |

> Evitar usuários nominais de técnicos no `.env` de produção. Rotacionar senhas conforme política STI.

### 4.2 Credenciais externas (não SES)

| Serviço | Uso | Observação |
|---------|-----|------------|
| ANA HidroWeb REST | Inventário + séries de rio | Identificador/senha **pessoal ou institucional ANA** — só no `.env` do servidor |
| Telegram / SMTP | Alertas | Opcional; desligado por padrão |
| Copernicus ADS | Qualidade do ar | Opcional (`USE_COPERNICUS=false`) |

### 4.3 Arquivo `.env`

1. Copiar `.env.producao.example` (ou `.env.example`) → `.env` no servidor.
2. Preencher senhas **apenas** no servidor (nunca commit).
3. Definir `DATABASE_URL` apontando para o Postgres do servidor.
4. Manter `SEND_ALERT_ON_LEVEL_CHANGE=false` até homologação CIEVS.

Modelo mínimo (valores ilustrativos — STI preenche):

```env
DATABASE_URL=postgresql+psycopg2://sisclima:***@localhost:5432/sis_clima_saude
USE_SQLSERVER=true
DW_HOST=10.15.1.50
DW_DATABASE=Datawarehouse
DW_USER=<conta_servico>
DW_PASSWORD=<senha>
INDICASUS_HOST=10.15.0.222
INDICASUS_DATABASE=BdSES
INDICASUS_USER=<conta_servico>
INDICASUS_PASSWORD=<senha>
SISREG_HOST=10.15.1.71
SISREG_DATABASE=SES
SISREG_USER=<conta_servico>
SISREG_PASSWORD=<senha>
USE_ESUS_APS=true
ESUS_APS_HOST=10.15.0.25
ESUS_APS_DATABASE=esus2
ESUS_APS_USER=<conta_leitura>
ESUS_APS_PASSWORD=<senha>
USE_ANA=true
ANA_FETCH_SERIES=true
ANA_USE_HIDROWEB_REST=true
ANA_HIDROWEB_IDENTIFICADOR=<cpf_ou_id_ana>
ANA_HIDROWEB_SENHA=<senha_ana>
ETL_INTERVAL_HOURS=6
ETL_RETRY_MINUTES=15
ETL_RUN_ON_START=true
ALERT_REQUIRE_FRESH_ETL=true
ALERT_MAX_ETL_AGE_HOURS=12
SEND_ALERT_ON_LEVEL_CHANGE=false
STREAMLIT_PORT=8501
LANDING_PORT=80
```

---

## 5. Liberação de rede / firewall

### 5.1 Saída obrigatória (HTTPS público)

| Destino | Finalidade |
|---------|------------|
| `api.open-meteo.com` | Meteorologia / biometeo |
| `painelalertas.cemaden.gov.br` | Alertas Cemaden (`wsAlertas2`) |
| `telemetriaws1.ana.gov.br` | SOAP ANA (fallback) |
| `www.ana.gov.br` | REST HidroWebService |
| `dataserver-coids.inpe.br` | Queimadas |
| `servicodados.ibge.gov.br` | Municípios / WASH / demografia |

User-Agent das chamadas: **`ARARAS-Clima-Saude-MT/...`** (identificável pela TI — sem stealth).

### 5.2 Saída rede SES (VPN / VLAN)

| Destino | Porta | Finalidade |
|---------|-------|------------|
| `10.15.1.50` | 1433 | DW |
| `10.15.0.222` | 1433 | IndicaSUS BdSES |
| `10.15.1.71` | 1433 | SISREG |

### 5.3 Entrada

| Origem | Destino | Observação |
|--------|---------|------------|
| Rede SES / VPN usuários autorizados | `:8501` ou proxy HTTPS STI | Preferir HTTPS terminado no proxy |

### 5.4 SSL

Flags `*_SSL_VERIFY=true` por padrão. Só alterar para `false` com registro formal se o proxy SES quebrar a cadeia de certificados (caso excepcional).

---

## 6. Implantação recomendada (Docker Compose)

Arquivos: `docker-compose.yml`, `Dockerfile`, `docker/entrypoint.sh`, `requirements-docker.txt`.

### 6.1 Passos

```bash
# 1) Clone do repositório (ou artefato liberado pelo CIEVS)
git clone <url-repo> araras-mt
cd araras-mt

# 2) Ambiente
cp .env.example .env
# editar .env (credenciais + DATABASE_URL)

# 3) Subir banco
docker compose up -d db

# 4) Build e serviços permanentes
docker compose up -d --build db etl-scheduler app
# rodada extraordinária sob demanda:
docker compose run --rm pipeline
# alertas (após homologação):
# docker compose up -d alerts-scheduler
```

Serviços Compose:

| Serviço | Container | Restart |
|---------|-----------|---------|
| `db` | `sis_clima_db` | unless-stopped |
| `app` | `sis_clima_app` | unless-stopped |
| `pipeline` | `sis_clima_pipeline` | sob demanda |
| `etl-scheduler` | `sis_clima_etl` | unless-stopped |
| `alerts-scheduler` | `sis_clima_alerts` | unless-stopped (opcional; exige ETL fresca) |

Painel: `http://<servidor>:8501` (ou URL do proxy STI).  
Landing (entrada): `http://<servidor>/` — document root `sites/araras-mt/` (serviço Compose `landing`, porta `LANDING_PORT` padrão 80).

### 6.2 Healthcheck

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8501/healthz
# esperado: 200
```

Ou no host Windows:

```powershell
Invoke-WebRequest http://127.0.0.1:8501/healthz -UseBasicParsing
```

### 6.3 Observação de versões

Em `requirements.txt` (Cloud/local alinhado): `streamlit==1.60.0`, **`starlette==1.3.1`** (starlette 1.4 quebra GZip do Streamlit).
Homologar o mesmo pin no build Docker do servidor (`requirements-docker.txt`) para evitar 500 no healthcheck.

---

## 7. Alternativa sem Docker (Windows Server)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Postgres 16 instalado localmente ou remoto
# configurar DATABASE_URL no .env

.\.venv\Scripts\python.exe regenerar_sistema_completo.py
.\.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false
```

Agendamento:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\criar_tarefas_windows.ps1
```

Tarefas: pipeline 07:30 / 12:00 / 17:00; alertas conforme bat.
Scripts: `rodar_pipeline.bat` → `rotina_diaria_ops.py`; `rodar_alertas_once.bat`.

---

## 8. Rotina operacional diária

| Horário sugerido | Ação |
|------------------|------|
| 07:30 | `rotina_diaria_ops.py` (ANA + enrichment + SISREG/pressão + seed) |
| 08:15 | Digest de alertas (se habilitado) |
| 12:00 / 17:00 | Reprocessamento em níveis críticos |
| A cada 6 h | `etl-scheduler` executa pipeline; falha tenta novamente em 15 min |
| Contínuo | Containers `app` + `db` + `etl-scheduler` |

Comando:

```powershell
.\.venv\Scripts\python.exe rotina_diaria_ops.py
# sem VPN:
.\.venv\Scripts\python.exe rotina_diaria_ops.py --offline
```

Validação pós-ciclo:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_ops.py
.\.venv\Scripts\python.exe validar_dw_conexao.py
```

---

## 9. Segurança da informação (checklist STI)

- [ ] `.env` com ACL restrita (somente conta do serviço + admin STI)
- [ ] Segredos fora do Git / fora de tickets em texto claro
- [ ] Postgres não exposto à internet
- [ ] Contas SQL Server somente leitura
- [ ] Alertas desligados até aprovação CIEVS (`SEND_ALERT_ON_LEVEL_CHANGE=false`)
- [ ] Proxy HTTPS + autenticação institucional no acesso ao painel (se política exigir)
- [ ] Backup diário do volume Postgres + retenção de logs
- [ ] Inventário de destinos HTTPS liberados (seção 5)
- [ ] Sem código ofuscado / scrapers stealth (política CIEVS/rede SES)

---

## 10. Contingência

| Falha | Comportamento esperado |
|-------|------------------------|
| VPN/DW fora | Pipeline usa CSV/cache; painel permanece no ar com dados anteriores |
| ANA REST 417/5xx | Retry OAuth; fallback SOAP / CSV |
| Queda do container `app` | `restart: unless-stopped` |
| Postgres indisponível | Contingência: seed SQLite (capacidade reduzida) — **não é o modo produção** |

---

## 11. Aceite sugerido (STI + CIEVS)

| # | Critério de aceite | Evidência |
|---|--------------------|-----------|
| 1 | `healthz` = 200 no servidor | curl / monitoramento |
| 2 | `DATABASE_URL` Postgres ativo | `validar_dw_conexao` / log pipeline |
| 3 | TCP 1433 aos três hosts SES | teste de porta / script |
| 4 | Rotina diária registra log em `logs/` | arquivo do dia |
| 5 | 142 municípios no resumo após regeneração | consulta SQL / painel |
| 6 | Smoke `all_ok` | `scripts/smoke_ops.py` |
| 7 | Sem senhas no repositório | revisão Git |
| 8 | ETL automática saudável e dentro da janela | `logs/etl_scheduler_health.json` + `pipeline_runs` |

Documento complementar de produto/qualidade: `docs/RELATORIO_PRONTIDAO_INSTITUCIONAL.md`.
Checklist de homologação (OK/NOK): `docs/CHECKLIST_HOMOLOGACAO_STI.md` (PDF em `docs/apresentacoes/`).

---

## 12. Contatos e suporte

| Papel | Responsabilidade |
|-------|------------------|
| CIEVS-MT | Regras epidemiológicas, limiares, SOP de alertas, homologação funcional |
| STI-SES | Servidor, rede, contas, proxy, backup, hardening |
| Desenvolvedor / mantenedor técnico | Pipeline, painel, pins de dependência, documentação |

---

## 13. Anexos rápidos

### A — Endpoints públicos usados pelo sistema

- `https://api.open-meteo.com/v1/forecast`
- `https://painelalertas.cemaden.gov.br/wsAlertas2`
- `https://telemetriaws1.ana.gov.br/ServiceANA.asmx`
- `https://www.ana.gov.br/hidrowebservice`
- `https://dataserver-coids.inpe.br/queimadas/...`
- `https://servicodados.ibge.gov.br/api/...`

### B — Entrypoints Docker

`app` | `pipeline` | `pipeline-alerts` | `etl-scheduler` | `alert-once` | `alert-scheduler` | `validate-dw`

### C — Documentos relacionados

- `docs/DOCKER_BASE_UNICA.md`
- `docs/OPERACAO.md`
- `docs/ARQUITETURA.md`
- `docs/ENV_EXISTENTE_COMPATIBILIDADE.md`
- `docs/SENTINELA_SG_E_ANA.md`

---

*Documento destinado à STI para implantação. Ajustes de naming de hosts/contas devem seguir o padrão de nomenclatura da SES sem alterar a arquitetura descrita.*
