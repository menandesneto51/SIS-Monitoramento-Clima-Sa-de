# Análise OR e sazonalidade (ARARAS MT)

Esta camada adiciona ao ARARAS MT análise ecológica de sazonalidade e odds ratio clima–agravos (calor, arboviroses, SRAG, ocupação):

- **Odds Ratio (OR) ecológico** clima–agravos/ocupação
- **Sazonalidade histórica** (índice mensal, heatmap SE×ano, perfil semanal e picos)
- **Lags temporais** clima–desfecho (0–14 dias)

## Método

Índice sazonal mensal, perfil de semana epidemiológica e OR 2×2 (exposição climática × desfecho de saúde). Resultados são ecológicos e não comprovam causalidade individual.

## Tabelas geradas no ARARAS MT

- `analise_clima_saude_odds_ratio_v1`
- `sazonalidade_indice_mensal_v1`
- `sazonalidade_heatmap_semana_ano_v1`
- `sazonalidade_perfil_semana_epi_v1`
- `sazonalidade_picos_v1`
- `clima_desfecho_lags_v1`

## Interpretação

- OR > 1 indica maior chance do desfecho no grupo mais exposto.
- OR < 1 indica menor chance relativa no grupo exposto.
- p-valor (Fisher) < 0,05 sugere associação estatística no recorte analisado.
- A análise é **ecológica e exploratória**: não prova causalidade individual.

## Uso operacional CIEVS

1. Verificar mês e semanas de maior risco sazonal.
2. Priorizar municípios com OR elevado e consistente com pressão assistencial.
3. Cruzar com níveis operacionais e com a aba AdaptaSUS para ação coordenada.
