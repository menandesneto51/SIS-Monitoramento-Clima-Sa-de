-- Arboviroses via notificação individual (filtro por nome do agravo).
-- Complementa dengue/chikungunya/zika quando as fichas específicas não existirem
-- ou quando houver Febre Amarela, Oropouche, Mayaro e correlatas.

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'NOTIFICACAO_INDIVIDUAL_ARBO' AS fonte_sinan,
    Agravo AS agravo,
    NumeroNotificacao AS numero_notificacao,
    DataNotificacao AS data_notificacao,
    AnoNotificacao AS ano,
    MesNotificacao AS mes,
    SemanaNotificacao AS semana_epidemiologica,
    DataPrimeirosSintomas AS data_primeiros_sintomas,
    CodigoMunicipioResidencia AS cod_ibge_residencia,
    MunicipioResidencia AS municipio_residencia,
    CodigoMunicipioNotificacao AS cod_ibge_notificacao,
    MunicipioNotificacao AS municipio_notificacao,
    RegionalResidencia AS regional_residencia,
    RegionalNotificacao AS regional_notificacao,
    IdadePaciente AS idade,
    FaixaEtaria AS faixa_etaria,
    SexoPaciente AS sexo,
    RacaPaciente AS raca_cor,
    ClassificacaoFinal AS classificacao_final,
    Evolucao AS evolucao,
    DataObito AS data_obito,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_NOTIFICACAOINDIVIDUAL
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1
  AND (
        UPPER(Agravo) LIKE '%DENGUE%'
     OR UPPER(Agravo) LIKE '%ZIKA%'
     OR UPPER(Agravo) LIKE '%CHIKUNGUNYA%'
     OR UPPER(Agravo) LIKE '%FEBRE AMARELA%'
     OR UPPER(Agravo) LIKE '%OROPOUCHE%'
     OR UPPER(Agravo) LIKE '%MAYARO%'
     OR UPPER(Agravo) LIKE '%ARBOVIROSE%'
     OR UPPER(Agravo) LIKE '%WEST NILE%'
     OR UPPER(Agravo) LIKE '%FEBRE DO NILO%'
  );
