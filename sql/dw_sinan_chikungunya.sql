-- Ficha específica Chikungunya (quando existir no DW).
SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'CHIKUNGUNYA' AS fonte_sinan,
    'Chikungunya' AS agravo,
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
    EvolucaoCaso AS evolucao,
    DataObito AS data_obito,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_CHIKUNGUNYA
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1;
