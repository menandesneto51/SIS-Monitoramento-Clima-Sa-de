# Matriz viva de homologação — ARARAS MT

**Data:** 2026-09-20  
**Ambiente avaliado:** host operacional CIEVS (Postgres local + painel `:8501`)  
**Branch Git:** `operacional-araras-v10`  
**Servidor SES piloto:** `10.15.0.131` (cutover STI ainda PEND — SSH:22 fechado; :8501 responde Streamlit sem `/healthz` dedicado)

---

## Operação do dia (20/09)

| Item | Status | Evidência |
|------|--------|-----------|
| Docker Desktop + stack prod | OK | app/db/etl/landing/alerts up |
| `/healthz` local | OK | 200 |
| EHF observado (as-of ontem) | OK | data 2026-09-19 · idade 1d (Cuiabá) |
| Smoke hard + soft | OK | **APROVADO_FASE1** (sem ressalvas) |
| Boletim **SE 38/2026** | OK | MD + PDF apresentável (`4f1cbc1`) |
| Alertas scheduler | OK | `sis_clima_alerts` Up |
| Fix EHF sem data futura | OK | `ehf_geocalor.py` ancora em ontem; smoke rejeita idade &lt; 0 |
| Deploy `10.15.0.131` | PEND | STI — rede: :8501 aberto, :22 fechado |

Artefatos SE38:
- `docs/apresentacoes/Boletim_ElNino_SE_38-2026.md`
- `docs/apresentacoes/Boletim_ElNino_SE_38-2026_apresentavel.pdf`
- `docs/apresentacoes/Boletim Informativo Sala de Situação MT El Niño SE 38-2026.pdf`
