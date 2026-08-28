# Relatório de QA final — Boletim El Niño SE 34/2026 (V7)

**Markdown:** `docs/apresentacoes/Boletim_ElNino_SE_34-2026.md`  
**PDF:** `docs/apresentacoes/Boletim_ElNino_SE_34-2026_apresentavel_v7.pdf`  
**Motivo da V7:** a V6 estava bloqueada para escrita (arquivo aberto).  
**Páginas:** 20 (meta editorial 18–19; ver justificativa abaixo).

## Hidrologia (bloqueador)

Fonte: `resumo_municipal_atual.situacao_hidro` (10 municípios com dado; 132 sem dado).

| Categoria | n | Municípios (dado real) |
| --- | --- | --- |
| Baixa disponibilidade (`seca_baixa`) | 8 | Aripuanã, Campos de Júlio, Jauru, Juína, Nova Lacerda, Pontes e Lacerda, Sapezal, Vila Bela da Santíssima Trindade |
| Risco elevado de inundação (`inundacao_alta`) | 1 | Comodoro |
| Habitual (`normal`) | 1 | Vale de São Domingos |
| Cobertura | 10 | 10 de 142 (7,0%) |
| Soma | 8+1+1 = 10 | assert ok |

O objeto `hydro_facts` no snapshot é a única origem desses totais. `municipios_hidro_alerta` conta **apenas seca** (8), sem somar inundação. Epidemiologia e cenário de estiagem usam 8; cenário de inundação usa 1, sem somar categorias e sem a frase “não há evidência municipal suficiente”.

## Classes ARARAS nesta geração

Rodada ao gerar o MD (25/08/2026): **amarela 3 · laranja 55 · vermelha 47 · roxa 37** (84/142 vermelho+roxo); projeção **vermelha 6 · roxa 136** (142/142); **104/141** em agravamento; **1** sem pareamento. A fórmula de classes não foi alterada; os totais diferem dos 21/49/35/37 da revisão anterior porque o `resumo_municipal_atual` foi relido ao regenerar o boletim.

## QA automático do Markdown

`Issues: 0` (incluindo HYDRO_TOTAL_ERROR, FACT_CONSISTENCY_ERROR, SECTION_SEQUENCE_ERROR, SAF).

## QA de paginação do PDF

| Código | Resultado | Justificativa se ≠ 0 |
| --- | --- | --- |
| PAGE_UNDERFILLED | 0 não justificado | p. 4 e p. 11 são páginas de mapa (Mapa 1/2 e Mapa 3); o corpo de texto é curto porque a figura ocupa a área útil. |
| ORPHAN_TEXT | 0 | O bloco “Implicações para a saúde — fogo e ar” deixou de ser página exclusiva; o parágrafo ficou no fim da seção 9. |
| ORPHAN_TITLE | 0 | Seção 17 inicia a p. 19; glossário/metodologia fluem na p. 18. |
| TABLE_OVERFLOW | 0 | Tabelas com `repeatRows=1`; Top 10 e distâncias não vão em KeepTogether. |
| SECTION_SEQUENCE_ERROR | 0 | Seções `## 1` … `## 18` consecutivas; 11b/11c viraram `###`. |
| HYDRO_TOTAL_ERROR | 0 | 8+1+1=10. |
| FACT_CONSISTENCY_ERROR | 0 no texto publicado | Aviso interno de driver 105 > 104 agravadores **não** foi publicado; cálculo de classes não foi alterado. |
| ACRONYM_FIRST_USE_ERROR | 0 | SAF ausente do PDF; UNIEVS, DPOC, RENAME, PCDT, CEREST, VISAT, COSEMS-MT expandidos na primeira ocorrência. UTCI = Índice Universal de Clima Térmico (UTCI). |

## Página extra (20 vs 18–19)

Não se reduziu o corpo abaixo de Calibri 11. A vigésima página resulta de: dois mapas de classificação, Mapa 3 territorial, Top 10 e tabela de distâncias com cabeçalho repetido, e referências. Cortes pedidos (lista de classes compacta, encaminhamentos únicos, distâncias Top 8, hidrologia sem “9”) foram aplicados.

## Testes

`tests.test_boletim_el_nino_semanal` e `tests.test_prontidao_boletim`: OK (inclui `test_hydro_facts_separa_seca_e_inundacao`).  
`tests.test_boletim_referencias`: falha pré-existente de ordem da primeira referência (INMET vs CEMADEN); fora do escopo desta revisão.
