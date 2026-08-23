-- Detalhe intoxicação exógena — colunas de agente/circunstância para filtro fumaça/queimada.
SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    NumeroNotificacao AS numero_notificacao,
    DataNotificacao AS data_notificacao,
    AnoNotificacao AS ano,
    SemanaNotificacao AS semana_epidemiologica,
    ClassificacaoFinal AS classificacao_final,
    EvolucaoCaso AS evolucao,
    NumeroCasos AS numero_casos,
    LocalOcorrenciaExposicao AS local_ocorrencia_exposicao,
    LocalOcorrenciaExposicaoOutros AS local_ocorrencia_exposicao_outros,
    AgenteToxicoClassificacao AS agente_toxico_classificacao,
    AgenteToxicoClassificacaoOutro AS agente_toxico_classificacao_outro,
    AgenteToxico1NomeComercial AS agente_toxico1_nome_comercial,
    AgenteToxico1PrincipioAtivo AS agente_toxico1_principio_ativo,
    AgenteToxico2NomeComercial AS agente_toxico2_nome_comercial,
    AgenteToxico2PrincipioAtivo AS agente_toxico2_principio_ativo,
    AgenteToxico3NomeComercial AS agente_toxico3_nome_comercial,
    AgenteToxico3PrincipioAtivo AS agente_toxico3_principio_ativo,
    CircunstanciaExposicaoContaminacao AS circunstancia_exposicao_contaminacao,
    CircunstanciaExposicaoContaminacaoOutra AS circunstancia_exposicao_contaminacao_outra,
    ViaExposicaoContaminacao1 AS via_exposicao_contaminacao1,
    TipoExposicao AS tipo_exposicao
FROM dbo.VW_SINAN_INTOXICACAOEXOGENA
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1;
