# Indicadores SIVEP-Gripe / SRAG — Ministério da Saúde

## Documentação avaliada

| Documento | Uso neste módulo |
|-----------|------------------|
| [Guia de Vigilância Integrada da covid-19, influenza e outros vírus respiratórios](https://www.gov.br/saude/pt-br/centrais-de-conteudo/publicacoes/guias-e-manuais/2024/guia-vigilancia-integrada-da-covid-19-influenza-e-outros-virus-respiratorios-de-importancia-em-saude-publica) (MS/SVSA, 2024) | Definição de caso SRAG, classificação final, qualidade laboratorial, metas sentinela |
| Caderno de Análise de Indicadores da vigilância sentinela de SG (MS, 2024; metas OMS) | Escala de desempenho (>80% meta; 21–80% baixo; 1–20% baixíssimo; 0% silencioso) |
| Nota Técnica Conjunta nº 01/257/2025 SVSA/SAPS/SAES/MS | Uso operacional de SIVEP-Gripe para SRAG e ênfase em notificação oportuna |
| [Dados Abertos SUS — SRAG / SIVEP-Gripe](https://dadosabertos.saude.gov.br/dataset/srag-2019-a-2026) | Modelo de variáveis e curva por SE |

## O que foi importado no ARARAS MT

Catálogo em `config/indicadores_ms_sivep.yaml` (SRAG-01 … SRAG-12).

Motor: `sisclima/engines/sivep_ms_indicators.py`.

Tabelas geradas pelo pipeline:

- `epi_sivep_srag` — diário municipal (casos, UTI, óbitos, letalidade, incidência, z-score, vírus)
- `epi_sivep_se_municipal` — curva por semana epidemiológica
- `epi_sivep_virus_se` — distribuição viral por SE
- `epi_sivep_qualidade_ms` — cobertura lab + classificação OMS/MS
- `epi_sivep_indicadores_ms` — painel longo por indicador
- `dicionario_indicadores_ms_sivep` — catálogo persistido

UI: `pages/13_SIVEP_Indicadores_MS.py`.

## Limitações (honesto)

Indicadores de **unidade sentinela de SG** que dependem de denominador de atendimentos gerais da US (proporção SG/atendimentos, nº de amostras/semana por US) **não** estão neste módulo: a base operacional atual é **SRAG hospitalizado** via SIVEP local. Para completá-los, será necessário importar o formulário agregado sentinela.

## Como atualizar

1. Colocar exportações SIVEP em `data/input/sivep_atualizacao/`
2. Rodar atualização local / pipeline
3. Abrir a página **SIVEP Indicadores MS**
