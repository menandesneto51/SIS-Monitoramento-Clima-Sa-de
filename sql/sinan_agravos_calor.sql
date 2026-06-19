SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'NOTIFICACAO_INDIVIDUAL' AS fonte_sinan,
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

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'INTOXICACAO_EXOGENA' AS fonte_sinan,
    'Intoxicacao Exogena' AS agravo,
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
FROM dbo.VW_SINAN_INTOXICACAOEXOGENA
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'DENGUE' AS fonte_sinan,
    'Dengue' AS agravo,
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
FROM dbo.VW_SINAN_DENGUE
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1

UNION ALL

SELECT
    DataNotificacao AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    'SRAG_SINAN' AS fonte_sinan,
    'Sindrome Respiratoria Aguda Grave' AS agravo,
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
    ClassificacaoFinalSRAG AS classificacao_final,
    EvolucaoClinica AS evolucao,
    DataAltaObito AS data_obito,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 1;
