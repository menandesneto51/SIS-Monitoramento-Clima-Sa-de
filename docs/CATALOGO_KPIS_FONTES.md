# Catálogo priorizado — KPIs e fontes (SIS Clima-Saúde)

Mapa operacional do que agregar ao núcleo municipal → índices → alertas, alinhado à visão CIEVS/SES-MT.
Implementação sob `painel-v9`; este documento fecha o catálogo e aponta onde cada bloco entrou no código.

## Arquitetura (não reinventar)

```text
Fontes (DW / CSV / API) → pipeline_enrichment → resumo_municipal_atual
  → índices compostos → alertas multinível → app_v9 / digest CIEVS
```

Âncoras: `sisclima/pipeline.py`, `sisclima/engines/panel_indicators.py`,
`sisclima/engines/indice_pressao_saude.py`, `sisclima/engines/alertas_multinivel.py`,
`docs/VISAO_OPERACIONAL_SIS_CLIMA_SAUDE.md`, `docs/ALINHAMENTO_ADAPTASUS_MS.md`.

## Prioridade 1 — lacunas documentadas

| Bloco | Status | Encaixe |
|-------|--------|---------|
| Confiabilidade DW / IndicaSUS / SISREG | Entregue | `fonte_status_regeneracao` em `regenerar_sistema_completo.py`; DW via `DW_ENV_FILE` / Meningites-Ondas |
| Queimadas / fumaça | Entregue | `inpe_queimadas` → `queimadas_focos_municipal` + merge no resumo / tensão climática |
| Extremos de frio | Entregue | `onda_fria_*` em biometeo + UI Clima/TITAN + digest |
| WASH (AdaptaSUS) | Entregue (estrutural) | `wash_municipal` (Censo IBGE) + risco AdaptaSUS |
| SAN (AdaptaSUS) | Lacuna explícita | stub `san_municipal` (`status=lacuna`); não interpretar como risco zero |
| Fan-out territorial | Preparado | `contacts.validate` / `plan_fanout` / `ALERT_FANOUT_DRY_RUN`; envio real só com planilha + flag |

## Prioridade 2 — sala de situação

| KPI | Status |
|-----|--------|
| População vulnerável exposta | Entregue (`pop_vulneravel_exposta`, `indice_exposicao_vulneravel`) |
| Perspectiva de pressão 14d | Entregue (`perspectiva_pressao_14d_municipal` — persistência + clima; **não** nowcast epi) |
| Predição climática 14d | Entregue (`predicao_calor_14d_*`, frescor de fontes) |
| Níveis de rio (ANA ≈ Vigibarragens) | Entregue (`niveis_rios_municipal`) |
| Dias-leito UTI / fila SISREG por especialidade / APS-ACS / UPA surge | Roadmap |
| Nowcast epidemiológico 14–28d (atraso SIVEP) | Roadmap (exige SIVEP preenchido) |

## Prioridade 3 — fontes externas (encaixe MT)

| Fonte | Status |
|-------|--------|
| INPE Queimadas | Entregue |
| ANA telemetria / cotas | Entregue (nível de rio) |
| CAMS / QualAR / ERA5 / e-SUS Notifica / rumor formalizado | Roadmap |

## Prioridade 4 — qualidade / governança

| Indicador | Status |
|-----------|--------|
| Status por fonte na regeneração | Entregue (`fonte_status_regeneracao`) |
| Idade do dado / frescor | Entregue (`fonte_frescor_estado`, `data_freshness`) |
| Completude municipal / concordância SIS×INMET / auditoria pós-evento | Parcial / docs OPERACAO |

## Padrão de agregação (para novos blocos)

1. Ingestão em `sisclima/ingestion/` com flag `USE_*`
2. Tabela dedicada + 3–8 colunas no `resumo_municipal_atual`
3. Peso em índice existente (`panel_indicators` / pressão / AdaptaSUS)
4. Seção em `app_v9.py` + glossário em `sisclima/ui/explainers.py`
5. Entrada em `exportar_snapshot_cloud.py` `TABLES`
6. Frase operacional no digest multinível

## Sequência de valor (servidor SES)

1. Ligar DW + IndicaSUS + SISREG live a cada regeneração (`DW_PASSWORD` / `DW_ENV_FILE` na VPN)
2. Manter queimadas + frio + rios no núcleo clima–respiratório–hidrologia
3. Evoluir SAN quando houver SISVAN/CadÚnico
4. Fan-out real com `data/input/contatos_alertas.csv` + `ALERT_FANOUT_ENABLED=true`
5. Nowcast epi formal quando SIVEP estiver estável
