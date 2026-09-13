-- SIVEP Malária — agregado municipal (sem PII).
-- Flag: USE_DW_SIVEP. Não substitui SIVEP-SRAG local.
-- Nota: a base DW pode estar defasada (ex.: último ano 2017); usa janela relativa ao MAX(AnoNotificacao).
WITH anos AS (
    SELECT MAX(TRY_CONVERT(int, AnoNotificacao)) AS ano_max
    FROM dbo.SIVEP_MALARIA
)
SELECT
    COALESCE(
        TRY_CONVERT(date, NULLIF(DataSintoma, '')),
        TRY_CONVERT(date, NULLIF(DataNotificacao, '')),
        TRY_CONVERT(date, NULLIF(DataExame, ''))
    ) AS data,
    CodigoMunicipioResidencia AS cod_ibge,
    MAX(MunicipioResidencia) AS municipio,
    COUNT_BIG(*) AS n_registros,
    SUM(COALESCE(TRY_CONVERT(int, NumeroCasos), 1)) AS casos_malaria
FROM dbo.SIVEP_MALARIA
WHERE TRY_CONVERT(int, AnoNotificacao) >= (SELECT ano_max - 2 FROM anos)
  AND NULLIF(LTRIM(RTRIM(CodigoMunicipioResidencia)), '') IS NOT NULL
GROUP BY
    COALESCE(
        TRY_CONVERT(date, NULLIF(DataSintoma, '')),
        TRY_CONVERT(date, NULLIF(DataNotificacao, '')),
        TRY_CONVERT(date, NULLIF(DataExame, ''))
    ),
    CodigoMunicipioResidencia;
