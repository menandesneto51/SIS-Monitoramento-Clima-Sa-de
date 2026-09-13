-- CNES equipamentos por tipo/grupo — competência mais recente, agregado municipal (sem PII).
-- Flag: USE_DW_CNES.
WITH ultima_competencia AS (
    SELECT MAX(CONCAT(Ano, RIGHT('00' + Mes, 2))) AS comp
    FROM dbo.CNES_EQUIPAMENTOS
)
SELECT
    CONCAT(Ano, '-', RIGHT('00' + Mes, 2), '-01') AS data,
    EstabelecimentoMunicipioCodigo AS cod_ibge,
    MAX(EstabelecimentoMunicipioNome) AS municipio,
    ISNULL(NULLIF(LTRIM(RTRIM(EquipamentoGrupo)), ''), 'Sem grupo') AS equipamento_grupo,
    ISNULL(NULLIF(LTRIM(RTRIM(EquipamentoTipo)), ''), 'Sem tipo') AS equipamento_tipo,
    SUM(COALESCE(QtdExistente, 0)) AS equipamentos_existentes,
    SUM(COALESCE(QtdUso, 0)) AS equipamentos_em_uso,
    COUNT(DISTINCT CodigoCnes) AS estabelecimentos
FROM dbo.CNES_EQUIPAMENTOS
WHERE CONCAT(Ano, RIGHT('00' + Mes, 2)) = (SELECT comp FROM ultima_competencia)
  AND NULLIF(LTRIM(RTRIM(EstabelecimentoMunicipioCodigo)), '') IS NOT NULL
GROUP BY
    Ano,
    Mes,
    EstabelecimentoMunicipioCodigo,
    ISNULL(NULLIF(LTRIM(RTRIM(EquipamentoGrupo)), ''), 'Sem grupo'),
    ISNULL(NULLIF(LTRIM(RTRIM(EquipamentoTipo)), ''), 'Sem tipo');
