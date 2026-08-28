# Pacote de produção — ARARAS MT

**Commit de referência:** HEAD desta branch (`araras-mt` / `operacional-araras-v10`).  
**Entrada do site/painel:** `streamlit_app.py` → `app_v9.py`.

## Escopo publicado

| Domínio | O que entra em produção | Onde |
|---------|-------------------------|------|
| Painel público | Visão leiga, mapas, El Niño resumido, guia do leitor | `app_v9.py` (`modo_publico`), `sisclima/ui/painel_publico.py`, `theme.py` |
| Painel restrito | Mesma navegação + Fontes, Prontidão, TITAN, Assistência, Alertas, Sala | `app_v9.py`, `sisclima/auth/access.py` |
| Padronização visual | Tokens SES-MT, header, cards, callouts | `sisclima/ui/theme.py`, `assets/ses-panel.css`, `assets/branding/` |
| Boletim El Niño | SE 34-2026 validado (MD + PDF apresentável V10/V10.2) | `sisclima/engines/boletim_el_nino*`, `docs/apresentacoes/Boletim_*` |
| Decretos | Busca IOMAT/imprensa + painel restrito na aba El Niño | `sisclima/ingestion/iomat_decretos.py`, `sisclima/ui/decretos_emergencia.py`, `scripts/buscar_decretos_*` |
| Comunicação × indicadores | Cobrança/ofícios por área, PDFs e e-mails | `sisclima/plano/cobranca.py`, `sala_situacao_plano.py`, `docs/apresentacoes/cobranca_emails/` |
| Alertas | Scheduler + gate ETL, digest multinível, SMTP/Telegram/WhatsApp | `sisclima/alerts/*`, `engines/alertas_multinivel.py`, `docker-compose` `alerts-scheduler` |
| ETL / atualização | Pipeline, etl-scheduler, rotina diária, seed Cloud | `sisclima/pipeline.py`, `etl_scheduler.py`, `rotina_diaria_ops.py`, `data/cloud/sis_cloud_seed.db` |
| Plano El Niño / Sala | 88 indicadores, validação CIEVS, acessos | `sisclima/plano/*`, `ui/sala_situacao_plano.py`, `config/plano_el_nino_*.yaml` |

## Operação rápida

```powershell
# Painel local
.\.venv\Scripts\streamlit.exe run streamlit_app.py

# ETL (uma rodada)
.\.venv\Scripts\python.exe -m sisclima.pipeline

# Alertas (uma vez, com gate de frescor)
.\.venv\Scripts\python.exe -m sisclima.alerts.scheduler --once

# Decretos (CLI)
.\.venv\Scripts\python.exe scripts\buscar_decretos_emergencia_araras.py --dias 60

# Boletim semanal
.\.venv\Scripts\python.exe -m sisclima.engines.boletim_el_nino_semanal --no-dw
```

## Deploy Streamlit Cloud

- **Branch:** `araras-mt`
- **Main file:** `streamlit_app.py`
- Secrets: copiar de `.streamlit/secrets.toml.example` (nunca versionar `.env`)

## Não versionar em produção

- `.env`, credenciais, `data/output/*.db` locais
- PDFs intermediários `*_apresentavel_v4` … `v9`
- Pasta `docs/apresentacoes/_qa_se34/`

## Limitações conhecidas (não bloqueiam este pacote)

- Alguns conectores do Plano ainda em espera de tabela (`SISAGUA`, entomologia, denúncias)
- Fontes DW marcadas `pendente_sql_dw` no catálogo de agravos
- Cobertura hidrológica municipal parcial no boletim
