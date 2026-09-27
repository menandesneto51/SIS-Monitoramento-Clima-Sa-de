# PROJECT_CONTEXT.md — SIS Clima-Saúde MT

## Objetivo
Sistema de monitoramento integrado clima-saúde para Mato Grosso, com ingestão de fontes meteorológicas, ambientais, epidemiológicas, assistenciais e operacionais.

## Integração atual
Este repositório passa a atuar também como produtor técnico para a camada `Operational Risk` do simulador multigravo/CIEVS no repositório `aprendendo-sobre-o-sarampo`.

## Contratos verificados
- PM2.5 / CAMS;
- meteorologia;
- ocupação assistencial;
- SRAG/SIVEP;
- autonomia de insumos;
- falhas de infraestrutura;
- latência de comunicação.

## Incremento atual
Preparar a identificação segura de notificações de intoxicação exógena por inalação de fumaça.

### Regra
Não alterar a query produtiva `sql/dw_sinan_agravos_calor.sql` até confirmar os nomes reais das colunas da view `dbo.VW_SINAN_INTOXICACAOEXOGENA`.

## Ambiente
Credenciais do DW somente por `.env`; nunca versionar usuário/senha/token.
