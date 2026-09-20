# Matriz viva de homologação — ARARAS MT

**Data:** 2026-09-20  
**Ambiente Fase 1 (cutover operacional):** host CIEVS — Postgres `127.0.0.1:5433` + painel `:8501` + landing `:80`  
**Branch / tag:** `operacional-araras-v10` · `prod-fase1-20260919`  
**Servidor SES produção 24×7:** `10.15.0.131` — **PEND STI** (SSH:22 fechado; `:8501` responde Streamlit sem marcador ARARAS no HTML estático)

---

## Plano «Próximos passos pós-validação» — status

| # | Entrega | Status | Evidência |
|---|---------|--------|-----------|
| 1 | Git release YTD + docs + tag | **OK** | `9ef6aee` · tag `prod-fase1-20260919` no remoto |
| 2 | Cutover Fase 1 (compose prod) | **OK** | `sis_clima_{db,etl,app,landing}` Up; `/healthz` 200; `DATABASE_STRICT_POSTGRES=true` |
| 3 | EHF fresco (sem soft `ehf_fresco`) | **OK** | as-of **2026-09-19** · idade **1d** · smoke **APROVADO_FASE1** |
| 4 | Piloto alertas + profile alertas | **OK** | `logs/piloto_alertas_validacao/report.json` (enviado 19/09); `sis_clima_alerts` Up; `SEND_ALERT_ON_LEVEL_CHANGE=true` pós-CIEVS |
| 5 | Fan-out ERS oficiais | **OK** | CSV 22×`ativo=1` (16 ERS + piloto); `docs/REGIONAIS_ALERTAS_PENDENTE.md` |

---

## Smoke 2026-09-20

- Parecer: **APROVADO_FASE1** (soft_fail vazio)
- 142 municípios · ocupação sem FALLBACK · EHF/RIT presentes · ETL `status=success`
- Fix anti-forecast: `sisclima/engines/ehf_geocalor.py` (`1f58ec3`)

## Artefatos Sala

- SE 38/2026: MD + PDF (`4f1cbc1`)

## Fora deste ciclo (backlog)

- Cutover físico 24×7 em `10.15.0.131` (STI)
- Force-push `main` legado VIGIA
- Conectores SISAGUA / entomologia CSV; `pendente_sql_dw`
