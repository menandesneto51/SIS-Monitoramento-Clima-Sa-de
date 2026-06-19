-- Ajustar nomes das views/colunas conforme o ambiente SES/MT.
-- Regra operacional: SIVEP por município de residência e data de início dos sintomas.
SELECT
    CAST(data_inicio_sintomas AS date) AS data_sintomas,
    cod_ibge_residencia AS cod_ibge,
    municipio_residencia AS municipio,
    COUNT(*) AS casos_srag,
    SUM(CASE WHEN evolucao LIKE '%OBITO%' THEN 1 ELSE 0 END) AS obitos_srag,
    SUM(CASE WHEN uti = 1 OR internacao_uti = 1 THEN 1 ELSE 0 END) AS internacoes_uti
FROM dbo.SIVEP_SRAG
WHERE data_inicio_sintomas >= DATEADD(day, -60, GETDATE())
GROUP BY CAST(data_inicio_sintomas AS date), cod_ibge_residencia, municipio_residencia;
