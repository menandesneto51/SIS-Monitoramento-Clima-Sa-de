# Pacote de produção — ARARAS MT

**Branch operacional (produção):** `operacional-araras-v10`  
**Commit de referência:** HEAD dessa branch (ex.: IRM/RIT frescor).  
**Entrada do site/painel:** `streamlit_app.py` → `app_v9.py`.

## Política de branches (caminho seguro)

| Branch | Papel |
|--------|--------|
| **`operacional-araras-v10`** | Fonte da verdade do ARARAS MT — push, deploy e releases |
| **`legacy-vigia-main`** | Arquivo do histórico antigo VIGIA (cópia de `origin/main` em 2026-09-12) |
| **`main` (GitHub)** | Ainda aponta para o legado VIGIA — **não** usar force-push sem decisão explícita e Cloud já migrado |
| Local `main` | Pode existir; **rastreia** `origin/operacional-araras-v10` (`git push` / `git pull` nessa upstream) |

```powershell
# Desenvolvimento / publicação segura
git checkout main
git pull                    # puxa operacional-araras-v10
git push origin HEAD:operacional-araras-v10
```

**Não** execute `git push --force origin main` no fluxo diário.

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
# Painel local (reaplica IRM/RIT/compostos na carga)
.\.venv\Scripts\streamlit.exe run streamlit_app.py

# ETL (uma rodada) — inclui enrich operacional + multirisco
.\.venv\Scripts\python.exe -m sisclima.pipeline

# Alertas (uma vez, com gate de frescor ETL + refresh IRM/RIT antes do digest)
.\.venv\Scripts\python.exe -m sisclima.alerts.scheduler --once

# Decretos (CLI)
.\.venv\Scripts\python.exe scripts\buscar_decretos_emergencia_araras.py --dias 60

# Boletim semanal (refresh EHF→IRM→RIT→compostos no builder)
.\.venv\Scripts\python.exe -m sisclima.engines.boletim_el_nino_semanal --no-dw
```

### Frescor multirisco (obrigatório)

Ordem única: **EHF → IRM → RIT → compostos** (`sisclima/engines/resumo_frescor.py`).

| Superfície | Quando atualiza |
|---|---|
| ETL / `run_operational_enrichment` | Ao final da rodada (antes de alerta inteligente) |
| Pipeline pós-STAR | Após GeoCalor da rodada |
| Alertas (`scheduler` / digest) | **Antes** de montar e enviar o digest |
| Painel (`app_v9`) | Na carga do `resumo_municipal_atual` |
| Boletim El Niño | No builder, antes do snapshot RIT |

Indicadores novos: `indice_resiliencia_municipal_0_100` (capacidade), `rit_score_rede` (fragilidade), `gap_fumaca_nebulizacao`, `pressao_x_resiliencia`. Não alteram `nivel` / `nivel_predicao_7d`.
## Deploy Streamlit Cloud

- **Branch:** `operacional-araras-v10` (não usar `main` legado VIGIA)
- **Main file:** `streamlit_app.py`
- Secrets: copiar de `.streamlit/secrets.toml.example` (nunca versionar `.env`)

## Não versionar em produção

- `.env`, credenciais, `data/output/*.db` locais
- PDFs intermediários `*_apresentavel_v4` … `v9`
- Pasta `docs/apresentacoes/_qa_se34/`

## Limitações conhecidas (não bloqueiam este pacote)

- Conectores do Plano SISAGUA / entomologia / denúncias leem CSV em `data/local/vigilancia/` (exemplos incluídos); sem CSV a UI mostra lacuna explícita
- Fontes DW marcadas `pendente_sql_dw` no catálogo de agravos
- Cobertura hidrológica municipal parcial no boletim
- PM proxy Open-Meteo desligado por default (`USE_OPENMETEO_PM_PROXY=false`)

## Hardening de segurança (mínimo)

- `?interno=1` só com `ARARAS_ALLOW_LOCAL_PREVIEW=true` **e** Host loopback (nunca LAN/Cloud)
- Sessão revalida status/nível no banco a cada acesso
- Rate-limit de login (bloqueio após falhas repetidas)
- Postgres Compose **sem** porta publicada no host (só rede Docker)
- E-mails de alerta com vários destinatários usam **Bcc**
- OIDC STI não auto-promove a SES salvo `STI_OIDC_AUTO_SES=true`

---

## Validação pré-produção (2026-09-19)

| Agente / gate | Resultado | Notas |
|---|---|---|
| **Security Review** | APROVADO | Sem achados medium+ no diff operacional |
| **Bugbot** | APROVADO após correção | YTD climático agora agrega **1 valor por ano** (não pool diário entre anos) |
| **Smoke homologação** | `APROVADO_FASE1_COM_RESSALVAS` | Hard gates OK; soft: `ehf_fresco` se GeoCalor >3d (fonte externa) |
| **Docker overlay prod** | OK | `docker-compose.yml` + `docker-compose.prod.yml`; `/healthz` 200 |
| **Alertas** | HOLD | Manter `SEND_ALERT_ON_LEVEL_CHANGE=false` até aceite CIEVS |

### GO / NO-GO

- **GO Fase 1 (painel + ETL + Postgres)** no servidor SES, branch `operacional-araras-v10`.
- **NO-GO alertas reais** até aceite CIEVS + frescor EHF ≤3 dias no smoke.
- Cutover: seguir `docs/PLANO_CUTOVER_PRODUCAO.md` + `docs/CHECKLIST_HOMOLOGACAO_STI.md`.

```powershell
# Smoke no host (após ETL)
.\.venv\Scripts\python.exe scripts\smoke_homologacao_producao.py --skip-rede
# Esperado: all_ok=true; soft_fail só ehf_fresco se atraso GeoCalor

# Subir produção (servidor SES)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d db
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build etl-scheduler app landing
```
