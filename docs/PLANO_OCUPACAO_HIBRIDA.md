# Plano: ocupação IndicaSUS × pressão SISREG

Atualizado: 2026-08-29

## Princípio de produto (decidido)

| Conceito | Fonte | Quem tem | Campo |
|---|---|---|---|
| **Ocupação hospitalar** | IndicaSUS / BdSES | Só mun. com unidade que notifica leitos | `ocupacao_leitos_pct` · `fonte_ocupacao` |
| **Pressão hospitalar / regulação** | SISREG | Demanda territorial (com ou sem hospital próprio) | `kpi_sisreg_*` · `ops_sisreg_municipio` |

- Ausência de IndicaSUS **não é falha** — é município sem hospital notificante.
- SISREG **nunca** vira `% ocupação`.
- Índice G/A/V (`indice_pressao_saude`) **compõe** os pilares; sem ocupação, renormaliza pesos.

## 1. Hierarquia de fontes (não misturar conceitos)

| Prioridade | Fonte | O que mede | Pode virar `ocupacao_leitos_pct`? |
|---|---|---|---|
| **P0** | IndicaSUS / BdSES (`ind.*` + geo) | Leitos existentes × ocupados **em tempo real** | **Sim** — única taxa de ocupação verdadeira |
| P1 | SISREG (`VW_HOSPITALAR_SINTETICO`, ambulatorial) | Fila / solicitação / regulação | **Não** — pressão regulatória |
| P2 | DW `dbo.VW_INTERNACAO` | Produção AIH (internações, UTI, permanência) | **Não** — volume/demanda, sem denominador de leitos |

Regra: municípios sem IndicaSUS continuam `fonte_ocupacao=SEM_LEITOS_INDICASUS` (nulo).  
**Não** reintroduzir média estadual nem converter fila SISREG em “% ocupação”.

## 2. Fase A — IndicaSUS (feito / em curso)

### A1. Recuperar unidades órfãs (implementado)
Problema: `UnidadeNotificadoraId` sem linha em `dbo.UnidadeSaude` → `LocalidadeId` nulo.

Solução no `atualizar_ocupacao_indicasus.py`:
1. `COALESCE` geo: `UnidadeSaude` → `Estabelecimento` → `form.Hospital`
2. Resolver IBGE subindo `PaiLocalidadeId` (bairro → município)

Esperado: as ~46 unidades órfãs entram no agregado municipal; cobertura sobe acima de 39 mun. (ainda **não** 142).

**Resultado 2026-08-29:** **58** municípios com `INDICASUS_TEMPO_REAL`; **209** unidades com geo; **0** órfãs; ~10.365 leitos / 4.496 ocupados (~43,4%).

### A1b. Filtros SIEGES (dash ocupação) — 2026-08-29

Alinhamento em `atualizar_ocupacao_indicasus.py` (numeração ativa, não só `QtdExistente`):

| Filtro SIEGES | Campo BdSES |
|---|---|
| SituacaoAtual ≠ Bloqueado | `TipoAcompanhamento <> 'Bloqueado'` (fora do denominador) |
| Tipo ∈ SUS Habilitado / SUS Não Habilitado | `NumeracaoLeito…Tipo` (exclui `Não SUS`) |
| TipoLeito ≠ Pronto Atendimento | `CategoriaCNES.Nome NOT LIKE 'Pronto Atendimento%'` |
| Unidades listadas (UPA, mista, etc.) | `UNIDADES_EXCLUIDAS_SIEGES` + padrões de nome |

**Após filtros (2026-08-29):** ~**45** mun. / **121** unidades / **5.684** leitos elegíveis / **3.115** ocupados (~**54,8%**). Bloqueados ficam fora do denominador.

### A2. Lacuna estrutural restante
Municípios sem unidade notificando leitos no schema `ind` continuam sem taxa.  
Ação institucional: IndicaSUS / assistência ampliarem notificação — não é bug de consulta.

## 3. Fase B — SISREG como **pressão**, não ocupação

Já existe: `ops_sisreg_municipio` (live ou CSV).

Usso proposto no painel / índice de pressão:
- Filas hospitalares e ambulatoriais por município de residência
- Indicadores: pendentes, tempo médio, volume 7d/30d
- Rótulo: `fonte_pressao_sisreg` (separado de `fonte_ocupacao`)

**Não** calcular `ocupacao ≈ f(fila)` sem denominador de leitos CNES/IndicaSUS.

### Consulta-alvo (rascunho operacional)
Parametrizar por janela (ex.: 7/30 dias) e município IBGE 51*, agregando status da `VW_HOSPITALAR_SINTETICO` — volume alto: sempre filtrar data + UF.

## 4. Fase C — `VW_INTERNACAO` (DW) como **demanda hospitalar**

Já parcialmente usado: `sql/dw_internacao_cid_clima.sql` (CIDs clima).

Expansão proposta (nova tabela, ex. `internacao_pressao_municipal`):
- Internações 7d / 30d por `CodigoMunicipioOcorrencia` **e** residência
- Diárias UTI (`TeveDiariasUTI` / `DiariasUTI`)
- Permanência média
- Taxa por 100 mil (com população IBGE)

Útil para: calor/fumaça, carga hospitalar, boletim.  
**Não** substitui % ocupação de leitos.

## 5. Fase D — Integração no painel (ordem sugerida)

1. ~~Recuperar órfãs IndicaSUS~~ → re-rodar ocupação + enrich  
2. Declarar no UI: “ocupação tempo real = IndicaSUS (N mun.); demais sem leitos notificados”  
3. Expor cards SISREG (fila) e internamentos DW **ao lado**, não no mesmo campo  
4. Opcional: índice composto `carga_assistencial` = f(ocupação IndicaSUS se houver, senão percentil de fila SISREG + internamentos 7d) — com documentação explícita  
5. Homologar com STI: lista de municípios sem notificação IndicaSUS + pedido de cadastro

## 6. O que pedir à STI (texto curto)

1. Confirmar se `form.Hospital` / `Estabelecimento` são chaves estáveis para `UnidadeNotificadoraId` (já usadas no ARARAS).  
2. Relação oficial unidade notificante × CNES × IBGE para as que ainda falharem.  
3. Views/documentação: existe **capacidade de leitos** no DW/SISREG além do BdSES? (hoje: não encontrada em `VW_INTERNACAO` / `VW_HOSPITALAR_SINTETICO`).  
4. Apoio operacional para municípios sem notificação de leitos no IndicaSUS.

## 7. Critérios de aceite

| Critério | Meta |
|---|---|
| Unidades com leito e geo resolvido | ~100% das unidades do schema `ind` com ref. de leito |
| `fonte_ocupacao` | só `INDICASUS_TEMPO_REAL` ou `SEM_LEITOS_INDICASUS` |
| SISREG / VW_INTERNACAO | colunas próprias; sem copiar para `ocupacao_leitos_pct` |
| Smoke | `com_ocupacao` sobe após A1; pressão não achata |
