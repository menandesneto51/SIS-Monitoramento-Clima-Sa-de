# Arquitetura Técnica

## Camadas

1. **Bronze**: ingestão bruta por CSV, API ou SQL Server.
2. **Silver**: padronização de colunas, datas, chaves municipais, unidades e tipos de leito.
3. **Gold**: indicadores calculados, classificação de níveis, recomendações e alertas.
4. **Dashboard**: consumo Streamlit e exportação para Power BI quando necessário.

## Relação com projetos anteriores

- **TITAN**: meteorologia, INMET, Copernicus, indicadores clima-saúde, matriz de risco e alerta operacional.
- **SENTINELA**: sinais/rumores, score tático, monitoramento de comunicação social e alertas indiretos.
- **AESOP**: dados assistenciais e vigilância sindrômica, pressão de atendimento e anomalias.
- **SIVEP/SRAG**: monitoramento respiratório, UTI, óbitos e pressão hospitalar associada.
- **LACEN/GAL**: exames, positividade, atrasos e associação clima-doença.
- **SINAN/SIM**: agravos e mortalidade para avaliação epidemiológica e pós-evento.
- **IndicaSUS/CNES**: capacidade instalada, ocupação, leitos, perfil de unidade e resiliência operacional.

## Regra decisória

O nível final do município é o maior nível entre:

- risco biometeorológico;
- pressão assistencial;
- capacidade/ocupação hospitalar;
- falhas operacionais de água, energia e climatização;
- autonomia de estoque;
- sinais SENTINELA;
- óbitos suspeitos;
- alertas INMET.

```text
nivel_final = max(nivel_clima, nivel_assistencia, nivel_leitos, nivel_infra, nivel_estoque, nivel_sentinela, nivel_mortalidade, nivel_inmet)
```
