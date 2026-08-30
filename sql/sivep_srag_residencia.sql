-- SIVEP/SRAG — fallback operacional no DW SES-MT.
-- O DW não expõe dbo.SIVEP_SRAG; a fonte disponível é a ficha SINAN SRAG.
-- Caso a SES disponibilize export oficial SIVEP em data/input/sivep_atualizacao/,
-- a carga local tem prioridade sobre este SQL.
SELECT
    TRY_CONVERT(date, NULLIF(DataPrimeirosSintomas, '')) AS data_sintomas,
    TRY_CONVERT(date, NULLIF(DataNotificacao, '')) AS data_notificacao,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    IdadePaciente AS idade,
    SexoPaciente AS sexo,
    EvolucaoClinica AS evolucao,
    ClassificacaoFinalSRAG AS classificacao_final,
    CASE
        WHEN FoiInternadoEmUTI IN ('1', 'Sim', 'SIM', 'S') THEN 1
        ELSE 0
    END AS uti,
    CASE
        WHEN FezUsoSuporteVentilatorio IN ('1', 'Sim', 'SIM', 'S') THEN 1
        ELSE 0
    END AS suporte_ventilatorio,
    CASE
        WHEN EvolucaoClinica LIKE '%Obito%'
          OR EvolucaoClinica LIKE '%Óbito%'
          OR EvolucaoClinica LIKE '%OBITO%'
        THEN 1
        ELSE 0
    END AS obito,
    COALESCE(
        NULLIF(DiagnosticoEtiologicoInfluenzaA, ''),
        NULLIF(DiagnosticoEtiologicoInfluenzaB, ''),
        NULLIF(DiagnosticoEtiologicoVirusSincicialRespiratorio, ''),
        NULLIF(DiagnosticoEtiologicoAdenovirus, ''),
        ClassificacaoFinalSRAG
    ) AS virus,
    NumeroNotificacao AS numero_notificacao,
    NumeroCasos AS numero_casos
FROM dbo.VW_SINAN_SINDROMERESPIRATORIAAGUDAGRAVE
WHERE TRY_CONVERT(int, AnoNotificacao) >= YEAR(GETDATE()) - 2
  AND (
        TRY_CONVERT(date, NULLIF(DataPrimeirosSintomas, '')) IS NOT NULL
     OR TRY_CONVERT(date, NULLIF(DataNotificacao, '')) IS NOT NULL
  );
