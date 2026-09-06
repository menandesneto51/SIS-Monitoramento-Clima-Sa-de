# Validação EHF / GeoCalor — SE 35/2026
Data da auditoria: 2026-09-04

## Fontes
- star_clima_geocalor_diario (265.114 linhas; 2021-07-24 a 2026-09-02)
- star_ondas_calor_evento (1.421 eventos)

## Checks
| Check | Resultado |
|-------|-----------|
| Universo municipal MT | 142 / 142 (0 códigos fora de MT) |
| Cobertura diária na janela 20/08–02/09 | 142 mun em todos os dias |
| Datas futuras na série observada | 0 |
| is_hw_day=1 com EHF≤0 | 0 |
| Eventos com duração < 3 dias | 0 |
| Evento vs diário (ehf_max, intensidade, fim) | 0 inconsistências / 89 eventos |
| EHF>0 sem is_hw_day | 41 dias (isolados <3 consecutivos — correto) |
| Lag vs corte (hoje−1=03/09) | 1 dia (série até 02/09) |

## Janela operacional (boletim)
- Início: 2026-08-20 · Fim: 2026-09-02
- Último dia: 28 municípios em dia de onda (baixa 28)
- Na janela: 88 mun com ≥1 dia · 89 eventos (baixa 32 · severa 56 · extrema 1)
- Cuiabá: 5 dias de onda · EHF máx. 3,50 · pico severa · fora de onda em 02/09

## Intensidade relativa (amostra crítica)
Nova Xavantina (5106257): EHF máx. 6,96 > 3×EHF85 local (6,94) → **extrema** (correto).
Santo Afonso (5107263): EHF máx. 8,80 ≤ 3×EHF85 local (11,79) → **severa** (correto).
Valores brutos de EHF não ordenam severidade entre municípios.

## Status
EHF_VALIDATED = true
Pronto para regeneração do boletim.
