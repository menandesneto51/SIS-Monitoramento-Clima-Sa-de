# Checklist de Homologação STI — SIS Clima-Saúde MT

**Servidor / ambiente:** _______________________________  
**Data:** ____/____/________  
**Responsável STI:** _________________________________  
**Responsável CIEVS:** ________________________________  
**Versão / branch:** `painel-v9`  
**Documento base:** `docs/STI_IMPLANTACAO_SERVIDOR_SES.md`

**Legenda:** `OK` = atendido · `NOK` = falhou · `N/A` = não aplicável · `PEND` = pendente

---

## 1. Pré-requisitos de infraestrutura

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 1.1 | Servidor com ≥ 4 vCPU / 8 GB RAM / 40 GB livres | | | | | |
| 1.2 | Docker Engine + Compose **ou** Python 3.12 + venv | | | | | |
| 1.3 | Conta de serviço OS (não perfil pessoal) | | | | | |
| 1.4 | Pasta do sistema com permissão só para conta serviço + admin | | | | | |
| 1.5 | Backup agendado do volume Postgres / disco de dados | | | | | |

---

## 2. Rede e firewall

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 2.1 | Saída HTTPS: `api.open-meteo.com` | | | | | |
| 2.2 | Saída HTTPS: `painelalertas.cemaden.gov.br` | | | | | |
| 2.3 | Saída HTTPS: `telemetriaws1.ana.gov.br` | | | | | |
| 2.4 | Saída HTTPS: `www.ana.gov.br` (HidroWeb REST) | | | | | |
| 2.5 | Saída HTTPS: `dataserver-coids.inpe.br` | | | | | |
| 2.6 | Saída HTTPS: `servicodados.ibge.gov.br` | | | | | |
| 2.7 | Saída TCP 1433 → `10.15.1.50` (DW) | | | | | |
| 2.8 | Saída TCP 1433 → `10.15.0.222` (IndicaSUS) | | | | | |
| 2.9 | Saída TCP 1433 → `10.15.1.71` (SISREG) | | | | | |
| 2.10 | Entrada painel `:8501` (ou proxy HTTPS STI) só rede SES | | | | | |
| 2.11 | Postgres `:5432` **não** publicado na internet | | | | | |

**Teste rápido (no servidor):**

```powershell
Test-NetConnection 10.15.1.50 -Port 1433
Test-NetConnection 10.15.0.222 -Port 1433
Test-NetConnection 10.15.1.71 -Port 1433
```

---

## 3. Credenciais e `.env`

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 3.1 | `.env` criado a partir de `.env.producao.example` | | | | | |
| 3.2 | Conta serviço DW (somente leitura) preenchida | | | | | |
| 3.3 | Conta serviço IndicaSUS / BdSES preenchida | | | | | |
| 3.4 | Conta serviço SISREG preenchida | | | | | |
| 3.5 | `DATABASE_URL` aponta para Postgres do servidor | | | | | |
| 3.6 | Senha Postgres forte (não default `sisclima_trocar`) | | | | | |
| 3.7 | Credenciais ANA REST no `.env` (se REST ativo) | | | | | |
| 3.8 | `.env` **fora** do Git / ACL restrita | | | | | |
| 3.9 | `SEND_ALERT_ON_LEVEL_CHANGE=false` até homologação CIEVS | | | | | |

---

## 4. Deploy Docker (ou equivalente)

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 4.1 | `docker compose up -d db` saudável | | | | | |
| 4.2 | `docker compose up -d --build app` no ar | | | | | |
| 4.3 | Pins: Streamlit ≥ 1.60 e `starlette==1.3.1` | | | | | |
| 4.4 | Volumes persistentes: `data/`, `logs/`, `sis_pgdata` | | | | | |
| 4.5 | `config/` e `sql/` montados / disponíveis | | | | | |

```bash
docker compose ps
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8501/healthz
# esperado: 200
```

---

## 5. Validação funcional (aceite técnico)

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 5.1 | `GET /healthz` → **200** | | | | | |
| 5.2 | Home do painel carrega sem erro 500 | | | | | |
| 5.3 | `validar_dw_conexao.py` conecta ao DW | | | | | |
| 5.4 | Pipeline / `rotina_diaria_ops.py` conclui sem crash | | | | | |
| 5.5 | `resumo_municipal_atual` com ~142 municípios | | | | | |
| 5.6 | `scripts/smoke_ops.py` → `all_ok: true` | | | | | |
| 5.7 | Índice de pressão **não** flat (~20 para todos) | | | | | |
| 5.8 | Hidro ANA: tabela `hidro_risco_municipal` populada | | | | | |
| 5.9 | Ocupação IndicaSUS presente (LIVE ou CACHE marcado) | | | | | |
| 5.10 | Log do dia gravado em `logs/` | | | | | |

```powershell
.\.venv\Scripts\python.exe validar_dw_conexao.py
.\.venv\Scripts\python.exe rotina_diaria_ops.py
.\.venv\Scripts\python.exe scripts\smoke_ops.py
```

---

## 6. Agendamento e operação contínua

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 6.1 | Rotina diária agendada (07:30 ou cron equivalente) | | | | | |
| 6.2 | Reprocessamento 12:00 / 17:00 (se acordado) | | | | | |
| 6.3 | `alerts-scheduler` **desligado** ou digest sem envio real | | | | | |
| 6.4 | Contato STI de plantão / runbook de restart documentado | | | | | |
| 6.5 | Monitoramento básico (healthz + disco + container) | | | | | |

Windows (opcional):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\criar_tarefas_windows.ps1
```

---

## 7. Segurança

| # | Item | OK | NOK | N/A | PEND | Evidência / observação |
|---|------|:--:|:---:|:---:|:----:|------------------------|
| 7.1 | Sem senhas em tickets / repositório | | | | | |
| 7.2 | Contas SQL somente leitura | | | | | |
| 7.3 | Proxy/SSO institucional na frente do painel (se política) | | | | | |
| 7.4 | User-Agent institucional permitido (`SIS-Clima-Saude-MT/...`) | | | | | |
| 7.5 | Sem scrapers ofuscados / bypass de WAF | | | | | |
| 7.6 | Retenção de logs e política de purge definidas | | | | | |

---

## 8. Aceite integrado

| Resultado | Marcar |
|-----------|:------:|
| **Homologado para piloto interno CIEVS** | ☐ |
| **Homologado para produção 24×7** | ☐ |
| **Não homologado** (listar bloqueios abaixo) | ☐ |

**Bloqueios / pendências:**

1. ________________________________________________________________
2. ________________________________________________________________
3. ________________________________________________________________

**Assinaturas**

| Papel | Nome | Assinatura | Data |
|-------|------|------------|------|
| STI | | | |
| CIEVS | | | |

---

## 9. Referências

| Documento | Caminho |
|-----------|---------|
| Pacote técnico STI | `docs/STI_IMPLANTACAO_SERVIDOR_SES.md` / `.pdf` |
| Relatório de prontidão | `docs/RELATORIO_PRONTIDAO_INSTITUCIONAL.md` / `.pdf` |
| Env produção (modelo) | `.env.producao.example` |
| Operação diária | `docs/OPERACAO.md` |
| Docker | `docs/DOCKER_BASE_UNICA.md` |

---

*Checklist para preenchimento em campo. Não substitui parecer formal da STI nem autorização da gestão SES.*
