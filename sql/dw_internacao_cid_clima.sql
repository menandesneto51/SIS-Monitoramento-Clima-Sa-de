-- IndicaSUS / internações hospitalares no DW SES-MT (view dbo.VW_INTERNACAO).
-- Agrega internações por CID sensível ao clima (fumaça, calor, DDA, cardio).
SELECT
    DATEFROMPARTS(
        TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(AnoInternacao)), '')),
        COALESCE(
            TRY_CONVERT(int, LEFT(LTRIM(RTRIM(MesInternacao)), 2)),
            TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(MesCompetencia)), '')),
            1
        ),
        COALESCE(TRY_CONVERT(int, NULLIF(LTRIM(RTRIM(DiaInternacao)), '')), 1)
    ) AS data,
    AnoInternacao AS ano_internacao,
    MesInternacao AS mes_internacao,
    MesCompetencia AS mes_competencia,
    CodigoMunicipioResidencia AS cod_ibge,
    MunicipioResidencia AS municipio,
    RegionalResidencia AS regional_residencia,
    CodigoDiagnosticoPrincipal AS codigo_diagnostico_principal,
    DiagnosticoPrincipal AS diagnostico_principal,
    DiagnosticoSecundario AS diagnostico_secundario,
    ProcedimentoCodigo AS procedimento_codigo,
    ProcedimentoRealizado AS procedimento_realizado,
    CaraterInternacao AS carater_internacao,
    NumeroInternacoes AS numero_internacoes,
    NumeroObitos AS numero_obitos,
    CASE
        WHEN CodigoDiagnosticoPrincipal LIKE 'J30%' OR CodigoDiagnosticoPrincipal LIKE 'J45%'
          OR DiagnosticoSecundario LIKE 'J30%' OR DiagnosticoSecundario LIKE 'J45%' THEN 'resp_alergico'
        WHEN CodigoDiagnosticoPrincipal LIKE 'J18%' OR CodigoDiagnosticoPrincipal LIKE 'J06%'
          OR CodigoDiagnosticoPrincipal LIKE 'J00%' THEN 'resp_infeccioso'
        WHEN CodigoDiagnosticoPrincipal LIKE 'E86%' OR CodigoDiagnosticoPrincipal LIKE 'T67%'
          OR CodigoDiagnosticoPrincipal LIKE 'X30%' THEN 'desidratacao_calor'
        WHEN CodigoDiagnosticoPrincipal LIKE 'A09%' OR CodigoDiagnosticoPrincipal LIKE 'K52%' THEN 'dda'
        WHEN CodigoDiagnosticoPrincipal LIKE 'I%' THEN 'cardiovascular'
        ELSE 'outros'
    END AS grupo_internacao_clima
FROM dbo.VW_INTERNACAO
WHERE TRY_CONVERT(int, AnoInternacao) >= YEAR(GETDATE()) - 1
  AND CodigoMunicipioResidencia LIKE '51%';
