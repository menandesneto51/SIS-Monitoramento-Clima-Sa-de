# Análise de consistência pré-produção — ARARAS MT

**Data:** 2026-08-29  
**Ambiente analisado:** Postgres Docker local (`resumo_municipal_atual` = 142)  
**Objetivo:** listar inconsistências de cálculo/indicadores antes do cutover.

---

## Veredito

**C1 corrigido em 2026-08-29** (fallback estadual removido; enrich + reclassificação aplicados).  
Cutover piloto pode seguir após smoke CIEVS; demais itens A/M permanecem como declaração ou Fase 2.

| Severidade | Qtd |
|------------|-----|
| Crítico (corrigir antes) | 0 (C1 feito) |
| Alto (corrigir ou declarar) | 4 |
| Médio / Fase 2 | 5 |
| OK nesta rodada | vários |

### Pós-C1 (verificado)

| Checagem | Resultado |
|----------|-----------|
| `INDICASUS_TEMPO_REAL` | 39 |
| `SEM_LEITOS_INDICASUS` | 103 |
| `*FALLBACK*` | **0** |
| `com_ocupacao` no enrich | 39 |
| Níveis após reclassificar | 63 roxa / 55 vermelha / 22 laranja / 2 amarela |

`indice_pressao_saude` pode subir em mun. sem IndicaSUS (renormaliza pesos nos outros pilares) — revisar M6 depois, sem reintroduzir média estadual.

---

**Status (2026-08-29):** CORRIGIDO — `pipeline.py` / `operational_enrichment.py` não fazem mais `fillna` estadual; rótulo `SEM_LEITOS_INDICASUS`; `stages.py` ignora ocupação nula no max de estágio; texto de ajuda em `app_v9.py` alinhado; enrich+reclassify rodados (`com_ocupacao=39`, fallback=0).

---

## C1 — CRÍTICO: ocupação IndicaSUS inventada (fallback estadual)

**Evidência**

| Fonte | Municípios | Ocupação |
|-------|------------|----------|
| `INDICASUS_TEMPO_REAL` | 39 | 0–78% (mediana ~33%) |
| `INDICASUS_TEMPO_REAL_ESTADUAL_FALLBACK` | **103** | **todos = 45,631068%** (média estadual) |

`hospital_ocupacao_municipio` tem **39** IBGE reais. O overlap com o resumo bate (diff = 0). Os outros 103 recebem a média do estado.

**Onde grava**

- `sisclima/pipeline.py` (~354–366): `fillna(valor_estado)` + rótulo `…ESTADUAL_FALLBACK`
- `sisclima/engines/operational_enrichment.py` (~540–549): idem (`INDICASUS_ESTADUAL_FALLBACK`)

**Impacto**

- `ocupacao_leitos_pct` entra em `classify_stage` / pressão / alertas.
- Níveis atuais entre fallback: 45 roxa + 39 vermelha + 17 laranja + 2 amarela — parte do sinal pode ser **calor/ar reais**, mas a ocupação **não** é territorial.
- Digest SES e boletim leem o resumo persistido → ecoam 45,6% “local” em mun. sem leitos IndicaSUS.
- Texto de ajuda em `app_v9.py` (§ ocupação) ainda diz que o painel “aplica fallback estadual” — desalinhado da regra desejada (não inventar).

**Correção recomendada**

1. Remover `fillna` da média estadual em `pipeline.py` e `operational_enrichment.py`.
2. Deixar `ocupacao_leitos_pct` nulo e `fonte_ocupacao=SEM_LEITOS_INDICASUS` (como o enrich da UI já tenta).
3. Garantir que `classify_stage` / pressão **ignoram** ocupação nula (não tratam NaN como 0 nem como 45%).
4. Re-rodar ETL + reclassificar resumo.
5. Ajustar texto de ajuda e métricas da aba Assistência.

---

## A — Alto (corrigir ou declarar no go-live)

### A1. Cobertura IndicaSUS estrutural (~39/142)

Não é bug de código após C1: BdSES só mapeia municípios com leitos + `LocalidadeId`. Declarar no plantão: “ocupação real só onde há cadastro IndicaSUS”.

### A2. SIVEP oficial ausente no DW

`epi_sivep_srag` ≈ 90 linhas via fallback `VW_SINAN_…SRAG`. Sem `dbo.SIVEP_SRAG`. Documentar; não inventar casos.

### A3. Zika / alguns agravos DW

`VW_SINAN_ZIKA` ausente (soft-fail). Outros conectores do Plano ainda `aguardando_fonte` (SISAGUA, entomologia, denúncias).

### A4. Texto vs código (ocupação)

Help em Cálculos (`app_v9.py` ~3268) contradiz a política “não inventar”. Corrigir junto com C1.

### A5. Plano El Niño — situação vazia no quadro

Rodada de checagem: 88 indicadores com `situacao=""`. Provável falta de **Atualizar indicadores automáticos** / leituras gravadas. Antes da Sala em produção: rodar automáticos + cobrança e validar filas.

---

## M — Médio / Fase 2

| ID | Tema | Notas |
|----|------|-------|
| M1 | Hidrologia | `hidro_risco_municipal` = 10 mun.; cotas OK (max 699, nenhum ≥5000) |
| M2 | OSRM / cobertura trajeto | `COBERTURA_USAR_TRAJETO=false` — manter até OSRM interno |
| M3 | Fan-out municipal | 142 SMS `PENDENTE`; não ligar `ALERT_FANOUT_ENABLED` |
| M4 | ERS individuais | Só lista agregada `rede-cievs-mt-e-ers@…`; 16 e-mails pendentes |
| M5 | SMTP Titan | Primário Gmail OK; Titan 535 — senha ou manter Gmail |
| M6 | Pressão / índices compostos | `indice_pressao_saude` 65–81 em quase todos — revisar **depois** de C1 (hoje contaminado pela ocupação 45,6%) |
| M7 | Alertas off no cutover | `SEND_ALERT_ON_LEVEL_CHANGE=false` até SOP CIEVS |

---

## OK nesta rodada (sanity)

| Checagem | Resultado |
|----------|-----------|
| `resumo_municipal_atual` | **142**, IBGE único, len=7 |
| Distribuição níveis | 63 roxa / 55 vermelha / 22 laranja / 2 amarela |
| Tmáx | 31–40 °C (plausível) |
| UTCI/proxy | 30,1–38,2 |
| Risco 3d | ~2,4–29,2 |
| PM2,5 | 142 mun.; max ~82 |
| SISREG | **140** |
| Estoque / infra | 2496 / 1248 linhas |
| SINAN agravos / arbovírus | populados |
| Ocupação real (39) | coerente com tabela live (diff 0) |
| Hidro cota suspeita | 0 |

---

## Ordem de correção sugerida

1. **C1** — eliminar fallback estadual de ocupação + re-ETL + reclassificar.  
2. **A4** — alinhar texto de ajuda.  
3. **A5** — atualizar automáticos do Plano e revisar cobrança.  
4. Declarar **A1–A3**, **M1–M5** no aviso de go-live.  
5. Reavaliar **M6** (pressão) após C1.  
6. Cutover piloto com alertas off (`PLANO_CUTOVER_PRODUCAO.md`).

---

## Como repetir a checagem

```powershell
docker compose run --rm --no-deps -v "${PWD}:/app" -w /app -e PYTHONPATH=/app --entrypoint "" pipeline python tmp/consistencia_pre_prod.py
```

Após C1, esperar: `fonte_ocupacao` sem `ESTADUAL_FALLBACK`; ~39 com `INDICASUS_TEMPO_REAL` e demais `SEM_LEITOS_INDICASUS` ou nulo.
