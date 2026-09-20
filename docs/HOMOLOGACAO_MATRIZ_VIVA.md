# Matriz viva de homologação — ARARAS MT

**Data:** 2026-09-20  
**Ambiente avaliado:** host operacional CIEVS (Postgres local + painel `:8501`)  
**Branch Git:** `operacional-araras-v10`  
**Servidor SES piloto:** `10.15.0.131` (cutover STI ainda PEND)

---

## Operação do dia (20/09)

| Item | Status | Evidência |
|------|--------|-----------|
| Docker Desktop + stack prod | OK | app/db/etl/landing/alerts up |
| `/healthz` | OK | 200 |
| EHF fresco | OK | idade 1d · ref. 2026-09-19 |
| Smoke hard gates | OK | soft: `etl_health_file` (ETL em curso pós-restart) |
| Boletim **SE 38/2026** | OK | MD + PDF apresentável |
| Alertas scheduler | OK | `sis_clima_alerts` Up |
| Deploy `10.15.0.131` | PEND | STI |

Artefatos SE38:
- `docs/apresentacoes/Boletim_ElNino_SE_38-2026.md`
- `docs/apresentacoes/Boletim_ElNino_SE_38-2026_apresentavel.pdf`
- `docs/apresentacoes/Boletim Informativo Sala de Situação MT El Niño SE 38-2026.pdf`
