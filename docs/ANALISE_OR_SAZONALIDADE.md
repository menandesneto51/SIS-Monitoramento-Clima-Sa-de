# Análise OR e sazonalidade (SIS Clima-Saúde MT)

Esta camada adiciona ao SIS um módulo inspirado no painel de meningites para:

- **Odds Ratio (OR) ecológico** clima–agravos/ocupação
- **Sazonalidade histórica** (índice mensal, heatmap SE×ano, perfil semanal e picos)
- **Lags temporais** clima–desfecho (0–14 dias)

## Referência metodológica interna

- `Meningites/02_estatisticas_or_meningites_v17.py`
- `Meningites/21_sazonalidade_meningites_v23.py`
- `Meningites/06_clima_casos_meningites_v17.py`

## Tabelas geradas no SIS

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

