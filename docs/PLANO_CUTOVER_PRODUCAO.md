# Plano de cutover — ARARAS MT (dia D)

**Objetivo:** colocar o painel em produção/piloto no servidor SES com Postgres + ETL, sem alertas reais até aceite CIEVS.  
**Documentos-base:** `docs/CHECKLIST_HOMOLOGACAO_STI.md`, `docs/STI_IMPLANTACAO_SERVIDOR_SES.md`, `docs/RELEASE_PRODUCAO.md`.  
**Branch:** `araras-mt` / tag de release do dia.

---

## 0. Critério de “go”

Só seguir se **todos** abaixo forem verdade:

| # | Critério |
|---|----------|
| G1 | Postgres é a base principal (`DATABASE_URL` postgresql) — **não** seed SQLite |
| G2 | ETL do dia concluiu com `status=success` e log em `logs/` |
| G3 | `resumo_municipal_atual` ≈ 142 municípios |
| G4 | Senhas fortes (Postgres + admin painel); `.env` fora do Git |
| G5 | `SEND_ALERT_ON_LEVEL_CHANGE=false` (ou `alerts-scheduler` parado) |
| G6 | STI e CIEVS cientes do cutover e do contato de rollback |

Se algum G* falhar → **não publicar**; corrigir e remarcar.

---

## 1. D−1 (véspera)

| # | Ação | Responsável | Feito |
|---|------|-------------|:----:|
| 1.1 | Tag/commit de release limpo (sem `.env`, DB, `data/output`) | Dev/CIEVS | ☐ |
| 1.2 | Copiar artefato + `.env.producao.example` → servidor | STI | ☐ |
| 1.3 | Preencher `.env` (DW, IndicaSUS, SISREG, Postgres forte) | STI + CIEVS | ☐ |
| 1.4 | Testar TCP 1433: DW `10.15.1.50`, IndicaSUS `10.15.0.222`, SISREG `10.15.1.71` | STI | ☐ |
| 1.5 | Backup vazio/restore de teste do volume Postgres (ou snapshot) | STI | ☐ |
| 1.6 | Criar usuários painel interno (além do admin) | CIEVS | ☐ |
| 1.7 | Confirmar: `COBERTURA_USAR_TRAJETO=false` até OSRM interno | Dev | ☐ |

---

## 2. Dia D — subir

Ordem fixa (não pular):

```powershell
# No servidor SES, pasta do projeto
docker compose up -d db
# aguardar healthy
docker compose up -d --build etl-scheduler app
docker compose ps
curl -s -o /nul -w "%{http_code}" http://127.0.0.1:8501/healthz
# esperado: 200
```

| # | Ação | Feito |
|---|------|:----:|
| 2.1 | `db` healthy | ☐ |
| 2.2 | `etl-scheduler` up (primeira ETL ou `docker compose run --rm pipeline`) | ☐ |
| 2.3 | `app` up; `/healthz` = 200 | ☐ |
| 2.4 | Proxy HTTPS / ACL rede SES apontando para `:8501` | ☐ |
| 2.5 | **Não** subir `alerts-scheduler` com envio real | ☐ |

---

## 3. Dia D — validar (aceite rápido, ~30–45 min)

### 3.1 Dados

| # | Checagem | Esperado (piloto atual) | Feito |
|---|----------|-------------------------|:----:|
| 3.1.1 | `resumo_municipal_atual` | ~142 | ☐ |
| 3.1.2 | IndicaSUS `hospital_ocupacao_municipio` | ≥ ~39 mun. tempo real (BdSES); demais sem inventar ocupação | ☐ |
| 3.1.3 | `ops_sisreg_municipio` | ~140 | ☐ |
| 3.1.4 | SIVEP / SRAG | série ou fallback SINAN SRAG documentado | ☐ |
| 3.1.5 | Fontes no painel | Postgres + data do dia; sem depender só do seed | ☐ |

### 3.2 Funcional (CIEVS)

| # | Checagem | Feito |
|---|----------|:----:|
| 3.2.1 | Painel público carrega (mapa colorido, não cinza) | ☐ |
| 3.2.2 | Login restrito (admin + 1 usuário CIEVS) | ☐ |
| 3.2.3 | Assistência: cobertura IndicaSUS real sem fallback estadual em massa | ☐ |
| 3.2.4 | Aba SIVEP / Sentinela SG unificada | ☐ |
| 3.2.5 | Inteligência: alerta estatístico + risco dominante coloridos | ☐ |
| 3.2.6 | Sem bloco “Ajudante CIEVS / Meningites / USE_LLM…” | ☐ |
| 3.2.7 | Sazonalidade: z-score mês atual vs mesmo mês histórico | ☐ |
| 3.2.8 | Operacional: estoque / infra / SISREG visíveis | ☐ |

Smoke opcional:

```powershell
docker compose run --rm --no-deps pipeline python scripts/smoke_ops.py
```

---

## 4. Dia D — comunicar

| # | Ação | Feito |
|---|------|:----:|
| 4.1 | Aviso interno CIEVS: URL, login, o que é piloto vs pleno | ☐ |
| 4.2 | Registrar limitações conhecidas (abaixo) no plantão | ☐ |
| 4.3 | Assinar seção 8 do `CHECKLIST_HOMOLOGACAO_STI.md` (piloto **ou** 24×7) | ☐ |

### Limitações a declarar no go-live (não são regressão)

- IndicaSUS: só municípios com leitos + `LocalidadeId` no BdSES (~39 hoje).
- SIVEP: sem export oficial → fallback `VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE`.
- `VW_SINAN_ZIKA` ausente no DW.
- SAN/SISVAN, SISAGUA, entomologia: Fase 2.
- OSRM público desligado (`COBERTURA_USAR_TRAJETO=false`).
- Alertas externos: **off** até SOP CIEVS.

---

## 5. Rollback (se algo crítico falhar)

**Critérios para rollback:** painel 500 persistente; ETL quebrada no dia; Postgres inacessível; dados claramente do seed SQLite; vazamento de credencial.

```powershell
# 1) Parar app/etl (manter db se for só UI)
docker compose stop app etl-scheduler

# 2) Se release novo quebrou: voltar tag anterior + recreate
git checkout <tag-anterior>
docker compose up -d --build app etl-scheduler

# 3) Contingência só leitura (capacidade reduzida — NÃO é produção)
# apontar temporariamente seed Cloud / SQLite conforme SOP STI — documentar o desvio
```

| # | Após rollback | Feito |
|---|---------------|:----:|
| 5.1 | Avisar STI + CIEVS | ☐ |
| 5.2 | Preservar logs do incidente em `logs/` | ☐ |
| 5.3 | Abrir bloqueio no checklist (seção 8) | ☐ |

---

## 6. D+1 … D+7 (estabilização)

| # | Ação | Feito |
|---|------|:----:|
| 6.1 | Conferir ETL automática (intervalo 6 h) e health JSON | ☐ |
| 6.2 | Backup diário Postgres verificado | ☐ |
| 6.3 | Revisar Fontes e qualidade 1×/dia no plantão | ☐ |
| 6.4 | Coletar bugs de UX (mapa, abas, login) | ☐ |
| 6.5 | Só então: avaliar ligar `alerts-scheduler` + SOP de canais | ☐ |

---

## 7. Contatos do cutover

| Papel | Nome | Telefone / canal |
|-------|------|------------------|
| STI plantão | | |
| CIEVS plantão | | |
| Responsável técnico ARARAS | | |

**Data do cutover:** ____/____/________  
**Resultado:** ☐ Piloto interno · ☐ Produção 24×7 · ☐ Abortado (rollback)
