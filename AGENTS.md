# AGENTS.md — SIS Clima-Saúde MT

## Regra geral
O Cursor é o ambiente padrão de implementação e continuidade técnica.

## Fluxo obrigatório
1. CTO Virtual coordena o incremento.
2. Domain Specialist valida semântica epidemiológica/ambiental.
3. Data Architect valida contrato, chaves, granularidade e schema.
4. Data Governance valida proveniência, versionamento e qualidade.
5. Security valida segredos e acesso ao DW.
6. QA executa testes e regressão.
7. Observability valida logs, freshness e falhas de ingestão.
8. Chief Architect confirma separação ingestão -> domínio -> UI.
9. Product Owner valida utilidade operacional.

## Regras para DW/SINAN
- Nunca inventar nomes de colunas.
- Antes de alterar uma query produtiva, executar schema discovery.
- Nunca versionar credenciais.
- Consultas de descoberta devem ser somente leitura.
- Mudanças em Intoxicação Exógena devem preservar rastreabilidade até a view/tabela real.
- Não contar toda intoxicação exógena como fumaça.
- Não inferir fumaça apenas por via respiratória.
- Para fumaça, exigir agente + descrição + via + circunstância compatíveis com o contrato documentado.

## Regras para integração com Operational Risk
- O SIS Clima produz/normaliza dados; não ativa COE automaticamente.
- Thresholds operacionais devem permanecer configuráveis e versionados.
- Dado ausente ou inválido não pode virar zero/verde.
- O consumidor downstream deve receber códigos IBGE e timestamps explícitos.
- Adapters externos não devem conter lógica institucional de acionamento.

## DoD
- schema/contrato validado;
- testes;
- documentação Cursor atualizada;
- nenhum segredo em diff;
- query produtiva alterada apenas após validação do schema real;
- revisão dos agentes aplicáveis.


## Regras cartográficas
- shapefile IBGE 2025 é a fonte primária de limites municipais;
- GeoJSON/TopoJSON são derivados web, nunca fonte autoritativa;
- validar CRS EPSG:4674 / SIRGAS 2000;
- exigir 142 feições e códigos IBGE únicos;
- não usar fuzzy matching para chave municipal no pipeline oficial;
- preservar topologia durante simplificação;
- gerar manifest com hashes dos componentes .shp/.shx/.dbf/.prj/.cpg e do artefato web;
