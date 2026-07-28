# Integração TITAN — solo, resiliência CNES e alertas

Camada operacional alinhada ao legado TITAN, com **código legível** e fontes oficiais (sem ofuscação / sem scrapers stealth — política SES).

## O que entra no SIS

| Bloco | Fonte | Tabelas / colunas |
|-------|--------|-------------------|
| Saturação do solo | Open-Meteo (hourly → daily) | `met_biometeo.umidade_solo_*`, `indice_saturacao_solo`, `solo_saturacao_municipal` |
| Resiliência + CNES | DW `CNES_LEITOS` / `CNES_ESTABELECIMENTOS` | `ops_cnes_municipio`, `ops_resumo_operacional_cnes`, `indice_resiliencia` enriquecido |
| Alertas TITAN | INMET API/CSV + Cemaden `wsAlertas2` + ANA | `inmet_alertas`, `cemaden_alertas`, `ana_risco_municipal`, `hidro_risco_municipal` |

## Índice de saturação do solo

- Umidade volumétrica (m³/m³) nas camadas superficiais Open-Meteo.
- Normalização operacional vs. referência de saturação (~0,42 m³/m³) → `indice_saturacao_solo` 0–100.
- Classes: `baixa` / `moderada` / `alta` / `critica` (distintas de saturação de leitos).

## Resiliência vs CNES

- `indice_resiliencia`: capacidade de resposta (ocupação + estoque + infra + busca + comunicação).
- Com CNES disponível, o componente `capacidade_leitos` mistura leitos livres e capacidade instalada per capita.
- `indice_capacidade_cnes`: proxy de capacidade assistencial instalada (não é o mesmo que resiliência).

## Alertas

Consolidados na aba **Clima / TITAN** e, de forma unificada, na aba **Alertas**:

- Tabela `alerta_integrado_sis_titan`: `nivel_alerta_integrado = max(SIS, INMET, Cemaden, solo, hidro, calor)`.
- Ajudante de interpretação (padrão Meningites): guia + justificativa + download `.md`.

## Fora de escopo

- Robô Vigidesastres/INMET com scraping ofuscado
- ERA5-CDS como fonte primária operacional desta entrega
