# Matriz viva de homologação — ARARAS MT

**Data:** 2026-09-19  
**Ambiente avaliado:** host operacional CIEVS (Postgres local + painel `:8501`)  
**Branch Git:** `operacional-araras-v10` (tag `prod-fase1-20260919`)  
**Servidor SES piloto (referência):** `10.15.0.131`  
**Smoke:** `scripts/smoke_homologacao_producao.py` → `logs/homologacao_smoke.json`

Legenda: OK | NOK | PEND | N/A

---

## Fase 0 — Baseline

| Item | Status | Evidência |
|------|--------|-----------|
| `DATABASE_URL` Postgres | OK | porta 5433 |
| `DATABASE_STRICT_POSTGRES` | OK | true |
| Docker overlay prod | OK | db/etl/app/landing |
| Painel `/healthz` | OK | HTTP 200 |
| ETL health JSON | OK | status success |

---

## Fase 1 — ETL / dados

| Gate | Status | Evidência |
|------|--------|-----------|
| resumo 142 | OK | smoke |
| ocupação sem FALLBACK | OK | |
| EHF / RIT presentes | OK | |
| clima fresco | OK | |
| EHF fresco (≤3d) | OK | idade 1d · ref. 2026-09-18 |
| Parecer 19/09 | **APROVADO_FASE1** | soft_fail vazio |

---

## Fase 2 — Boletins

| Item | Status | Evidência |
|------|--------|-----------|
| SE 37 lâmina climática | OK | mensagem operacional + baseline 29/35 + z Tmáx máx. −0,18 |

---

## Fase 3 — Alertas

| Item | Status | Evidência |
|------|--------|-----------|
| Prévia sem SMTP | OK | `logs/homologacao_alertas/` (Cuiabá EHF+RIT OK) |
| Piloto Cuiabá/Sorriso/Baixada | OK | CSV `ativo=1` |
| 16 ERS ativos | OK | aceite CIEVS 2026-09-19 |
| Envio real / profile alertas | OK | pós-aceite CIEVS |

---

## Fase 4 — Cutover SES

| Item | Status | Evidência |
|------|--------|-----------|
| Ensaio host de prova | OK | `docs/CUTOVER_STI_CHECKLIST.md` |
| Tag freeze | OK | `prod-fase1-20260919` |
| Deploy `10.15.0.131` | PEND | STI |
